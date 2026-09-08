"""Katana Viewer thumbnail helpers."""

from __future__ import annotations

import os
import tempfile
from contextlib import suppress
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


def capture_viewer_thumbnail(
    viewer_widget: Any,
    max_dimension: int = MAX_THUMBNAIL_DIMENSION,
) -> str:
    """Capture a Viewer widget to a temporary PNG.

    Args:
        viewer_widget: Katana Viewer Qt widget.
        max_dimension: Maximum output width or height in pixels.

    Returns:
        Path to the temporary PNG.

    Raises:
        RuntimeError: The widget cannot be captured or the PNG cannot be saved.
        ValueError: ``max_dimension`` is not positive.
    """
    if max_dimension < 1:
        raise ValueError("Thumbnail maximum dimension must be positive.")

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

    if max(width, height) > max_dimension:
        try:
            from qtpy import QtCore

            pixmap = pixmap.scaled(
                max_dimension,
                max_dimension,
                QtCore.Qt.KeepAspectRatio,
                QtCore.Qt.SmoothTransformation,
            )
        except Exception as exc:
            raise RuntimeError("Failed to scale the Katana Viewer thumbnail.") from exc
        if pixmap is None or pixmap.isNull():
            raise RuntimeError("Katana Viewer thumbnail scaling returned no image.")

    with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as stream:
        output_path = stream.name
    try:
        if not pixmap.save(output_path, "PNG"):
            raise RuntimeError("Qt could not save the Viewer thumbnail.")
    except Exception:
        with suppress(OSError):
            os.remove(output_path)
        raise
    return output_path


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
