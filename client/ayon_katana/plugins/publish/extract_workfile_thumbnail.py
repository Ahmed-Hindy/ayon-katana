"""Capture a Katana Viewer thumbnail for workfile publishing."""

from __future__ import annotations

import pyblish.api
from ayon_core.pipeline import OptionalPyblishPluginMixin

from ayon_katana.api import plugin, thumbnail


class ExtractWorkfileThumbnail(
    plugin.KatanaInstancePlugin,
    OptionalPyblishPluginMixin,
):
    """Capture a workfile thumbnail from the current Viewer."""

    label = "Extract Workfile Thumbnail"
    order = pyblish.api.ExtractorOrder + 0.49
    families = ["workfile"]
    optional = True

    def process(self, instance) -> None:
        """Capture the Viewer thumbnail."""
        if not self.is_active(instance.data):
            return
        if instance.data.get("thumbnailPath"):
            self.log.debug("Keeping the existing workfile thumbnail.")
            return

        viewer_widget, reason = thumbnail.select_viewer_widget()
        if viewer_widget is None:
            self.log.debug("Skipping workfile thumbnail: %s.", reason)
            return

        try:
            thumbnail_path = thumbnail.capture_viewer_thumbnail(viewer_widget)
        except Exception as exc:
            self.log.warning("Katana Viewer thumbnail capture failed: %s", exc)
            return

        instance.data["thumbnailPath"] = thumbnail_path
        cleanup_paths = instance.context.data.setdefault("cleanupFullPaths", [])
        if thumbnail_path not in cleanup_paths:
            cleanup_paths.append(thumbnail_path)
        self.log.debug(
            "Captured workfile thumbnail from %s: %s",
            reason,
            thumbnail_path,
        )
