"""Create publish instances for reusable Katana node graphs."""

from __future__ import annotations

from typing import Any

from ayon_core.pipeline import CreatorError

from ayon_katana.api import compat, containers, plugin


class CreateNodegraph(plugin.KatanaCreator):
    """Create a publish instance for exactly one selected Katana Group."""

    identifier = "io.ayon.creators.katana.nodegraph"
    label = "Node Graph"
    product_base_type = "nodegraph"
    product_type = product_base_type
    icon = "sitemap"
    description = "Publish one selected Katana Group as a reusable node graph"

    def _selected_group(self):
        """Return the selected Group used as the node graph source.

        Raises:
            CreatorError: The selection is not one publishable Katana Group.
        """
        selected_nodes = compat.get_selected_nodes()
        if len(selected_nodes) != 1:
            raise CreatorError(
                "Select exactly one Katana Group node to create a node graph "
                "publish instance."
            )

        selected_node = selected_nodes[0]
        if selected_node.getType() != "Group":
            raise CreatorError(
                "The selected node graph source must be a Katana Group node."
            )
        if containers.parse_container(selected_node) is not None:
            raise CreatorError(
                "The selected Group is an outer AYON container and cannot be "
                "published as a node graph source."
            )
        return selected_node

    def create(
        self,
        product_name: str,
        instance_data: dict[str, Any],
        pre_create_data: dict[str, Any],
    ):
        """Create an AYON instance referencing one selected Group."""
        selected_group = self._selected_group()
        instance_data["nodegraph_node"] = selected_group.getName()
        families = instance_data.setdefault("families", [])
        if "nodegraph" not in families:
            families.append("nodegraph")

        return super().create(
            product_name,
            instance_data,
            pre_create_data,
        )


class CreateRenderSetup(CreateNodegraph):
    """Publish reusable Katana render and lighting setup graphs."""

    identifier = "io.ayon.creators.katana.render_setup"
    label = "Render Setup"
    product_base_type = "rendersetup"
    product_type = product_base_type
    icon = "sliders"
    description = "Publish one reusable Katana render or lighting setup Group"
