"""Shared Katana node, parameter, and metadata helpers."""

from __future__ import annotations

import json
import re
from contextlib import contextmanager
from typing import Any, Optional

_TIME = 0.0


def sanitize_node_name(value: str, default_name: str = "AYON_Node") -> str:
    """Return a Katana-safe non-empty node name.

    Args:
        value: Desired node name.
        default_name: Name returned when sanitization removes all characters.

    Returns:
        Sanitized node name.
    """
    sanitized = re.sub(r"[^A-Za-z0-9_]+", "_", value).strip("_")
    return sanitized or default_name


def ensure_group_parameter(node, parameter_path: str):
    """Create and return a nested Katana group parameter.

    Args:
        node: Katana node that owns the parameter.
        parameter_path: Dot-separated group parameter path.

    Returns:
        Katana group parameter.
    """
    parameter = node.getParameters()
    if not parameter_path:
        return parameter
    for part in parameter_path.split("."):
        child = parameter.getChild(part)
        if child is None:
            child = parameter.createChildGroup(part)
        parameter = child
    return parameter


def ensure_string_parameter(node, parameter_path: str, default_value: str = ""):
    """Create and return a nested Katana string parameter.

    Args:
        node: Katana node that owns the parameter.
        parameter_path: Dot-separated parameter path.
        default_value: Value used when creating the parameter.

    Returns:
        Katana string parameter.
    """
    parent_path, _, leaf_name = parameter_path.rpartition(".")
    parent = ensure_group_parameter(node, parent_path)
    parameter = parent.getChild(leaf_name)
    if parameter is None:
        parameter = parent.createChildString(leaf_name, default_value)
    return parameter


def ensure_number_parameter(node, parameter_path: str, default_value: float = 0.0):
    """Create and return a nested Katana number parameter.

    Args:
        node: Katana node that owns the parameter.
        parameter_path: Dot-separated parameter path.
        default_value: Value used when creating the parameter.

    Returns:
        Katana number parameter.
    """
    parent_path, _, leaf_name = parameter_path.rpartition(".")
    parent = ensure_group_parameter(node, parent_path)
    parameter = parent.getChild(leaf_name)
    if parameter is None:
        parameter = parent.createChildNumber(leaf_name, default_value)
    return parameter


def set_string_parameter(node, parameter_path: str, value: str) -> None:
    """Set a nested Katana string parameter."""
    ensure_string_parameter(node, parameter_path, value).setValue(value, _TIME)


def set_number_parameter(node, parameter_path: str, value: float) -> None:
    """Set a nested Katana number parameter."""
    ensure_number_parameter(node, parameter_path, value).setValue(value, _TIME)


def get_parameter_value(node, parameter_path: str, default=None):
    """Return a nested parameter value or a default."""
    parameter = node.getParameter(parameter_path)
    if parameter is None:
        return default
    try:
        return parameter.getValue(_TIME)
    except TypeError:
        return default


def get_string_parameter(
    node,
    parameter_path: str,
    default: Optional[str] = None,
) -> Optional[str]:
    """Return a non-empty string parameter value or a default."""
    value = get_parameter_value(node, parameter_path, default)
    return value if isinstance(value, str) and value else default


def write_json_parameter(
    node,
    parameter_path: str,
    data: dict[str, Any],
    skip_unchanged: bool = True,
) -> None:
    """Serialize dictionary metadata into a Katana string parameter.

    Args:
        node: Katana node that owns the parameter.
        parameter_path: Dot-separated parameter path.
        data: Dictionary to serialize.
        skip_unchanged: Avoid dirtying the scene when content is unchanged.
    """
    serialized_data = json.dumps(data, sort_keys=True)
    if skip_unchanged:
        current_value = get_parameter_value(node, parameter_path)
        if current_value == serialized_data:
            return
    ensure_string_parameter(node, parameter_path).setValue(serialized_data, _TIME)


def read_json_parameter(
    node,
    parameter_path: str,
) -> Optional[dict[str, Any]]:
    """Read dictionary metadata from a Katana string parameter."""
    raw_value = get_parameter_value(node, parameter_path)
    if not raw_value:
        return None
    try:
        data = json.loads(raw_value)
    except (TypeError, json.JSONDecodeError):
        return None
    return data if isinstance(data, dict) else None


def get_color_management_preferences() -> dict[str, str]:
    """Return Katana color management preferences."""
    from . import colorspace

    config_path = colorspace.get_ocio_config_path()
    scene_linear = colorspace.get_scene_linear_colorspace()
    if not config_path or not scene_linear:
        return {}
    return {"config": config_path, "colorspace": scene_linear}


@contextmanager
def maintained_selection():
    """Maintain selection during context.

    This restores the selected nodes after the context exits and ignores nodes
    that no longer exist.
    """
    from . import compat

    selected_nodes = compat.get_selected_nodes()
    try:
        yield
    finally:
        live_nodes = []
        for node in selected_nodes:
            try:
                if compat.get_node(node.getName()) is node:
                    live_nodes.append(node)
            except Exception:
                continue
        compat.set_selected_nodes(live_nodes)
