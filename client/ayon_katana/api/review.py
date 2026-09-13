"""Katana Viewer review-sequence capture helpers."""

from __future__ import annotations

from contextlib import suppress
from pathlib import Path
from typing import Any

from . import thumbnail


def frame_numbers(frame_start: int, frame_end: int, frame_step: int) -> tuple[int, ...]:
    """Return an inclusive validated review frame sequence.

    Args:
        frame_start: First frame to capture.
        frame_end: Last frame to capture.
        frame_step: Positive frame increment.

    Returns:
        Inclusive frame numbers.

    Raises:
        ValueError: The range or step is invalid.
    """
    if frame_end < frame_start:
        raise ValueError(
            f"Review frame end {frame_end} is before frame start {frame_start}."
        )
    if frame_step < 1:
        raise ValueError("Review frame step must be greater than zero.")
    return tuple(range(frame_start, frame_end + 1, frame_step))


def capture_viewer_sequence(
    viewer_widget: Any,
    staging_dir: Path,
    product_name: str,
    frame_start: int,
    frame_end: int,
    frame_step: int,
    *,
    frame_padding: int = 4,
) -> list[str]:
    """Capture the visible Viewer over a frame range as a PNG sequence.

    The active Katana frame is restored even when capture fails. Files created
    by a failed partial capture are removed before the error is re-raised.

    Args:
        viewer_widget: Selected Katana Viewer Qt widget.
        staging_dir: Destination directory.
        product_name: Prefix used for captured filenames.
        frame_start: First frame, including handles when desired.
        frame_end: Last frame, including handles when desired.
        frame_step: Positive frame increment.
        frame_padding: Minimum frame-number padding.

    Returns:
        Captured filenames relative to ``staging_dir``.
    """
    if frame_padding < 1:
        raise ValueError("Review frame padding must be greater than zero.")
    frames = frame_numbers(frame_start, frame_end, frame_step)

    from Katana import NodegraphAPI
    from qtpy import QtWidgets

    staging_dir.mkdir(parents=True, exist_ok=True)
    original_frame = NodegraphAPI.GetCurrentTime()
    created_paths: list[Path] = []
    application = QtWidgets.QApplication.instance()
    try:
        for frame in frames:
            NodegraphAPI.SetCurrentTime(frame)
            if application is not None:
                application.processEvents()

            filename = f"{product_name}.{frame:0{frame_padding}d}.png"
            output_path = staging_dir / filename
            thumbnail.capture_viewer_image(viewer_widget, output_path)
            created_paths.append(output_path)
    except Exception:
        for path in created_paths:
            with suppress(OSError):
                path.unlink()
        raise
    finally:
        NodegraphAPI.SetCurrentTime(original_frame)
        if application is not None:
            application.processEvents()

    return [path.name for path in created_paths]
