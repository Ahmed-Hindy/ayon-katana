"""Validate render instances before local or farm execution."""

from __future__ import annotations

import pyblish.api
from ayon_core.pipeline import OptionalPyblishPluginMixin
from ayon_core.pipeline.publish import PublishValidationError

from ayon_katana.api import compat, plugin, render
from ayon_katana.plugins.publish.actions import (
    ReconnectAYONRenderGraphAction,
    SelectInvalidInstanceNodes,
)


class ValidateRender(
    plugin.KatanaInstancePlugin,
    OptionalPyblishPluginMixin,
):
    """Validate the render graph and enabled outputs."""

    label = "Validate Render"
    order = pyblish.api.ValidatorOrder
    families = ["render", "katana.render"]
    actions = [SelectInvalidInstanceNodes, ReconnectAYONRenderGraphAction]
    optional = True

    def process(self, instance):
        """Validate the instance graph and renderer."""
        if not self.is_active(instance.data):
            return

        instance_node_name = instance.data.get("instance_node")
        instance_node = compat.get_node(instance_node_name)
        if instance_node is None:
            raise PublishValidationError(
                f"Katana render instance node was not found: {instance_node_name}"
            )
        if render.get_render_node(instance_node) is None:
            raise PublishValidationError(
                f"Render instance {instance_node_name!r} has no Render node."
            )
        if render.get_settings_node(instance_node) is None:
            raise PublishValidationError(
                f"Render instance {instance_node_name!r} has no RenderSettings node."
            )

        renderer_name = instance.data.get("renderer") or ""
        if not renderer_name:
            raise PublishValidationError("RenderSettings has no renderer.")
        render_target = (instance.data.get("creator_attributes") or {}).get(
            "render_target",
            "farm",
        )
        if render_target != "local_no_render" and not render.is_renderer_registered(
            renderer_name
        ):
            raise PublishValidationError(
                f"Renderer {renderer_name!r} is not registered in this process."
            )

        output_definitions = render.get_output_definitions(instance_node)
        if not output_definitions:
            raise PublishValidationError("Render instance has no enabled outputs.")

        for output_definition in output_definitions:
            output_node = compat.get_node(output_definition.node_name)
            input_port = output_node.getInputPort("input") if output_node else None
            if input_port is None or not input_port.getConnectedPorts():
                raise PublishValidationError(
                    f"Render output {output_definition.node_name!r} is disconnected."
                )
