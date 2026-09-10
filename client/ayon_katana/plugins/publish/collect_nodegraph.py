"""Collect selected Katana node graph publish data."""

from __future__ import annotations

import pyblish.api

from ayon_katana.api import compat, containers, plugin


class CollectNodegraph(plugin.KatanaInstancePlugin):
    """Collect the source Group for node graph publishing."""

    label = "Collect Node Graph"
    order = pyblish.api.CollectorOrder + 0.01
    families = ["nodegraph"]

    def process(self, instance):
        """Collect node graph source data from its creator instance."""
        node_name = instance.data.get("nodegraph_node")
        if not node_name:
            return
        node = compat.get_node(node_name)
        if node is not None:
            instance.data["nodegraph_node"] = node.getName()


class CollectNodegraphDependencies(plugin.KatanaInstancePlugin):
    """Collect AYON containers nested in the published Group when discoverable."""

    label = "Collect Node Graph Dependencies"
    order = pyblish.api.CollectorOrder + 0.02
    families = ["nodegraph"]

    def process(self, instance):
        """Collect representation dependencies from nested containers."""
        node_name = instance.data.get("nodegraph_node")
        source_node = compat.get_node(node_name) if node_name else None
        if source_node is None:
            return

        representation_ids = {
            container.get("representation")
            for container in containers.ls()
            if container.get("representation")
            and compat.is_descendant(container["node"], source_node)
        }
        inputs = sorted(representation_ids)
        instance.data["inputRepresentations"] = inputs
        self.log.debug("Collected inputs: %s", inputs)
