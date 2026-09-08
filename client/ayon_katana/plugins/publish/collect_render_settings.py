"""Collect Katana render settings and colorspace metadata."""

from __future__ import annotations

import pyblish.api

from ayon_katana.api import colorspace, compat, lib, plugin, render


class CollectRenderSettings(plugin.KatanaInstancePlugin):
    """Collect render settings and colorspace metadata."""

    label = "Collect Render Settings"
    order = pyblish.api.CollectorOrder + 0.415
    families = ["render", "katana.render"]

    def process(self, instance) -> None:
        """Collect renderer, camera, resolution, and colorspace."""
        settings_node = compat.get_node(instance.data.get("render_settings_node"))
        if settings_node is None:
            raise RuntimeError("Katana RenderSettings node must be collected first.")
        settings = render.get_effective_render_settings(settings_node)
        resolution = render.get_resolution(settings.resolution_name)
        instance.data.update(
            {
                "renderer": settings.renderer,
                "camera": settings.camera,
                "katanaResolution": resolution.name,
                "resolutionWidth": resolution.width,
                "resolutionHeight": resolution.height,
                "pixelAspect": resolution.pixel_aspect,
            }
        )

        color_data = lib.get_color_management_preferences() or {}
        colorspace_name = color_data.get("colorspace", "")
        if color_data:
            instance.data["colorspaceConfig"] = color_data["config"]
            instance.data["colorspace"] = colorspace_name

        expected_files = instance.data.get("expectedFiles") or []
        if expected_files:
            instance.data["renderProducts"] = colorspace.ARenderProduct(
                list(expected_files[0]),
                colorspace_name,
            )
