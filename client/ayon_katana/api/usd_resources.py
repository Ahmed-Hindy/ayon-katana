"""Plan resource transfers for extracted Katana USD look layers."""

from __future__ import annotations

import glob
import os
import re
from pathlib import Path
from typing import Any, Iterable

COMPOSITION_EXTENSIONS = {
    ".abc",
    ".usd",
    ".usda",
    ".usdc",
    ".usdz",
    ".usdlc",
    ".usdnc",
}
COLORSPACE_ATTRS = (
    "inputs:color_space",
    "inputs:tex0_colorSpace",
)
_URI_PATTERN = re.compile(r"^[a-z][a-z0-9+.-]*://", re.IGNORECASE)
_UDIM_PATTERN = re.compile(r"<UDIM>", re.IGNORECASE)


def _path_string(path: Any) -> str:
    return getattr(path, "pathString", None) or str(path)


def _iter_property_paths(layer: Any) -> list[Any]:
    paths = []

    def collect(path: Any) -> None:
        """Record one authored property path."""
        if path.IsPropertyPath():
            paths.append(path)

    layer.Traverse("/", collect)
    return paths


def _flatten_asset_values(value: Any) -> Iterable[Any]:
    if value is None:
        return
    if hasattr(value, "path"):
        yield value
        return
    if isinstance(value, (str, bytes)):
        yield value
        return
    try:
        iterator = iter(value)
    except TypeError:
        return
    for item in iterator:
        if hasattr(item, "path") or isinstance(item, str):
            yield item


def _asset_path(asset: Any) -> str:
    return str(getattr(asset, "path", asset) or "")


def _resolved_asset_hint(asset: Any) -> str:
    return str(getattr(asset, "resolvedPath", "") or "")


def _iter_asset_values(layer: Any, path: Any, spec: Any) -> list[Any]:
    """Return unique default and time-sampled asset values from a spec."""
    values = list(_flatten_asset_values(getattr(spec, "default", None)))
    list_samples = getattr(layer, "ListTimeSamplesForPath", None)
    query_sample = getattr(layer, "QueryTimeSample", None)
    if callable(list_samples) and callable(query_sample):
        for time_code in list_samples(path) or []:
            values.extend(_flatten_asset_values(query_sample(path, time_code)))

    output = []
    seen = set()
    for asset in values:
        key = (_asset_path(asset), _resolved_asset_hint(asset))
        if not key[0] or key in seen:
            continue
        seen.add(key)
        output.append(asset)
    return output


def _layer_anchor_path(layer: Any) -> str:
    for attribute in ("realPath", "resolvedPath", "identifier"):
        value = str(getattr(layer, attribute, "") or "")
        if not value or value.startswith("anon:") or _URI_PATTERN.match(value):
            continue
        path = Path(value)
        if path.suffix:
            return str(path)
    return ""


def _resolve_relative_asset(layer: Any, authored: str, hint: str = "") -> str:
    """Resolve an authored asset against its owning layer without mutation."""
    if hint and Path(hint).is_absolute():
        return os.path.normpath(hint)
    if Path(authored).is_absolute():
        return os.path.normpath(authored)

    try:
        from pxr import Sdf

        resolved = Sdf.ComputeAssetPathRelativeToLayer(layer, authored)
    except Exception:
        resolved = ""
    if resolved and Path(resolved).is_absolute():
        return os.path.normpath(resolved)

    layer_path = _layer_anchor_path(layer)
    if layer_path:
        return os.path.normpath(str(Path(layer_path).parent / authored))
    return ""


def _build_source_anchor_map(source_stage: Any) -> dict[tuple[str, str], set[str]]:
    """Map authored relative asset values to original source-layer locations."""
    if source_stage is None:
        return {}
    try:
        layers = list(source_stage.GetLayerStack())
    except Exception:
        return {}

    anchors: dict[tuple[str, str], set[str]] = {}
    for layer in layers:
        for path in _iter_property_paths(layer):
            spec = layer.GetAttributeAtPath(path)
            if spec is None or "asset" not in str(getattr(spec, "typeName", "")):
                continue
            for asset in _iter_asset_values(layer, path, spec):
                authored = _asset_path(asset)
                if (
                    not authored
                    or Path(authored).is_absolute()
                    or _URI_PATTERN.match(authored)
                ):
                    continue
                resolved = _resolve_relative_asset(
                    layer,
                    authored,
                    _resolved_asset_hint(asset),
                )
                if resolved:
                    anchors.setdefault((_path_string(path), authored), set()).add(
                        resolved
                    )
    return anchors


def _get_colorspace(spec: Any) -> str:
    has_info = getattr(spec, "HasInfo", None)
    get_info = getattr(spec, "GetInfo", None)
    if callable(has_info) and callable(get_info) and has_info("colorSpace"):
        return str(get_info("colorSpace") or "")

    path = getattr(spec, "path", None)
    layer = getattr(spec, "layer", None)
    if path is None or layer is None:
        return ""
    get_prim_path = getattr(path, "GetPrimPath", None)
    if not callable(get_prim_path):
        return ""
    prim_path = get_prim_path()
    append_property = getattr(prim_path, "AppendProperty", None)
    if not callable(append_property):
        return ""
    for name in COLORSPACE_ATTRS:
        colorspace_spec = layer.GetAttributeAtPath(append_property(name))
        if colorspace_spec is not None and getattr(colorspace_spec, "default", None):
            return str(colorspace_spec.default)
    return ""


def _expand_local_asset(resolved: str) -> list[str]:
    if _UDIM_PATTERN.search(resolved):
        pattern = _UDIM_PATTERN.sub("[0-9][0-9][0-9][0-9]", resolved)
        files = sorted(glob.glob(pattern))
    else:
        files = [resolved] if Path(resolved).is_file() else []
    return [
        os.path.normpath(filepath) for filepath in files if Path(filepath).is_file()
    ]


def plan_look_resources(
    layer: Any,
    resources_dir: str | Path,
    source_stage: Any,
) -> dict[str, Any]:
    """Build resource, remap, and transfer data for a USD look layer.

    Args:
        layer: Extracted look Sdf layer.
        resources_dir: Final publish resources directory.
        source_stage: Original composed source stage used to anchor staged
            relative asset values.

    Returns:
        Dictionary containing ``resources``, ``assetRemap``, and ``transfers``.

    Raises:
        ValueError: A resource is remote, missing, ambiguously anchored, or
            collides with another resource destination.
    """
    resources_directory = Path(resources_dir)
    source_anchors = _build_source_anchor_map(source_stage)
    resources = []
    remap: dict[str, str] = {}
    transfers = []
    transfer_sources = set()
    destination_sources: dict[str, str] = {}
    resource_keys = set()

    for path in _iter_property_paths(layer):
        spec = layer.GetAttributeAtPath(path)
        if spec is None or "asset" not in str(getattr(spec, "typeName", "")):
            continue
        attribute_path = _path_string(path)
        colorspace = _get_colorspace(spec)
        for asset in _iter_asset_values(layer, path, spec):
            authored = _asset_path(asset).replace("\\", "/")
            if not authored:
                continue
            if Path(authored).suffix.lower() in COMPOSITION_EXTENSIONS:
                continue
            if _URI_PATTERN.match(authored):
                raise ValueError(
                    f"USD look resource {attribute_path} uses unsupported remote URI: "
                    f"{authored}"
                )

            if Path(authored).is_absolute():
                resolved = os.path.normpath(authored)
            else:
                candidates = source_anchors.get((attribute_path, authored), set())
                if len(candidates) > 1:
                    formatted = ", ".join(sorted(candidates))
                    raise ValueError(
                        "USD look resource "
                        f"{attribute_path} is ambiguous: {authored!r} "
                        f"resolves to multiple source files: {formatted}"
                    )
                if candidates:
                    resolved = next(iter(candidates))
                else:
                    resolved = _resolve_relative_asset(
                        layer,
                        authored,
                        _resolved_asset_hint(asset),
                    )
            if not resolved:
                raise ValueError(
                    f"Unable to resolve USD look resource {attribute_path}: {authored}"
                )

            files = _expand_local_asset(resolved)
            if not files:
                raise ValueError(
                    f"USD look resource {attribute_path} does not resolve to local "
                    f"files: {authored} -> {resolved}"
                )

            remap_path = f"./resources/{Path(authored).name}"
            remap[os.path.normpath(authored)] = remap_path
            resource_key = (attribute_path, authored, tuple(files), colorspace)
            if resource_key not in resource_keys:
                resource_keys.add(resource_key)
                resources.append(
                    {
                        "attribute": attribute_path,
                        "source": authored,
                        "files": files,
                        "color_space": colorspace or None,
                    }
                )

            for source in files:
                canonical_source = os.path.normcase(os.path.abspath(source))
                destination = resources_directory / Path(source).name
                destination_key = os.path.normcase(str(destination))
                previous_source = destination_sources.get(destination_key)
                if previous_source is not None and previous_source != canonical_source:
                    raise ValueError(
                        "USD look resources contain a destination basename collision: "
                        f"{Path(source).name!r} maps from both {previous_source!r} "
                        f"and {canonical_source!r}."
                    )
                destination_sources[destination_key] = canonical_source
                if canonical_source in transfer_sources:
                    continue
                transfer_sources.add(canonical_source)
                transfers.append((source, str(destination)))

    resources.sort(key=lambda item: (item["source"], item["attribute"]))
    transfers.sort(key=lambda item: (item[1], item[0]))
    return {
        "resources": resources,
        "assetRemap": dict(sorted(remap.items())),
        "transfers": transfers,
    }
