"""Katana Viewer review-sequence capture helpers."""

from __future__ import annotations

from contextlib import suppress
from pathlib import Path
from typing import Any

_FRAMEBUFFER_SYNC_PASSES = 2
_FRAMEBUFFER_SWAP_TIMEOUT_MS = 5000


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


def _select_viewer_framebuffer(viewer_widget: Any) -> Any:
    """Return the only visible framebuffer-capable viewport in a Viewer."""
    try:
        from qtpy import QtWidgets

        children = viewer_widget.findChildren(QtWidgets.QWidget)
    except Exception as exc:
        raise RuntimeError("Scene Review cannot inspect Viewer framebuffers.") from exc

    candidates = []
    for child in children:
        if not callable(getattr(child, "grabFramebuffer", None)):
            continue
        try:
            valid = (
                bool(child.isVisible())
                and int(child.width()) > 0
                and int(child.height()) > 0
            )
        except Exception:
            continue
        if valid:
            candidates.append(child)

    if len(candidates) != 1:
        raise RuntimeError(
            "Scene Review requires exactly one visible framebuffer-capable "
            f"viewport; found {len(candidates)}."
        )
    return candidates[0]


def _wait_for_framebuffer_swap(
    framebuffer_widget: Any,
    *,
    timeout_ms: int = _FRAMEBUFFER_SWAP_TIMEOUT_MS,
) -> None:
    """Wait until the Viewer presents one newly rendered OpenGL frame."""
    from qtpy import QtCore

    signal = getattr(framebuffer_widget, "frameSwapped", None)
    if signal is None or not hasattr(signal, "connect"):
        raise RuntimeError("Katana Viewer framebuffer has no frameSwapped signal.")

    event_loop = QtCore.QEventLoop()
    timer = QtCore.QTimer()
    timer.setSingleShot(True)
    swapped = False

    def on_frame_swapped() -> None:
        """Record one presented Viewer frame and release the local event loop."""
        nonlocal swapped
        swapped = True
        event_loop.quit()

    signal.connect(on_frame_swapped)
    timer.timeout.connect(event_loop.quit)
    try:
        timer.start(timeout_ms)
        framebuffer_widget.update()
        execute = getattr(event_loop, "exec", None) or event_loop.exec_
        execute()
    finally:
        timer.stop()
        with suppress(Exception):
            signal.disconnect(on_frame_swapped)

    if not swapped:
        raise RuntimeError(
            "Timed out waiting for the Katana Viewer framebuffer to render."
        )


def _synchronize_framebuffer(framebuffer_widget: Any) -> None:
    """Flush Katana updates and wait for the Viewer to present the new frame."""
    from Katana import Utils
    from qtpy import QtWidgets

    application = QtWidgets.QApplication.instance()
    # The first swap can still present the previous Hydra frame. Katana 8 and 9
    # both require a second flush/present cycle before the framebuffer is current.
    for _ in range(_FRAMEBUFFER_SYNC_PASSES):
        Utils.EventModule.ProcessAllEvents()
        if application is not None:
            application.processEvents()
        _wait_for_framebuffer_swap(framebuffer_widget)

    Utils.EventModule.ProcessAllEvents()
    if application is not None:
        application.processEvents()


def _capture_framebuffer_image(
    framebuffer_widget: Any,
    output_path: Path,
) -> None:
    """Capture one live Viewer framebuffer to ``output_path``."""
    with suppress(OSError):
        output_path.unlink()
    try:
        image = framebuffer_widget.grabFramebuffer()
    except Exception as exc:
        raise RuntimeError("Failed to capture the Katana Viewer framebuffer.") from exc
    if image is None or image.isNull():
        raise RuntimeError("Katana Viewer framebuffer capture returned an empty image.")
    if int(image.width()) < 1 or int(image.height()) < 1:
        raise RuntimeError("Katana Viewer framebuffer capture has invalid dimensions.")

    output_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        saved = image.save(str(output_path), "PNG")
    except Exception as exc:
        with suppress(OSError):
            output_path.unlink()
        raise RuntimeError("Qt could not save the Viewer framebuffer capture.") from exc
    if not saved:
        with suppress(OSError):
            output_path.unlink()
        raise RuntimeError("Qt could not save the Viewer framebuffer capture.")


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
    framebuffer_widget = _select_viewer_framebuffer(viewer_widget)

    from Katana import NodegraphAPI

    staging_dir.mkdir(parents=True, exist_ok=True)
    original_frame = NodegraphAPI.GetCurrentTime()
    created_paths: list[Path] = []
    capture_failed = False
    try:
        for frame in frames:
            NodegraphAPI.SetCurrentTime(frame)
            _synchronize_framebuffer(framebuffer_widget)

            filename = f"{product_name}.{frame:0{frame_padding}d}.png"
            output_path = staging_dir / filename
            _capture_framebuffer_image(framebuffer_widget, output_path)
            created_paths.append(output_path)
    except Exception:
        capture_failed = True
        for path in created_paths:
            with suppress(OSError):
                path.unlink()
        raise
    finally:
        NodegraphAPI.SetCurrentTime(original_frame)
        try:
            _synchronize_framebuffer(framebuffer_widget)
        except Exception:
            if not capture_failed:
                for path in created_paths:
                    with suppress(OSError):
                        path.unlink()
                raise

    return [path.name for path in created_paths]
