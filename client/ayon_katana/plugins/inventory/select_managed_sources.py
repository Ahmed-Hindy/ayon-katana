"""Scene Inventory action for selecting loader-owned source nodes."""

from ayon_core.pipeline import InventoryAction

from ayon_katana.api import compat
from ayon_katana.api import containers as container_api


class SelectManagedSources(InventoryAction):
    """Select the managed source nodes for loaded containers."""

    label = "Select Managed Sources"
    icon = "code-fork"
    color = "#888888"
    order = 100

    @staticmethod
    def is_compatible(container) -> bool:
        """Return whether the container has a managed source node."""
        container_node = container.get("node")
        if container_node is None:
            object_name = container.get("objectName")
            container_node = compat.get_node(object_name) if object_name else None
        if container_node is None:
            return False
        return (
            container_api.find_managed_node(container_node, container_api.SOURCE_ROLE)
            is not None
        )

    def process(self, containers) -> None:
        """Replace Katana's current selection with managed source nodes."""
        source_nodes = []
        for container in containers:
            container_node = container.get("node")
            if container_node is None:
                object_name = container.get("objectName")
                container_node = compat.get_node(object_name) if object_name else None
            if container_node is None:
                continue

            source_node = container_api.find_managed_node(
                container_node, container_api.SOURCE_ROLE
            )
            if source_node is not None:
                source_nodes.append(source_node)

        if source_nodes:
            compat.set_selected_nodes(source_nodes)
