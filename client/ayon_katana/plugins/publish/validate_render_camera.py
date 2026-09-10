"""Validate the native Katana render camera location."""

from __future__ import annotations

import pyblish.api
from ayon_core.pipeline import OptionalPyblishPluginMixin
from ayon_core.pipeline.publish import PublishValidationError

from ayon_katana.api import compat, plugin, render


class ValidateRenderCamera(
    plugin.KatanaInstancePlugin,
    OptionalPyblishPluginMixin,
):
    """Validate the Render node camera setting."""

    label = "Validate Render Camera"
    order = pyblish.api.ValidatorOrder - 0.1
    families = ["render", "katana.render"]
    optional = True

    def process(self, instance) -> None:
        """Reject render instances without a valid camera location."""
        if not self.is_active(instance.data):
            return

        camera_path = str(instance.data.get("camera") or "").strip()
        if not camera_path:
            raise PublishValidationError(
                "Katana RenderSettings has no camera location."
            )
        render_node = compat.get_node(instance.data.get("render_node"))
        if render_node is None:
            raise PublishValidationError(
                "Katana Render node is unavailable for camera cook."
            )
        location_type = render.get_scenegraph_location_type(
            render_node,
            camera_path,
        )
        if not location_type:
            raise PublishValidationError(
                f"Katana camera location could not be resolved: {camera_path}"
            )
        if location_type.casefold() != "camera":
            raise PublishValidationError(
                f"Katana camera location is not a camera: {camera_path}"
            )
