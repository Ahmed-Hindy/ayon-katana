"""Katana Viewer thumbnail helpers."""

from __future__ import annotations

import os
import tempfile
from contextlib import suppress
from pathlib import Path
from typing import Any, Optional

MAX_THUMBNAIL_DIMENSION = 1024


def get_viewer_tabs() -> list[Any]:
    """Return open Viewer tabs without changing the layout."""
    try:
        from Katana import UI4
    except ImportError:
        return []

    layouts = getattr(UI4.App, "Layouts", None)
    if layouts is not None and hasattr(layouts, "GetTabs"):
        try:
            return list(
                layouts.GetTabs(
                    "Viewer",
                    includeFloating=True,
                    includeDockWidgets=True,
                )
                or []
            )
        except Exception:
            return []

    tabs_api = getattr(UI4.App, "Tabs", None)
    if tabs_api is not None and hasattr(tabs_api, "GetTabsByType"):
        try:
            return list(tabs_api.GetTabsByType("Viewer") or [])
        except Exception:
            return []
    return []


def select_viewer_widget() -> tuple[Optional[Any], str]:
    """Choose the focused Viewer, or the only visible Viewer.

    Returns:
        A ``(widget, reason)`` pair. ``widget`` is ``None`` when no Viewer
        can be selected; ``reason`` explains why.
    """
    viewers = get_viewer_tabs()
    if not viewers:
        return None, "no Viewer tab is available"

    visible = [viewer for viewer in viewers if _is_visible(viewer)]
    if not visible:
        return None, "no visible Viewer tab is available"

    focus_widget = _get_focus_widget()
    focused = [viewer for viewer in visible if _contains_focus(viewer, focus_widget)]
    if len(focused) == 1:
        return focused[0], "focused Viewer"
    if len(focused) > 1:
        return None, "multiple visible Viewer tabs contain focus"
    if len(visible) == 1:
        return visible[0], "sole visible Viewer"
    return None, "multiple visible Viewer tabs are ambiguous"


def capture_viewer_image(
    viewer_widget: Any,
    output_path: os.PathLike[str] | str,
    *,
    max_dimension: Optional[int] = None,
) -> str:
    """Capture a Viewer widget directly to a PNG path.

    Args:
        viewer_widget: Katana Viewer Qt widget.
        output_path: Destination PNG path.
        max_dimension: Optional maximum width or height. ``None`` preserves
            the native Viewer widget dimensions.

    Returns:
        Normalized destination path.

    Raises:
        RuntimeError: The widget cannot be captured or the PNG cannot be saved.
        ValueError: ``max_dimension`` is not positive when supplied.
    """
    if max_dimension is not None and max_dimension < 1:
        raise ValueError("Viewer capture maximum dimension must be positive.")

    try:
        pixmap = viewer_widget.grab()
    except Exception as exc:
        raise RuntimeError("Failed to capture the Katana Viewer.") from exc
    if pixmap is None or pixmap.isNull():
        raise RuntimeError("Katana Viewer capture returned an empty image.")

    width = int(pixmap.width())
    height = int(pixmap.height())
    if width < 1 or height < 1:
        raise RuntimeError("Katana Viewer capture has invalid dimensions.")

    if max_dimension is not None and max(width, height) > max_dimension:
        try:
            from qtpy import QtCore

            pixmap = pixmap.scaled(
                max_dimension,
                max_dimension,
                QtCore.Qt.KeepAspectRatio,
                QtCore.Qt.SmoothTransformation,
            )
        except Exception as exc:
            raise RuntimeError("Failed to scale the Katana Viewer capture.") from exc
        if pixmap is None or pixmap.isNull():
            raise RuntimeError("Katana Viewer capture scaling returned no image.")

    destination = Path(output_path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    try:
        saved = pixmap.save(str(destination), "PNG")
    except Exception as exc:
        with suppress(OSError):
            destination.unlink()
        raise RuntimeError("Qt could not save the Viewer capture.") from exc
    if not saved:
        with suppress(OSError):
            destination.unlink()
        raise RuntimeError("Qt could not save the Viewer capture.")
    return str(destination)


def capture_viewer_thumbnail(
    viewer_widget: Any,
    max_dimension: int = MAX_THUMBNAIL_DIMENSION,
) -> str:
    """Capture a Viewer widget to a temporary PNG thumbnail."""
    with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as stream:
        output_path = stream.name
    try:
        return capture_viewer_image(
            viewer_widget,
            output_path,
            max_dimension=max_dimension,
        )
    except Exception:
        with suppress(OSError):
            os.remove(output_path)
        raise


def _get_focus_widget() -> Optional[Any]:
    try:
        from qtpy import QtWidgets

        application = QtWidgets.QApplication.instance()
        if application is None:
            return None
        return application.focusWidget()
    except Exception:
        return None


def _is_visible(widget: Any) -> bool:
    try:
        return bool(widget.isVisible())
    except Exception:
        return False


def _contains_focus(widget: Any, focus_widget: Optional[Any]) -> bool:
    if focus_widget is None:
        return False
    if focus_widget is widget:
        return True
    try:
        return bool(widget.isAncestorOf(focus_widget))
    except Exception:
        return False
