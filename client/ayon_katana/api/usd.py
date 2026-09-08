"""Katana USD helpers."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Optional

import ayon_api

log = logging.getLogger("ayon_katana.usd")

USD_PRODUCT_BASE_TYPES = {
    "assembly",
    "camera",
    "layout",
    "look",
    "usd",
    "usdCamera",
}
USD_FILE_FORMATS = ("usd", "usda", "usdc")
USD_TIME_SAMPLE_MODES = (
    "Current Frame",
    "Frame Range",
    "Project Settings",
    "Defined Layer Metadata",
)
USD_EXPORT_METHODS = (
    "Keep Composition Arcs",
    "Flatten Sublayers, Keep References",
    "Flatten All",
)


def is_native_usd_node(node: Any) -> bool:
    """Return whether a Katana node produces native USD data.

    Katana tags native USD node types with the ``nativeusd`` flavor. Regular
    Geolib nodes can still be connected to ``UsdLayerExport`` at the port
    level, but the exporter cannot evaluate them as USD layers.

    Args:
        node: Katana node exposing ``getType``.

    Returns:
        Whether Katana registers the node type as native USD.
    """
    from Katana import NodegraphAPI

    return "nativeusd" in NodegraphAPI.GetNodeFlavors(node.getType())


def get_composed_usd_stage(source_node: Any) -> Any:
    """Return the composed USD stage for a native USD node.

    Args:
        source_node: Katana node with the ``nativeusd`` flavor.

    Returns:
        Katana's pxr/fnpxr stage object.

    Raises:
        ValueError: The source node is missing or is not a native USD node.
        RuntimeError: Katana cannot provide a valid composed USD stage.
    """
    if source_node is None:
        raise ValueError("A native USD source node is required.")

    try:
        node_name = source_node.getName()
        node_type = source_node.getType()
    except (AttributeError, TypeError) as exc:
        raise ValueError(
            "USD stage inspection requires a Katana node exposing getName() "
            "and getType()."
        ) from exc

    try:
        native_usd = is_native_usd_node(source_node)
    except Exception as exc:
        raise RuntimeError(
            f"Failed to inspect the USD node flavor for {node_name!r}."
        ) from exc
    if not native_usd:
        raise ValueError(
            f"Katana node {node_name!r} ({node_type}) is not a native USD node."
        )

    try:
        from Katana import NodesUsdAPI

        stage_handle = NodesUsdAPI.GetStage(source_node)
    except Exception as exc:
        raise RuntimeError(
            f"Katana could not create a USD stage handle for {node_name!r}."
        ) from exc
    if stage_handle is None:
        raise RuntimeError(f"Katana returned no USD stage handle for {node_name!r}.")

    try:
        stage = stage_handle.getUsdStage()
    except Exception as exc:
        raise RuntimeError(
            f"Katana could not compose the USD stage for {node_name!r}."
        ) from exc
    if stage is None:
        raise RuntimeError(f"Katana returned no composed USD stage for {node_name!r}.")
    return stage


def get_extracted_usd_layer_path(instance_data: dict[str, Any]) -> Path:
    """Return the single extracted USD layer path from publish instance data.

    Args:
        instance_data: AYON publish instance data containing representations.

    Returns:
        Path to the single staged USD layer.

    Raises:
        ValueError: No single-file USD representation is available.
    """
    usd_extensions = {"usd", "usda", "usdc", "usdlc", "usdnc"}
    candidates = []
    for representation in instance_data.get("representations") or []:
        extension = str(representation.get("ext") or "").lower().lstrip(".")
        if extension in usd_extensions:
            candidates.append(representation)

    if not candidates:
        raise ValueError("No extracted USD representation is available for validation.")
    if len(candidates) != 1:
        raise ValueError(
            "USD validation requires exactly one extracted USD representation; "
            f"found {len(candidates)}."
        )

    representation = candidates[0]
    files = representation.get("files")
    if isinstance(files, (list, tuple)):
        if len(files) != 1:
            raise ValueError(
                "USD validation requires exactly one extracted USD layer file."
            )
        files = files[0]
    if not files:
        raise ValueError(
            "The extracted USD representation does not contain a layer file."
        )

    staging_dir = representation.get("stagingDir") or instance_data.get("stagingDir")
    if not staging_dir:
        raise ValueError("The extracted USD representation has no staging directory.")
    return Path(staging_dir) / str(files)


def _rehydrate_usd_layer_export(node: Any) -> None:
    """Restore transient state omitted when Katana reopens the supertool.

    Katana 9 serializes the ``UsdLayerExport`` node graph but does not restore
    its private ``_layerDefineNode`` Python attribute. Its native ``write``
    method reads that attribute unconditionally. Rebuild only this transient
    reference from the optional ``define`` input without changing the scene.

    Args:
        node: Katana ``UsdLayerExport`` node.
    """
    if hasattr(node, "_layerDefineNode"):
        return

    define_node = None
    define_port = node.getInputPort("define")
    if define_port is not None:
        connected_ports = list(define_port.getConnectedPorts())
        if len(connected_ports) == 1:
            define_node = connected_ports[0].getNode()
    node._layerDefineNode = define_node


def _get_parameter(node: Any, name: str) -> Any:
    parameter = node.getParameter(name)
    if parameter is None:
        node_name = getattr(node, "getName", lambda: "<unknown>")()
        raise RuntimeError(
            f"Katana node {node_name!r} has no required parameter {name!r}."
        )
    return parameter


def configure_usd_layer_export(
    node: Any,
    *,
    file_format: str,
    time_samples: str,
    frame_start: Optional[float] = None,
    frame_end: Optional[float] = None,
    samples_per_frame: float = 1.0,
    export_method: str = "Keep Composition Arcs",
    output_path: Optional[str | Path] = None,
) -> None:
    """Configure Katana's ``UsdLayerExport`` node.

    Args:
        node: Katana ``UsdLayerExport`` node.
        file_format: One of ``usd``, ``usda``, or ``usdc``.
        time_samples: Katana time-sampling mode.
        frame_start: First frame when using ``Frame Range``.
        frame_end: Last frame when using ``Frame Range``.
        samples_per_frame: Positive number of time samples per frame.
        export_method: Katana layer composition method.
        output_path: Optional destination assigned to ``saveTo``.

    Raises:
        ValueError: A setting is unsupported or internally inconsistent.
        RuntimeError: A required parameter is unavailable.
    """
    normalized_format = str(file_format).lower().lstrip(".")
    if normalized_format not in USD_FILE_FORMATS:
        raise ValueError(f"Unsupported USD file format: {file_format!r}.")
    if time_samples not in USD_TIME_SAMPLE_MODES:
        raise ValueError(f"Unsupported USD time-sampling mode: {time_samples!r}.")
    if export_method not in USD_EXPORT_METHODS:
        raise ValueError(f"Unsupported USD export method: {export_method!r}.")
    if float(samples_per_frame) <= 0:
        raise ValueError("USD samples per frame must be greater than zero.")
    if time_samples == "Frame Range":
        if frame_start is None or frame_end is None:
            raise ValueError("USD Frame Range requires start and end frames.")
        if float(frame_end) < float(frame_start):
            raise ValueError(f"Invalid USD frame range: {frame_start}-{frame_end}.")

    _get_parameter(node, "usdFileFormat").setValue(normalized_format, 0.0)
    _get_parameter(node, "time.timeSamples").setValue(time_samples, 0.0)
    _get_parameter(node, "time.samplesPerFrame").setValue(float(samples_per_frame), 0.0)
    _get_parameter(node, "exportOptions.exportMethod").setValue(export_method, 0.0)
    if frame_start is not None:
        _get_parameter(node, "time.frameRange.i0").setValue(float(frame_start), 0.0)
    if frame_end is not None:
        _get_parameter(node, "time.frameRange.i1").setValue(float(frame_end), 0.0)
    if output_path is not None:
        _get_parameter(node, "saveTo").setValue(Path(output_path).as_posix(), 0.0)


def read_usd_layer_export_settings(node: Any) -> dict[str, Any]:
    """Read publish settings from a USD export node.

    Args:
        node: Katana ``UsdLayerExport`` node.

    Returns:
        Normalized export settings.
    """
    return {
        "file_format": str(_get_parameter(node, "usdFileFormat").getValue(0.0)).lower(),
        "time_samples": str(_get_parameter(node, "time.timeSamples").getValue(0.0)),
        "frame_start": float(_get_parameter(node, "time.frameRange.i0").getValue(0.0)),
        "frame_end": float(_get_parameter(node, "time.frameRange.i1").getValue(0.0)),
        "samples_per_frame": float(
            _get_parameter(node, "time.samplesPerFrame").getValue(0.0)
        ),
        "export_method": str(
            _get_parameter(node, "exportOptions.exportMethod").getValue(0.0)
        ),
    }


def export_usd_layer(node: Any, output_path: str | Path) -> Path:
    """Write a USD layer without leaving transient path changes.

    Katana's ``write`` method reports some failures by returning ``None``
    instead of raising. This helper treats both cases as publish failures and
    verifies that a non-empty file was produced.

    Args:
        node: Katana ``UsdLayerExport`` node.
        output_path: Final path in the publish staging directory.

    Returns:
        Output path.

    Raises:
        RuntimeError: Export fails or does not produce a usable file.
        ValueError: The output extension is not a supported USD format.
    """
    destination = Path(output_path)
    file_format = destination.suffix.lower().lstrip(".")
    if file_format not in USD_FILE_FORMATS:
        raise ValueError(
            f"USD output must end in {USD_FILE_FORMATS}, got {destination.name!r}."
        )
    destination.parent.mkdir(parents=True, exist_ok=True)

    save_parameter = _get_parameter(node, "saveTo")
    saved_to_parameter = node.getParameter("_savedTo")
    format_parameter = _get_parameter(node, "usdFileFormat")
    original_save_to = save_parameter.getValue(0.0)
    original_saved_to = (
        saved_to_parameter.getValue(0.0) if saved_to_parameter is not None else None
    )
    original_format = format_parameter.getValue(0.0)
    try:
        _rehydrate_usd_layer_export(node)
        save_parameter.setValue(destination.as_posix(), 0.0)
        format_parameter.setValue(file_format, 0.0)
        if destination.exists():
            destination.unlink()
        result = node.write()
        if result is None:
            raise RuntimeError("Katana UsdLayerExport returned no success result.")
        if not destination.is_file():
            raise RuntimeError(
                f"Katana UsdLayerExport did not create {destination.as_posix()!r}."
            )
        if destination.stat().st_size <= 0:
            raise RuntimeError(
                f"Katana UsdLayerExport created an empty file: {destination}."
            )
        return destination
    except Exception:
        if destination.exists():
            destination.unlink()
        raise
    finally:
        save_parameter.setValue(original_save_to, 0.0)
        format_parameter.setValue(original_format, 0.0)
        if saved_to_parameter is not None:
            saved_to_parameter.setValue(original_saved_to, 0.0)


def get_ayon_entity_uri_from_representation_context(context: dict) -> str:
    """Return the AYON URI for a representation context.

    Args:
        context: Loader representation context.

    Returns:
        AYON entity URI.

    Raises:
        RuntimeError: Unable to resolve to a single valid URI.
    """
    project_name = context["project"]["name"]
    representation_id = context["representation"]["id"]
    response = ayon_api.post(
        f"projects/{project_name}/uris",
        entityType="representation",
        ids=[representation_id],
    )
    if response.status_code != 200:
        raise RuntimeError(
            f"Unable to resolve AYON entity URI for {project_name!r} "
            f"representation {representation_id!r}: {response.text}"
        )
    uris = response.data.get("uris") or []
    if len(uris) != 1 or not uris[0].get("uri"):
        raise RuntimeError(
            f"Unable to resolve AYON entity URI for {project_name!r} "
            f"representation {representation_id!r} to one URI: "
            f"{response.data!r}"
        )
    return uris[0]["uri"]


def clear_resolver_cache() -> dict[str, int | bool]:
    """Clear the optional AYON USD Resolver and flush native UsdIn stages.

    Returns:
        Resolver availability, clear state, and successfully flushed node count.

    Notes:
        The resolver is an optional external component. Its absence is a
        warning and a no-op; this addon never installs it implicitly.
    """
    try:
        from usdAssetResolver import AyonUsdResolver
    except ImportError:
        log.warning(
            "AYON USD Resolver is not installed; resolver cache was not cleared."
        )
        return {
            "resolver_available": False,
            "cache_cleared": False,
            "flushed_nodes": 0,
        }

    from Katana import NodegraphAPI

    AyonUsdResolver.ResolverContext().ClearCache()
    graph_state = NodegraphAPI.GetCurrentGraphState()
    flushed_nodes = 0
    for node in NodegraphAPI.GetAllNodesByType("UsdIn"):
        flush_stage = getattr(node, "flushStage", None)
        if flush_stage is None:
            log.warning(
                "UsdIn node %s has no native flushStage method.", node.getName()
            )
            continue
        try:
            flush_stage(node, graph_state)
        except Exception:
            log.warning(
                "Failed to flush UsdIn stage for %s.",
                node.getName(),
                exc_info=True,
            )
            continue
        flushed_nodes += 1

    return {
        "resolver_available": True,
        "cache_cleared": True,
        "flushed_nodes": flushed_nodes,
    }
