"""Finalize staged Katana USD layers without modifying live source layers."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

COMPOSITION_EXTENSIONS = {
    ".abc",
    ".usd",
    ".usda",
    ".usdc",
    ".usdz",
    ".usdlc",
    ".usdnc",
}
_SDF_FORMAT_ARGS = ":SDF_FORMAT_ARGS:"


def _usd_path(value: str | Path) -> str:
    return str(value).replace("\\", "/")


def _mapping_key(value: str | Path) -> str:
    return os.path.normcase(os.path.normpath(str(value)))


def _asset_filesystem_part(value: str) -> str:
    return value.split(_SDF_FORMAT_ARGS, 1)[0]


def _is_composition_path(value: str) -> bool:
    path = _asset_filesystem_part(value)
    return Path(path).suffix.lower() in COMPOSITION_EXTENSIONS


def get_representation_source_paths(instance: Any, representation: dict) -> list[str]:
    """Return absolute staged source paths for one representation."""
    staging_dir = representation.get("stagingDir") or instance.data.get("stagingDir")
    files = representation.get("files_raw", representation.get("files"))
    if not files:
        return []
    if isinstance(files, str):
        files = [files]
    elif not isinstance(files, (list, tuple)):
        raise ValueError(
            "Representation files must be a string, list, or tuple for USD remapping."
        )

    output = []
    for filename in files:
        filename = str(filename)
        filesystem_part = _asset_filesystem_part(filename)
        if Path(filesystem_part).is_absolute():
            source = filesystem_part
        elif staging_dir:
            source = str(Path(staging_dir) / filesystem_part)
        else:
            raise ValueError(
                "Representation has relative files but no staging directory: "
                f"{representation!r}"
            )
        output.append(os.path.normpath(source))
    return output


def build_publish_path_map(context: Any) -> dict[str, str]:
    """Map all active staged representation files to Core-computed publish paths."""
    from ayon_core.pipeline.publish.lib import get_instance_expected_output_path

    mapping: dict[str, str] = {}
    for instance in context:
        if not instance.data.get("active", True) or not instance.data.get(
            "publish", True
        ):
            continue
        for representation in instance.data.get("representations") or []:
            name = representation.get("name")
            if not name:
                continue
            extension = representation.get("ext")
            expected_path = Path(
                get_instance_expected_output_path(
                    instance,
                    representation_name=name,
                    ext=extension,
                )
            )
            sources = get_representation_source_paths(instance, representation)
            if len(sources) == 1:
                destinations = [expected_path]
            else:
                destinations = [
                    expected_path.parent / Path(source).name for source in sources
                ]
            for source, destination in zip(sources, destinations):
                mapping[_mapping_key(source)] = _usd_path(destination)
    return mapping


def _get_applied_items(list_proxy: Any) -> list[Any]:
    """Return reference/payload list items across supported USD versions."""
    getter = getattr(list_proxy, "GetAppliedItems", None)
    if callable(getter):
        return list(getter())
    return list(list_proxy.ApplyEditsToList([]))


def _iter_layer_composition_paths(layer: Any) -> list[str]:
    output = [str(path) for path in layer.subLayerPaths if path]

    def inspect(path: Any) -> None:
        """Collect external references and payloads from one prim spec."""
        if not path.IsPrimPath():
            return
        prim_spec = layer.GetPrimAtPath(path)
        if prim_spec is None:
            return
        for list_proxy in (prim_spec.referenceList, prim_spec.payloadList):
            for item in _get_applied_items(list_proxy):
                asset_path = str(item.assetPath or "")
                if asset_path:
                    output.append(asset_path)

    layer.Traverse("/", inspect)
    return output


def _resolve_asset_against_layer(layer: Any, authored: str) -> str:
    """Resolve one relative composition path against its owning source layer."""
    filesystem_part = _asset_filesystem_part(authored)
    if Path(filesystem_part).is_absolute():
        return os.path.normpath(filesystem_part)
    from pxr import Sdf

    resolved = Sdf.ComputeAssetPathRelativeToLayer(layer, filesystem_part)
    if resolved and Path(resolved).is_absolute():
        return os.path.normpath(resolved)

    for layer_path in (layer.realPath, layer.resolvedPath, layer.identifier):
        layer_path = str(layer_path or "")
        if not layer_path or layer_path.startswith("anon:"):
            continue
        return os.path.normpath(str(Path(layer_path).parent / filesystem_part))
    return ""


def build_source_composition_anchors(source_stage: Any) -> dict[str, set[str]]:
    """Map source-stage relative composition paths to their original resolutions."""
    if source_stage is None:
        return {}
    layers = list(source_stage.GetLayerStack())

    anchors: dict[str, set[str]] = {}
    for layer in layers:
        for authored in _iter_layer_composition_paths(layer):
            filesystem_part = _asset_filesystem_part(authored)
            if not filesystem_part or Path(filesystem_part).is_absolute():
                continue
            if filesystem_part.startswith("anon:"):
                continue
            resolved = _resolve_asset_against_layer(layer, authored)
            if resolved:
                anchors.setdefault(_mapping_key(filesystem_part), set()).add(resolved)
    return anchors


def _merge_format_args(rewritten: str, original: str) -> str:
    """Preserve Sdf format arguments when a mapped filesystem path changes."""
    if _SDF_FORMAT_ARGS not in original:
        return rewritten
    _path, arguments = original.split(_SDF_FORMAT_ARGS, 1)
    return f"{rewritten}{_SDF_FORMAT_ARGS}{arguments}"


def _rewrite_asset_path(
    authored: str,
    *,
    staged_layer_path: Path,
    publish_mapping: dict[str, str],
    asset_remap: dict[str, str],
    source_anchors: dict[str, set[str]],
) -> str:
    """Return the published path for an authored USD asset value."""
    if not authored:
        return authored
    filesystem_part = _asset_filesystem_part(authored)
    if filesystem_part.startswith("anon:"):
        raise ValueError(
            f"Anonymous USD composition dependency is unsupported: {authored}"
        )

    remap = {_mapping_key(key): value for key, value in (asset_remap or {}).items()}
    authored_key = _mapping_key(filesystem_part)
    if authored_key in remap:
        return _merge_format_args(_usd_path(remap[authored_key]), authored)

    mapped = publish_mapping.get(authored_key)
    if mapped:
        return _merge_format_args(mapped, authored)

    if not Path(filesystem_part).is_absolute():
        staged_resolution = os.path.normpath(
            str(staged_layer_path.parent / filesystem_part)
        )
        mapped = publish_mapping.get(_mapping_key(staged_resolution))
        if mapped:
            return _merge_format_args(mapped, authored)

    if not _is_composition_path(authored):
        return authored

    if Path(filesystem_part).is_absolute():
        if not Path(filesystem_part).is_file():
            raise ValueError(f"USD composition dependency does not exist: {authored}")
        return authored

    candidates = source_anchors.get(authored_key, set())
    if len(candidates) > 1:
        formatted = ", ".join(sorted(candidates))
        raise ValueError(
            f"USD composition dependency {authored!r} is ambiguous: {formatted}"
        )
    if candidates:
        resolved = next(iter(candidates))
        mapped = publish_mapping.get(_mapping_key(resolved))
        if mapped:
            return _merge_format_args(mapped, authored)
        if Path(resolved).is_file():
            return _merge_format_args(_usd_path(resolved), authored)
        raise ValueError(
            "USD composition dependency cannot be resolved on disk: "
            f"{authored} -> {resolved}"
        )

    staged_resolution = staged_layer_path.parent / filesystem_part
    if staged_resolution.is_file():
        return _merge_format_args(_usd_path(staged_resolution), authored)
    raise ValueError(
        f"Unable to resolve relative USD composition dependency: {authored}"
    )


def rewrite_staged_usd_layer(
    staged_layer_path: str | Path,
    *,
    publish_mapping: dict[str, str],
    asset_remap: dict[str, str] | None = None,
    source_stage: Any = None,
) -> Path:
    """Rewrite a staged USD layer atomically."""
    from pxr import Sdf, UsdUtils

    staged_path = Path(staged_layer_path)
    source_layer = Sdf.Layer.FindOrOpen(_usd_path(staged_path))
    if source_layer is None:
        raise ValueError(f"Failed to open staged USD layer: {staged_path}")

    source_anchors = build_source_composition_anchors(source_stage)
    copied_layer = Sdf.Layer.CreateAnonymous(f"ayon_finalize_{staged_path.name}")
    copied_layer.TransferContent(source_layer)

    def rewrite(authored: str) -> str:
        """Rewrite one asset path."""
        return _rewrite_asset_path(
            str(authored),
            staged_layer_path=staged_path,
            publish_mapping=publish_mapping,
            asset_remap=asset_remap or {},
            source_anchors=source_anchors,
        )

    UsdUtils.ModifyAssetPaths(copied_layer, rewrite)

    temporary_path = staged_path.with_name(
        f".{staged_path.stem}.ayon_finalize{staged_path.suffix}"
    )
    if temporary_path.exists():
        temporary_path.unlink()
    try:
        export_args = {}
        if staged_path.suffix.lower() == ".usd":
            format_id = str(source_layer.GetFileFormat().formatId or "")
            if format_id in {"usda", "usdc"}:
                export_args["format"] = format_id
        exported = copied_layer.Export(_usd_path(temporary_path), args=export_args)
        if exported is False or not temporary_path.is_file():
            raise RuntimeError(
                f"Failed to export finalized USD layer: {temporary_path}"
            )
        if temporary_path.stat().st_size <= 0:
            raise RuntimeError(f"Finalized USD layer is empty: {temporary_path}")
        verified = Sdf.Layer.FindOrOpen(_usd_path(temporary_path))
        if verified is None:
            raise RuntimeError(
                f"Failed to reopen finalized USD layer: {temporary_path}"
            )
        os.replace(temporary_path, staged_path)
    except Exception:
        if temporary_path.exists():
            temporary_path.unlink()
        raise
    return staged_path
