"""Collect nodes for Katana render instances."""

from __future__ import annotations

import pyblish.api

from ayon_katana.api import compat, plugin, render


class CollectRenderNode(plugin.KatanaInstancePlugin):
    """Collect the Render and RenderSettings nodes."""

    label = "Collect Render Node"
    order = pyblish.api.CollectorOrder + 0.1
    families = ["render", "katana.render"]

    def process(self, instance) -> None:
        """Resolve the render graph nodes."""
        instance_node_name = instance.data.get("instance_node")
        instance_node = compat.get_node(instance_node_name)
        if instance_node is None:
            raise RuntimeError(
                f"Katana render instance node does not exist: {instance_node_name}"
            )
        render_node = render.get_render_node(instance_node)
        settings_node = render.get_settings_node(instance_node)
        if render_node is None or settings_node is None:
            raise RuntimeError(
                f"Katana render graph is incomplete: {instance_node_name}"
            )
        instance.data.update(
            {
                "instance_node": instance_node.getName(),
                "render_node": render_node.getName(),
                "render_settings_node": settings_node.getName(),
            }
        )
