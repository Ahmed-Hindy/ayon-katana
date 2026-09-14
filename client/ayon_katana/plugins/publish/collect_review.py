"""Collect Katana Viewer Scene Review publish data."""

from __future__ import annotations

import math

import pyblish.api

from ayon_katana.api import plugin, render


def _whole_number(value, label: str) -> int:
    """Return a whole-number frame setting or raise a targeted error."""
    try:
        numeric = float(value)
    except (TypeError, ValueError) as exc:
        raise RuntimeError(f"AYON {label} is not a number: {value!r}.") from exc
    output = int(numeric)
    if numeric != output:
        raise RuntimeError(f"AYON {label} must be a whole number: {value!r}.")
    return output


def _task_frame_data(instance) -> tuple[int, int, int, int]:
    """Return cut range and handles, falling back to Katana's project range."""
    entity = instance.data.get("taskEntity") or instance.data.get("folderEntity")
    attributes = (entity or {}).get("attrib") or {}
    frame_start = attributes.get("frameStart")
    frame_end = attributes.get("frameEnd")
    if frame_start is None or frame_end is None:
        project_start, project_end = render.get_project_frame_range()
        return int(project_start), int(project_end), 0, 0

    return (
        _whole_number(frame_start, "frameStart"),
        _whole_number(frame_end, "frameEnd"),
        _whole_number(attributes.get("handleStart") or 0, "handleStart"),
        _whole_number(attributes.get("handleEnd") or 0, "handleEnd"),
    )


def _instance_fps(instance) -> float:
    """Resolve AYON task/context FPS required by Core's review extractor."""
    entity = instance.data.get("taskEntity") or instance.data.get("folderEntity")
    attributes = (entity or {}).get("attrib") or {}
    value = attributes.get("fps")
    if value is None:
        value = instance.data.get("fps")
    if value is None:
        value = instance.context.data.get("fps")
    try:
        fps = float(value)
    except (TypeError, ValueError) as exc:
        raise RuntimeError("Scene Review requires a valid AYON task FPS.") from exc
    if not math.isfinite(fps) or fps <= 0:
        raise RuntimeError("Scene Review requires a finite positive AYON task FPS.")
    return fps


class CollectReview(plugin.KatanaInstancePlugin):
    """Collect cut/handle range and FPS for a Katana Viewer review."""

    label = "Collect Scene Review"
    order = pyblish.api.CollectorOrder + 0.410
    families = ["katana.review"]

    def process(self, instance) -> None:
        """Normalize Scene Review data for capture and AYON Core review output."""
        frame_start, frame_end, handle_start, handle_end = _task_frame_data(instance)
        frame_start_handle = frame_start - handle_start
        frame_end_handle = frame_end + handle_end
        if frame_end_handle < frame_start_handle:
            raise RuntimeError(
                "Scene Review frame range is invalid after applying task handles."
            )

        instance.data.update(
            {
                "frameStart": frame_start,
                "frameEnd": frame_end,
                "handleStart": handle_start,
                "handleEnd": handle_end,
                "frameStartHandle": frame_start_handle,
                "frameEndHandle": frame_end_handle,
                "byFrameStep": 1,
                "fps": _instance_fps(instance),
                "review": True,
            }
        )
        families = instance.data.setdefault("families", [])
        for family in ("review", "katana.review"):
            if family not in families:
                families.append(family)
