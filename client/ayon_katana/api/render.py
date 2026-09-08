"""Katana render-instance graph and output helpers."""

from __future__ import annotations

import os
import sys
import xml.etree.ElementTree as element_tree
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from Katana import NodegraphAPI, RenderingAPI

from . import lib

_ROLE_PARAMETER = "user.ayon.render.role"
_OUTPUT_PATH_PARAMETER = "user.ayon.render.output_path"
_RENDER_ROLE = "render"
_SETTINGS_ROLE = "settings"
_OUTPUT_ROLE = "output"
_PRIMARY_OUTPUT_ROLE = "output.primary"
_TIME = 0.0
_INTERNAL_RENDERERS = {"profilingMockRenderer", "usd"}
_MAIN_OUTPUT_NAMES = {"beauty", "main", "primary", "rgba"}
_RENDERER_PARAMETER = "args.renderSettings.renderer"
_CAMERA_PARAMETER = "args.renderSettings.cameraName"
_RESOLUTION_PARAMETER = "args.renderSettings.resolution"
_RESOLUTION_RESOURCE = Path("plugins/Resources/Core/Resolutions")


def _is_main_output(name: str, channel: str) -> bool:
    """Return whether an output represents the primary beauty product."""
    return any(
        value.strip().casefold() in _MAIN_OUTPUT_NAMES
        for value in (name, channel)
        if value.strip()
    )


@dataclass(frozen=True)
class RenderOutputDefinition:
    """Describe one enabled Katana render output."""

    node_name: str
    name: str
    path: str
    extension: str
    channel: str
    enabled: bool

    @property
    def aov_identifier(self) -> str:
        """Return the AOV key used by AYON farm integration."""
        if _is_main_output(self.name, self.channel):
            return ""
        for candidate in (self.channel, self.name):
            normalized = candidate.strip()
            if normalized:
                return normalized
        return ""


@dataclass(frozen=True)
class RenderFrameRange:
    """Describe the effective native Katana frame range."""

    start: int
    end: int
    step: int
    source: str


@dataclass(frozen=True)
class RenderSettingsValues:
    """Describe the effective settings authored by a RenderSettings node."""

    renderer: str
    camera: str
    resolution_name: str


@dataclass(frozen=True)
class RenderResolution:
    """Describe a named Katana resolution preset."""

    name: str
    width: int
    height: int
    pixel_aspect: float


def _katana_executable_name() -> str:
    """Return the platform-native Katana batch executable name."""
    if sys.platform == "win32":
        return "katanaBin.exe"
    return "katanaBin"


def get_katana_executable() -> Path:
    """Return the Katana executable used by the current AYON launch."""
    candidates = []
    katana_root = os.environ.get("KATANA_ROOT")
    if katana_root:
        candidates.append(Path(katana_root) / "bin" / _katana_executable_name())

    current_executable = Path(sys.executable)
    if "katana" in current_executable.name.casefold():
        candidates.append(current_executable)

    app_executable = os.environ.get("AYON_APP_EXECUTABLE")
    if app_executable:
        candidates.append(Path(app_executable))

    for candidate in candidates:
        if candidate.is_file():
            return candidate
    raise RuntimeError("Could not resolve the Katana executable.")


def get_registered_renderers(include_internal: bool = False) -> list[str]:
    """Return renderer IDs registered in the current Katana process.

    Args:
        include_internal: Include Katana's profiling and USD helper renderers.

    Returns:
        Sorted renderer identifiers.
    """
    try:
        renderer_names = RenderingAPI.RenderPlugins.GetRendererPluginNames()
    except Exception:
        return []
    output = sorted({str(name) for name in renderer_names if name})
    if include_internal:
        return output
    return [name for name in output if name not in _INTERNAL_RENDERERS]


def get_default_renderer(preferred: Optional[str] = None) -> str:
    """Return the preferred registered pixel renderer.

    Args:
        preferred: Optional project-settings override.

    Returns:
        Preferred renderer identifier, or an empty string when none are loaded.
    """
    registered_renderers = get_registered_renderers()
    for candidate in (preferred, os.environ.get("DEFAULT_RENDERER")):
        if candidate and candidate in registered_renderers:
            return candidate
    return ""


def is_renderer_registered(renderer_name: str) -> bool:
    """Return whether a pixel renderer is registered in Katana."""
    return renderer_name in get_registered_renderers()


def _set_string_attr(node, parameter_path: str, value: str) -> None:
    """Set a Katana attribute-style string parameter group."""
    lib.set_number_parameter(node, f"{parameter_path}.enable", 1)
    lib.set_string_parameter(node, f"{parameter_path}.value", value)
    lib.set_string_parameter(node, f"{parameter_path}.type", "StringAttr")


def _set_number_attr(node, parameter_path: str, value: float) -> None:
    """Set a Katana attribute-style number parameter group."""
    lib.set_number_parameter(node, f"{parameter_path}.enable", 1)
    lib.set_number_parameter(node, f"{parameter_path}.value", value)
    lib.set_string_parameter(node, f"{parameter_path}.type", "IntAttr")


def _set_optional_string_attr(node, parameter_path: str, value: str) -> None:
    """Set or disable an optional Katana string attribute group."""
    if value:
        _set_string_attr(node, parameter_path, value)
        return

    enable_parameter = node.getParameter(f"{parameter_path}.enable")
    if enable_parameter is not None:
        enable_parameter.setValue(0, _TIME)
    value_parameter = node.getParameter(f"{parameter_path}.value")
    if value_parameter is not None:
        value_parameter.setValue("", _TIME)


def set_node_role(node, role: str) -> None:
    """Tag a child node with its role in an AYON render graph."""
    lib.set_string_parameter(node, _ROLE_PARAMETER, role)


def get_node_by_role(instance_node, role: str):
    """Return a direct child with a render graph role."""
    for child in instance_node.getChildren():
        if lib.get_string_parameter(child, _ROLE_PARAMETER) == role:
            return child
    return None


def set_output_path(instance_node, output_path: str) -> None:
    """Persist the expected render output path on the instance Group."""
    lib.set_string_parameter(instance_node, _OUTPUT_PATH_PARAMETER, output_path)


def get_output_path(instance_node) -> Optional[str]:
    """Return the persisted primary render output path."""
    return lib.get_string_parameter(instance_node, _OUTPUT_PATH_PARAMETER)


def _parameter_value(node, parameter_path: str, default=None):
    """Return a Katana parameter value or a default when unavailable."""
    parameter = node.getParameter(parameter_path)
    if parameter is None:
        return default
    try:
        return parameter.getValue(_TIME)
    except Exception:
        return default


def _is_enabled(value) -> bool:
    """Return whether a Katana enable parameter represents an enabled value."""
    if isinstance(value, str):
        return value.casefold() in {"yes", "true", "1"}
    return bool(value)


def _get_enabled_string_setting(settings_node, parameter_path: str) -> str:
    """Read an explicitly authored string setting from RenderSettings.

    Katana exposes UI defaults even when an attribute is disabled.  Disabled
    attributes are inherited from the input scene graph and must not be
    reported as locally authored render settings.
    """
    enabled = _parameter_value(settings_node, f"{parameter_path}.enable", 0)
    if not _is_enabled(enabled):
        return ""
    value = _parameter_value(settings_node, f"{parameter_path}.value", "")
    return str(value or "").strip()


def get_project_frame_range() -> tuple[int, int]:
    """Return the native project timeline in and out frames."""
    root_node = NodegraphAPI.GetRootNode()
    start = _parameter_value(root_node, "inTime")
    end = _parameter_value(root_node, "outTime")
    if start is None or end is None:
        raise RuntimeError("Katana project timeline has no inTime/outTime values.")
    return int(start), int(end)


def get_project_frame_step() -> int:
    """Return Katana's native project timeline increment."""
    root_node = NodegraphAPI.GetRootNode()
    step = _parameter_value(root_node, "timeIncrement")
    if step is None:
        raise RuntimeError("Katana project timeline has no timeIncrement value.")
    return int(step)


def set_project_frame_step(frame_step: int) -> None:
    """Set Katana's native project timeline increment for a new render graph."""
    root_node = NodegraphAPI.GetRootNode()
    parameter = root_node.getParameter("timeIncrement")
    if parameter is None:
        raise RuntimeError("Katana project timeline has no timeIncrement parameter.")
    parameter.setValue(int(frame_step), _TIME)


def get_render_frame_range(render_node) -> RenderFrameRange:
    """Return the active native Render range and project frame increment.

    Katana's Render node explicitly owns only the optional farm range.  When
    that range is disabled, the project timeline is the native source of
    truth.  Frame stepping is represented by the project ``timeIncrement``
    parameter in both cases.
    """
    active_range = _parameter_value(render_node, "farmSettings.setActiveFrameRange")
    if _is_enabled(active_range):
        start = _parameter_value(render_node, "farmSettings.activeFrameRange.start")
        end = _parameter_value(render_node, "farmSettings.activeFrameRange.end")
        if start is None or end is None:
            raise RuntimeError("Katana Render active frame range is incomplete.")
        source = "render"
    else:
        start, end = get_project_frame_range()
        source = "project"
    return RenderFrameRange(
        start=int(start),
        end=int(end),
        step=get_project_frame_step(),
        source=source,
    )


def get_effective_render_settings(settings_node) -> RenderSettingsValues:
    """Return renderer, camera, and resolution from native Katana settings."""
    resolution_name = _get_enabled_string_setting(
        settings_node,
        _RESOLUTION_PARAMETER,
    )
    if not resolution_name:
        root_node = NodegraphAPI.GetRootNode()
        resolution_name = str(_parameter_value(root_node, "resolution", "") or "")
    return RenderSettingsValues(
        renderer=_get_enabled_string_setting(settings_node, _RENDERER_PARAMETER),
        camera=_get_enabled_string_setting(settings_node, _CAMERA_PARAMETER),
        resolution_name=resolution_name.strip(),
    )


def _resolution_resource_paths() -> list[Path]:
    """Return the authoritative Katana resolution resource files."""
    katana_root = os.environ.get("KATANA_ROOT")
    if not katana_root:
        raise RuntimeError("KATANA_ROOT is required to resolve Katana resolutions.")
    resolution_directory = Path(katana_root) / _RESOLUTION_RESOURCE
    resolution_paths = sorted(resolution_directory.glob("*.xml"))
    if not resolution_paths:
        raise RuntimeError(
            f"Katana resolution resources were not found under {resolution_directory}."
        )
    return resolution_paths


def get_resolution(name: str) -> RenderResolution:
    """Resolve an effective native Katana resolution preset by name."""
    if not name:
        raise RuntimeError("Katana RenderSettings has no effective resolution.")
    for resolution_path in _resolution_resource_paths():
        root = element_tree.parse(resolution_path).getroot()
        for format_element in root.findall(".//format"):
            if format_element.get("name") != name:
                continue
            try:
                return RenderResolution(
                    name=name,
                    width=int(format_element.attrib["width"]),
                    height=int(format_element.attrib["height"]),
                    pixel_aspect=float(format_element.attrib["pixelAspect"]),
                )
            except (KeyError, TypeError, ValueError) as exc:
                raise RuntimeError(
                    f"Katana resolution preset {name!r} is malformed in "
                    f"{resolution_path}."
                ) from exc
    raise RuntimeError(f"Katana resolution preset {name!r} was not found.")


def get_scenegraph_location_type(render_node, location_path: str) -> str:
    """Return a cooked scenegraph location type from the native Render node."""
    if not location_path:
        return ""
    import Nodes3DAPI
    from Katana import FnGeolib

    runtime = FnGeolib.GetRegisteredRuntimeInstance()
    transaction = runtime.createTransaction()
    client = transaction.createClient()
    operation = Nodes3DAPI.GetOp(transaction, render_node)
    transaction.setClientOp(client, operation)
    runtime.commit(transaction)
    location = client.cookLocation(location_path)
    if not location:
        return ""
    attributes = location.getAttrs()
    type_attribute = attributes.getChildByName("type")
    if type_attribute is None:
        return ""
    return str(type_attribute.getValue() or "")


def _output_attribute_value(output_node, attribute_path: str, default=""):
    """Read an attribute value from a RenderOutputDefine node."""
    return _parameter_value(
        output_node,
        f"args.renderSettings.outputs.outputName.{attribute_path}.value",
        default,
    )


def _node_is_enabled(node) -> bool:
    """Return whether a Katana node is active in the graph."""
    is_bypassed = getattr(node, "isBypassed", None)
    if callable(is_bypassed):
        return not bool(is_bypassed())
    return True


def get_output_definition(output_node) -> RenderOutputDefinition:
    """Return normalized render-product data from a Katana output node."""
    output_name = str(_parameter_value(output_node, "outputName", "") or "").strip()
    output_path = str(
        _output_attribute_value(
            output_node,
            "locationSettings.renderLocation",
            "",
        )
        or ""
    ).strip()
    extension = (
        str(
            _output_attribute_value(
                output_node,
                "rendererSettings.fileExtension",
                "",
            )
            or ""
        )
        .strip()
        .lstrip(".")
    )
    if not extension and output_path:
        extension = Path(output_path).suffix.lstrip(".")
    channel = str(
        _output_attribute_value(
            output_node,
            "rendererSettings.channel",
            "",
        )
        or ""
    ).strip()
    return RenderOutputDefinition(
        node_name=output_node.getName(),
        name=output_name,
        path=output_path,
        extension=extension,
        channel=channel,
        enabled=_node_is_enabled(output_node),
    )


def get_output_nodes(instance_node) -> list:
    """Return all direct RenderOutputDefine children in graph order."""
    output_nodes = [
        child
        for child in instance_node.getChildren()
        if child.getType() == "RenderOutputDefine"
    ]

    def sort_key(node):
        """Return graph position and name for deterministic output ordering."""
        try:
            position = NodegraphAPI.GetNodePosition(node)
            return float(position[0]), node.getName()
        except Exception:
            return 0.0, node.getName()

    return sorted(output_nodes, key=sort_key)


def get_output_definitions(
    instance_node, include_disabled: bool = False
) -> list[RenderOutputDefinition]:
    """Return render products defined by the native Katana graph."""
    definitions = [
        get_output_definition(output_node)
        for output_node in get_output_nodes(instance_node)
    ]
    if include_disabled:
        return definitions
    return [definition for definition in definitions if definition.enabled]


def configure_output_node(
    output_node,
    output_name: str,
    output_path: str,
    extension: str,
    channel: str,
) -> None:
    """Configure a renderer-neutral file output definition.

    Args:
        output_node: Katana ``RenderOutputDefine`` node.
        output_name: Render output name.
        output_path: Output path containing Katana ``#`` frame padding.
        extension: File extension without a leading dot.
        channel: Renderer channel or AOV name.
    """
    output_node.getParameter("outputName").setValue(output_name, _TIME)
    lib.set_string_parameter(output_node, "args.__lastLocationType", "file")
    base_path = "args.renderSettings.outputs.outputName"
    is_main_output = _is_main_output(output_name, channel)
    _set_string_attr(
        output_node,
        f"{base_path}.rendererSettings.fileExtension",
        extension,
    )
    _set_string_attr(output_node, f"{base_path}.rendererSettings.channel", channel)
    _set_number_attr(
        output_node,
        f"{base_path}.rendererSettings.withAlpha",
        int(is_main_output),
    )
    _set_string_attr(output_node, f"{base_path}.locationType", "file")
    _set_string_attr(
        output_node,
        f"{base_path}.locationSettings.renderLocation",
        output_path,
    )


def configure_render_settings(
    settings_node,
    renderer: str,
    camera: str,
    resolution: str = "",
) -> None:
    """Configure explicit native renderer, camera, and resolution settings."""
    _set_optional_string_attr(settings_node, _RENDERER_PARAMETER, renderer)
    _set_optional_string_attr(settings_node, _CAMERA_PARAMETER, camera)
    _set_optional_string_attr(settings_node, _RESOLUTION_PARAMETER, resolution)


def _connect_to_target(source_port, target_port) -> None:
    """Connect one source to a target, replacing previous target inputs."""
    for connected_port in list(target_port.getConnectedPorts()):
        target_port.disconnect(connected_port)
    source_port.connect(target_port)


def reconnect_render_graph(instance_node) -> None:
    """Connect settings, all render outputs, the Group return, and Render node."""
    settings_node = get_settings_node(instance_node)
    render_node = get_render_node(instance_node)
    output_nodes = get_output_nodes(instance_node)
    if settings_node is None or render_node is None or not output_nodes:
        raise RuntimeError(
            f"Render instance {instance_node.getName()!r} has an incomplete graph."
        )

    _connect_to_target(
        instance_node.getSendPort("in"),
        settings_node.getInputPort("input"),
    )
    source_port = settings_node.getOutputPort("out")
    for output_node in output_nodes:
        _connect_to_target(source_port, output_node.getInputPort("input"))
        source_port = output_node.getOutputPort("out")
    _connect_to_target(source_port, instance_node.getReturnPort("out"))
    _connect_to_target(source_port, render_node.getInputPort("input"))


def create_output_node(
    instance_node,
    output_name: str,
    output_path: str,
    extension: str,
    channel: str,
    primary: bool = False,
):
    """Create, configure, and connect one native Katana render output."""
    existing_output_count = len(get_output_nodes(instance_node))
    output_node = NodegraphAPI.CreateNode("RenderOutputDefine", instance_node)
    node_suffix = lib.sanitize_node_name(output_name, "Output")
    output_node.setName(f"AYON_RenderOutput_{node_suffix}")
    set_node_role(output_node, _PRIMARY_OUTPUT_ROLE if primary else _OUTPUT_ROLE)
    configure_output_node(
        output_node,
        output_name=output_name,
        output_path=output_path,
        extension=extension,
        channel=channel,
    )
    NodegraphAPI.SetNodePosition(
        output_node,
        (float(existing_output_count * 250), 0.0),
    )
    reconnect_render_graph(instance_node)
    return output_node


def update_render_graph(
    instance_node,
    product_name: str,
    output_name: str,
    output_path: str,
    extension: str,
    channel: str,
    renderer: str,
    camera: str,
    frame_start: int,
    frame_end: int,
    frame_step: int,
    resolution: str = "",
):
    """Synchronize persisted creator data into native Katana render nodes.

    Args:
        instance_node: Outer AYON render instance Group.
        product_name: AYON product name.
        output_name: Render output name.
        output_path: Expected output pattern.
        extension: File extension.
        channel: Render channel.
        renderer: Optional renderer identifier.
        camera: Optional scenegraph camera path.
        frame_start: First frame.
        frame_end: Last frame.
        frame_step: Native Katana project timeline increment.
        resolution: Optional named Katana resolution preset.

    Returns:
        Updated native ``Render`` node.
    """
    settings_node = get_settings_node(instance_node)
    output_node = get_output_node(instance_node)
    render_node = get_render_node(instance_node)
    if settings_node is None or output_node is None or render_node is None:
        raise RuntimeError(
            f"Render instance {instance_node.getName()!r} has an incomplete graph."
        )

    configure_render_settings(settings_node, renderer, camera, resolution)
    configure_output_node(
        output_node,
        output_name,
        output_path,
        extension,
        channel,
    )
    render_node.setName(f"AYON_{product_name}_Render")
    render_node.getParameter("passName").setValue(product_name, _TIME)
    render_node.getParameter("farmSettings.setActiveFrameRange").setValue("Yes", _TIME)
    render_node.getParameter("farmSettings.activeFrameRange.start").setValue(
        frame_start, _TIME
    )
    render_node.getParameter("farmSettings.activeFrameRange.end").setValue(
        frame_end, _TIME
    )
    set_project_frame_step(frame_step)
    set_output_path(instance_node, output_path)
    return render_node


def create_render_graph(
    instance_node,
    product_name: str,
    output_name: str,
    output_path: str,
    extension: str,
    channel: str,
    renderer: str,
    camera: str,
    frame_start: int,
    frame_end: int,
    frame_step: int,
    resolution: str = "",
):
    """Create the native Katana nodes owned by a render instance.

    Args:
        instance_node: Outer AYON instance Group.
        product_name: AYON product name.
        output_name: Render output name.
        output_path: Expected output pattern.
        extension: File extension.
        channel: Render channel.
        renderer: Optional renderer identifier.
        camera: Optional scenegraph camera path.
        frame_start: First frame.
        frame_end: Last frame.
        frame_step: Native Katana project timeline increment.
        resolution: Optional named Katana resolution preset.

    Returns:
        Created native ``Render`` node.
    """
    settings_node = NodegraphAPI.CreateNode("RenderSettings", instance_node)
    settings_node.setName("AYON_RenderSettings")
    set_node_role(settings_node, _SETTINGS_ROLE)

    render_node = NodegraphAPI.CreateNode("Render", instance_node)
    render_node.setName(f"AYON_{product_name}_Render")
    set_node_role(render_node, _RENDER_ROLE)

    output_node = create_output_node(
        instance_node,
        output_name=output_name,
        output_path=output_path,
        extension=extension,
        channel=channel,
        primary=True,
    )
    update_render_graph(
        instance_node=instance_node,
        product_name=product_name,
        output_name=output_name,
        output_path=output_path,
        extension=extension,
        channel=channel,
        renderer=renderer,
        camera=camera,
        frame_start=frame_start,
        frame_end=frame_end,
        frame_step=frame_step,
        resolution=resolution,
    )

    NodegraphAPI.SetNodePosition(settings_node, (-300.0, 0.0))
    NodegraphAPI.SetNodePosition(output_node, (0.0, 0.0))
    NodegraphAPI.SetNodePosition(render_node, (300.0, -100.0))
    return render_node


def get_render_node(instance_node):
    """Return the native Render child of an AYON render instance."""
    return get_node_by_role(instance_node, _RENDER_ROLE)


def get_settings_node(instance_node):
    """Return the native RenderSettings child."""
    return get_node_by_role(instance_node, _SETTINGS_ROLE)


def get_output_node(instance_node):
    """Return the creator-owned primary RenderOutputDefine child."""
    return get_node_by_role(instance_node, _PRIMARY_OUTPUT_ROLE)
