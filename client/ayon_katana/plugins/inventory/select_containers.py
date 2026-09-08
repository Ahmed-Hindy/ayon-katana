"""Select Katana nodes owned by chosen AYON containers."""

from ayon_core.pipeline import InventoryAction

from ayon_katana.api import compat


def _get_container_node(container):
    node = container.get("node")
    if node is not None:
        return node

    object_name = container.get("objectName")
    return compat.get_node(object_name) if object_name else None


class SelectInScene(InventoryAction):
    """Select Katana nodes represented by Scene Inventory containers."""

    label = "Select in scene"
    icon = "search"
    color = "#888888"
    order = 99

    @staticmethod
    def is_compatible(container):
        """Return whether a container resolves to a Katana node."""
        return _get_container_node(container) is not None

    def process(self, containers):
        """Select the Katana nodes for the chosen containers."""
        nodes = [
            node
            for node in (_get_container_node(container) for container in containers)
            if node is not None
        ]
        if not nodes:
            return

        compat.set_selected_nodes(nodes)
