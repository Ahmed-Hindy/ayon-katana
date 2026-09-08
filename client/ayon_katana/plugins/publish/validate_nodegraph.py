"""Validate Katana node graph publish instances."""

from __future__ import annotations

import pyblish.api
from ayon_core.pipeline import OptionalPyblishPluginMixin
from ayon_core.pipeline.publish import PublishValidationError

from ayon_katana.api import compat, containers, plugin


class ValidateNodegraph(
    plugin.KatanaInstancePlugin,
    OptionalPyblishPluginMixin,
):
    """Validate the selected source Group."""

    label = "Validate Node Graph"
    order = pyblish.api.ValidatorOrder
    families = ["nodegraph"]
    optional = True

    def process(self, instance):
        """Validate the source Group."""
        if not self.is_active(instance.data):
            return

        source_name = instance.data.get("nodegraph_node")
        if not source_name:
            raise PublishValidationError(
                "Node graph instance has no selected Group identifier.",
                title="Node graph source missing",
            )
        source_node = compat.get_node(str(source_name))
        if source_node is None:
            raise PublishValidationError(
                f"Node graph source no longer exists: {source_name}",
                title="Node graph source missing",
            )
        if source_node.getType() != "Group":
            raise PublishValidationError(
                "Node graph source must remain a Group node.",
                title="Node graph source invalid",
            )
        if containers.parse_container(source_node) is not None:
            raise PublishValidationError(
                "Node graph source cannot be an outer AYON container.",
                title="Node graph source invalid",
            )

        instance_name = instance.data.get("instance_node")
        instance_node = compat.get_node(str(instance_name)) if instance_name else None
        if instance_node is not None and (
            source_node is instance_node
            or compat.is_descendant(instance_node, source_node)
        ):
            raise PublishValidationError(
                "Node graph source contains its publishing instance.",
                title="Node graph source recursive",
            )

        if not compat.get_output_ports(source_node):
            raise PublishValidationError(
                "Node graph source must expose at least one output port.",
                title="Node graph output missing",
            )
