"""Persist AYON context on Katana's root node."""

from __future__ import annotations

import logging
from typing import Any, Optional

from ayon_core.pipeline.context_tools import get_current_task_entity
from Katana import NodegraphAPI

from . import instances, lib

_CONTEXT_PARAMETER = "user.ayon.context.data"
_CONTEXT_SCHEMA = "ayon:context-1.0"
_CONTEXT_KEYS = ("project_name", "folder_path", "task_name")

log = logging.getLogger("ayon_katana.context")


def get_current_context_data(host, data: Optional[dict[str, Any]] = None) -> dict:
    """Return the current AYON context, optionally updated by event data.

    Args:
        host: Installed AYON Katana host.
        data: Optional context fields supplied by an AYON lifecycle event.

    Returns:
        Canonical project, folder, and task context data.
    """
    try:
        host_context = host.get_current_context()
    except KeyError:
        log.debug("AYON context is unavailable in the current Katana session.")
        host_context = {}
    context_data = {
        key: value for key, value in host_context.items() if key in _CONTEXT_KEYS
    }
    if data:
        context_data.update(
            {
                key: value
                for key, value in data.items()
                if key in _CONTEXT_KEYS and value is not None
            }
        )
    return context_data


def update_embedded_context(
    host,
    data: Optional[dict[str, Any]] = None,
) -> dict:
    """Persist the active AYON context in the current Katana project.

    Args:
        host: Installed AYON Katana host.
        data: Optional context fields supplied by an AYON lifecycle event.

    Returns:
        Context data written to the Katana root node.
    """
    context_data = get_current_context_data(host, data)
    if context_data:
        host.update_context_data(context_data)
    return context_data


def get_current_task_type() -> Optional[str]:
    """Return the active AYON task type when it can be resolved."""
    task_entity = get_current_task_entity(fields={"taskType"})
    if task_entity is None:
        return None
    return task_entity.get("taskType")


def _get_current_task_entity() -> Optional[dict[str, Any]]:
    """Return task attributes required for safe Katana project settings."""
    return get_current_task_entity(fields={"attrib"})


def _frame_range_from_task(
    task_entity: dict[str, Any],
) -> Optional[tuple[float, float]]:
    """Return task frame range including configured handles.

    Args:
        task_entity: AYON task entity carrying ``attrib`` data.

    Returns:
        Start and end frame, or ``None`` when the task is not configured with
        a valid range.
    """
    attributes = task_entity.get("attrib") or {}
    frame_start = attributes.get("frameStart")
    frame_end = attributes.get("frameEnd")
    if frame_start is None or frame_end is None:
        return None

    try:
        start = float(frame_start) - float(attributes.get("handleStart") or 0)
        end = float(frame_end) + float(attributes.get("handleEnd") or 0)
    except (TypeError, ValueError):
        log.warning("Skipping Katana frame range with invalid task attributes.")
        return None

    if start >= end:
        log.warning(
            "Skipping Katana frame range because start %s is not before end %s.",
            start,
            end,
        )
        return None
    return start, end


def apply_frame_range(task_entity: dict[str, Any]) -> bool:
    """Apply a task frame range and place Katana on its first frame.

    The order handles a target range that does not overlap the existing
    Katana range. Katana requires ``inTime < outTime`` for every individual
    setter call.

    Args:
        task_entity: AYON task entity carrying frame and handle attributes.

    Returns:
        ``True`` when a valid frame range was applied.
    """
    frame_range = _frame_range_from_task(task_entity)
    if frame_range is None:
        return False
    frame_start, frame_end = frame_range

    current_in_time = NodegraphAPI.GetInTime()
    if frame_end > current_in_time:
        NodegraphAPI.SetOutTime(frame_end)
    NodegraphAPI.SetInTime(frame_start)
    NodegraphAPI.SetOutTime(frame_end)
    NodegraphAPI.SetCurrentTime(frame_start)
    return True


def apply_current_frame_range() -> bool:
    """Apply the active AYON task range without changing Katana FPS.

    Returns:
        ``True`` when the active task supplied a valid frame range.
    """
    try:
        task_entity = _get_current_task_entity()
    except Exception:
        log.exception("Could not resolve the active AYON task frame range.")
        return False
    if task_entity is None:
        log.warning("Cannot set Katana frame range without an active AYON task.")
        return False
    return apply_frame_range(task_entity)


def update_instance_context_metadata(folder_path: str, task_name: str) -> int:
    """Persist a new folder and task on existing publish instances.

    Args:
        folder_path: Target AYON folder path.
        task_name: Target AYON task name.

    Returns:
        Number of node-backed or workfile instances updated.
    """
    updated_count = 0
    for node, instance_data in instances.iter_instances():
        output = dict(instance_data)
        changed = False
        if output.get("folderPath") and output["folderPath"] != folder_path:
            output["folderPath"] = folder_path
            changed = True
        if output.get("task") and output["task"] != task_name:
            output["task"] = task_name
            changed = True
        if changed:
            instances.imprint(node, output)
            updated_count += 1

    workfile_data = get_workfile_instance_data()
    if workfile_data:
        changed = False
        if workfile_data.get("folderPath") != folder_path:
            workfile_data["folderPath"] = folder_path
            changed = True
        if workfile_data.get("task") != task_name:
            workfile_data["task"] = task_name
            changed = True
        if changed:
            set_workfile_instance_data(workfile_data)
            updated_count += 1
    return updated_count


def log_fps_limitation(task_entity: Optional[dict[str, Any]] = None) -> None:
    """Report that Katana has no authoritative project FPS setter.

    Real Katana 8.0v1 and 9.0v1 probes expose frame-range and current-time
    APIs but no FPS getter or setter. ``timeIncrement`` is documented as the
    timeline navigation increment, not a frame-rate setting, so it must not
    be repurposed as an FPS compatibility shim.

    Args:
        task_entity: Optional task entity used only to include requested FPS
            in the log message.
    """
    fps = None
    if task_entity is not None:
        fps = (task_entity.get("attrib") or {}).get("fps")
    if fps is None:
        log.warning(
            "Katana 8/9 expose no authoritative project FPS setter; "
            "leaving scene FPS unchanged."
        )
        return
    log.warning(
        "Katana 8/9 expose no authoritative project FPS setter; "
        "leaving scene FPS unchanged (AYON task requests %s FPS).",
        fps,
    )


def apply_context_settings(
    host,
    data: Optional[dict[str, Any]] = None,
) -> dict:
    """Apply the safe Katana subset of AYON context project settings.

    Embedded AYON context and task frame range/current frame are updated in
    one place for new scenes and task changes. Katana 8/9 cannot apply AYON
    FPS without a non-authoritative workaround, and its ``resolution``
    project parameter is a renderer-independent preset name rather than a
    width/height project setting. Neither setting is mutated here.

    Args:
        host: Installed AYON Katana host.
        data: Optional context fields supplied by an AYON lifecycle event.

    Returns:
        Context data persisted on the Katana root node.
    """
    context_data = update_embedded_context(host, data)
    if not all(
        context_data.get(key) for key in ("project_name", "folder_path", "task_name")
    ):
        log.debug("Skipping Katana timing without a complete AYON context.")
        return context_data
    try:
        task_entity = _get_current_task_entity()
    except Exception:
        log.exception("Could not resolve the active AYON task for Katana timing.")
        return context_data

    if task_entity is None:
        log.debug("Skipping Katana timing without an active AYON task.")
        return context_data

    apply_frame_range(task_entity)
    log_fps_limitation(task_entity)
    return context_data


def get_context_data() -> dict[str, Any]:
    """Read AYON context data from the Katana root node."""
    data = lib.read_json_parameter(
        NodegraphAPI.GetRootNode(),
        _CONTEXT_PARAMETER,
    )
    return data or {}


def _write_context_data(context_data: dict[str, Any]) -> None:
    """Write complete AYON context data to Katana's root node."""
    output = dict(context_data)
    output.setdefault("schema", _CONTEXT_SCHEMA)
    lib.write_json_parameter(
        NodegraphAPI.GetRootNode(),
        _CONTEXT_PARAMETER,
        output,
    )


def update_context_data(data: dict[str, Any], _changes: Optional[Any] = None) -> None:
    """Write AYON context data to the Katana root node.

    Workfile creator data is preserved when AYON updates the project context.

    Args:
        data: Complete context data.
        _changes: Optional AYON change-tracking object. ``data`` already contains
            the complete new context, so the change details are informational.
    """
    context_data = get_context_data()
    context_data.update(data)
    _write_context_data(context_data)


def get_workfile_instance_data() -> dict[str, Any]:
    """Return persisted workfile creator data."""
    workfile_data = get_context_data().get("workfile")
    return dict(workfile_data) if isinstance(workfile_data, dict) else {}


def set_workfile_instance_data(data: dict[str, Any]) -> None:
    """Persist workfile creator data without replacing project context."""
    context_data = get_context_data()
    context_data["workfile"] = dict(data)
    _write_context_data(context_data)
