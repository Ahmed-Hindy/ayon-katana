"""Katana Viewer review-sequence capture helpers."""

from __future__ import annotations

from contextlib import suppress
from pathlib import Path
from typing import Any

_VIEWPORT_SYNC_PASSES = 2


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


def _select_review_viewport(viewer_widget: Any) -> Any:
    """Return the only visible Katana viewport suitable for review capture."""
    candidates = []
    try:
        delegate_count = int(viewer_widget.getNumberOfViewerDelegates())
        for delegate_index in range(delegate_count):
            delegate = viewer_widget.getViewerDelegateByIndex(delegate_index)
            if delegate is None:
                continue
            for viewport in viewer_widget.getViewports(delegate):
                viewport_widget = viewer_widget.getViewportWidget(viewport, delegate)
                if viewport_widget is None:
                    continue
                if not callable(getattr(viewport_widget, "grabFramebuffer", None)):
                    continue
                if not bool(viewport_widget.isVisible()):
                    continue
                if (
                    int(viewport_widget.width()) < 1
                    or int(viewport_widget.height()) < 1
                ):
                    continue
                candidates.append(viewport_widget)
    except Exception as exc:
        raise RuntimeError(
            "Scene Review cannot inspect Katana Viewer viewports."
        ) from exc

    if len(candidates) != 1:
        raise RuntimeError(
            "Scene Review requires exactly one visible capture viewport; "
            f"found {len(candidates)}."
        )
    return candidates[0]


def _synchronize_viewport(viewport_widget: Any) -> None:
    """Flush Katana updates and synchronously redraw the review viewport."""
    from Katana import Utils
    from qtpy import QtWidgets

    application = QtWidgets.QApplication.instance()
    # One repaint can still show the previous Hydra frame. Katana 8 and 9 both
    # require a second flush/repaint cycle before review pixels are current.
    for _ in range(_VIEWPORT_SYNC_PASSES):
        Utils.EventModule.ProcessAllEvents()
        viewport_widget.repaint()
        if application is not None:
            application.processEvents()


def _write_viewport_image(viewport_widget: Any, output_path: Path) -> None:
    """Write the current Katana viewport framebuffer to ``output_path``."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    if output_path.exists():
        try:
            output_path.unlink()
        except OSError as exc:
            raise RuntimeError(
                "Katana review viewport cannot replace existing output."
            ) from exc

    try:
        image = viewport_widget.grabFramebuffer()
        saved = (
            image is not None
            and not image.isNull()
            and image.save(str(output_path), "PNG")
        )
    except Exception as exc:
        with suppress(OSError):
            output_path.unlink()
        raise RuntimeError("Katana could not capture the review viewport.") from exc

    if not saved:
        with suppress(OSError):
            output_path.unlink()
        raise RuntimeError("Katana review viewport capture produced no image.")

    try:
        valid_output = output_path.is_file() and output_path.stat().st_size > 0
    except OSError:
        valid_output = False
    if not valid_output:
        with suppress(OSError):
            output_path.unlink()
        raise RuntimeError("Katana review viewport capture produced no image.")


def _remove_paths(paths: list[Path]) -> None:
    """Best-effort removal of partially captured review frames."""
    for path in paths:
        with suppress(OSError):
            path.unlink()


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

    The active Katana frame and Viewer presentation are restored even when
    capture fails. Files from a failed capture are removed before re-raising.

    Args:
        viewer_widget: Selected Katana Viewer tab widget.
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
    if (
        not product_name
        or product_name in {".", ".."}
        or "/" in product_name
        or "\\" in product_name
        or Path(product_name).is_absolute()
    ):
        raise ValueError(
            "Review product name must be a single non-empty filename component."
        )

    frames = frame_numbers(frame_start, frame_end, frame_step)
    viewport_widget = _select_review_viewport(viewer_widget)

    from Katana import NodegraphAPI

    staging_dir.mkdir(parents=True, exist_ok=True)
    original_frame = NodegraphAPI.GetCurrentTime()
    created_paths: list[Path] = []
    capture_failed = False
    try:
        for frame in frames:
            NodegraphAPI.SetCurrentTime(frame)
            _synchronize_viewport(viewport_widget)

            filename = f"{product_name}.{frame:0{frame_padding}d}.png"
            output_path = staging_dir / filename
            _write_viewport_image(viewport_widget, output_path)
            created_paths.append(output_path)
    except Exception:
        capture_failed = True
        _remove_paths(created_paths)
        raise
    finally:
        try:
            NodegraphAPI.SetCurrentTime(original_frame)
            _synchronize_viewport(viewport_widget)
        except Exception:
            if not capture_failed:
                _remove_paths(created_paths)
                raise

    return [path.name for path in created_paths]
