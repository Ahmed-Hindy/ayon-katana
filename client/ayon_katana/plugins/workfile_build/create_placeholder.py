"""Create Katana Workfile Builder placeholders for publish instances."""

from __future__ import annotations

from ayon_core.pipeline.workfile.workfile_template_builder import (
    CreatePlaceholderItem,
    PlaceholderCreateMixin,
)
from Katana import NodegraphAPI

from ayon_katana.api import compat, instances, lib
from ayon_katana.api.workfile_template_builder import KatanaPlaceholderPlugin


class KatanaPlaceholderCreatePlugin(
    KatanaPlaceholderPlugin,
    PlaceholderCreateMixin,
):
    """Replace Workfile Builder create placeholders with publish instances."""

    identifier = "ayon.create.placeholder"
    label = "Katana Create"

    def get_placeholder_node_name(self, placeholder_data):
        """Return a stable node name derived from the configured creator."""
        creator_name = placeholder_data.get("creator") or "creator"
        creator = self.builder.get_creators_by_name().get(creator_name)
        product_type = getattr(creator, "product_base_type", creator_name)
        return lib.sanitize_node_name(
            f"AYON_PLACEHOLDER_CREATE_{product_type}",
            "AYON_PLACEHOLDER_CREATE",
        )

    def create_placeholder_node(self, node_name):
        """Create a pass-through Group for a creator placeholder."""
        placeholder_node = NodegraphAPI.CreateNode("Group", NodegraphAPI.GetRootNode())
        placeholder_node.setName(node_name)
        placeholder_node.addInputPort("in")
        placeholder_node.addOutputPort("out")
        placeholder_node.getSendPort("in").connect(
            placeholder_node.getReturnPort("out")
        )
        return placeholder_node

    def populate_placeholder(self, placeholder):
        """Populate a creator placeholder when it is still empty."""
        placeholder_node = compat.get_node(placeholder.scene_identifier)
        if placeholder_node is None:
            raise RuntimeError(
                f"Katana placeholder no longer exists: {placeholder.scene_identifier}"
            )
        if self._get_created_instance_nodes(placeholder_node):
            self.log.info(
                "Creator placeholder %s is already populated.",
                placeholder.scene_identifier,
            )
            return
        self.populate_create_placeholder(placeholder)

    def repopulate_placeholder(self, placeholder):
        """Populate a creator placeholder again when needed."""
        self.populate_placeholder(placeholder)

    def get_placeholder_options(self, options=None):
        """Return the Workfile Builder creator options."""
        return self.get_create_plugin_options(options)

    def collect_placeholders(self):
        """Return creator placeholders stored in the current project."""
        output = []
        create_placeholders = self.collect_scene_placeholders()
        for node in create_placeholders:
            placeholder_data = self._read(node)
            if placeholder_data.get("plugin_identifier") != self.identifier:
                continue
            output.append(
                CreatePlaceholderItem(
                    node.getName(),
                    placeholder_data,
                    self,
                )
            )
        return output

    def create_succeed(self, placeholder, creator_instance):
        """Connect a successfully created instance inside its placeholder."""
        placeholder_node = compat.get_node(placeholder.scene_identifier)
        instance_node = creator_instance.transient_data.get("node")
        if placeholder_node is None or instance_node is None:
            return

        compat.set_parent(instance_node, placeholder_node)
        send_port = placeholder_node.getSendPort("in")
        instance_input = instance_node.getInputPort("in")
        instance_output = instance_node.getOutputPort("out")
        return_port = placeholder_node.getReturnPort("out")

        for connected_port in list(send_port.getConnectedPorts()):
            send_port.disconnect(connected_port)
        if instance_input is not None:
            send_port.connect(instance_input)
        if instance_output is not None:
            instance_output.connect(return_port)
        else:
            send_port.connect(return_port)

        NodegraphAPI.SetNodePosition(instance_node, (0.0, 0.0))
        placeholder.data["created_product_name"] = creator_instance["productName"]
        self._imprint(placeholder_node, placeholder.data)

    def delete_placeholder(self, placeholder):
        """Consume a populated placeholder or delete an empty one."""
        placeholder_node = compat.get_node(placeholder.scene_identifier)
        if placeholder_node is None:
            return
        if self._get_created_instance_nodes(placeholder_node):
            self.clear_placeholder(placeholder_node)
            return
        placeholder_node.delete()

    @staticmethod
    def _get_created_instance_nodes(placeholder_node):
        output = []
        for node in instances.iter_nodes(placeholder_node):
            if instances.read(node) is not None:
                output.append(node)
        return output
