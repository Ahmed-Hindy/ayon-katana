"""Collect the frame range for Katana render instances."""

from __future__ import annotations

import pyblish.api

from ayon_katana.api import compat, plugin, render


class CollectRenderFrameRange(plugin.KatanaInstancePlugin):
    """Collect the Render node frame range."""

    label = "Collect Frame Range"
    order = pyblish.api.CollectorOrder + 0.11
    families = ["render", "katana.render"]

    def process(self, instance) -> None:
        """Collect frame start, end, and step."""
        render_node = compat.get_node(instance.data.get("render_node"))
        if render_node is None:
            raise RuntimeError("Katana Render node must be collected before frames.")
        frame_range = render.get_render_frame_range(render_node)
        instance.data.update(
            {
                "frameStartHandle": frame_range.start,
                "frameEndHandle": frame_range.end,
                "byFrameStep": frame_range.step,
                "katanaFrameRangeSource": frame_range.source,
            }
        )
