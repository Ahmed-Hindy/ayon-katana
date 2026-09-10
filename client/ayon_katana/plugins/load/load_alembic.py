"""Load Alembic representations into managed Katana node graphs."""

from contextlib import suppress

from ayon_core.lib import TextDef
from Katana import NodegraphAPI

from ayon_katana.api import containers, plugin


class AbcLoader(plugin.KatanaLoader):
    """Load and manage Alembic data through a Katana Alembic_In node."""

    product_base_types = {
        "alembic",
        "animation",
        "camera",
        "model",
        "pointcache",
    }
    product_types = product_base_types
    label = "Load Alembic"
    representations = {"*"}
    extensions = {"abc"}
    order = 2

    icon = "database"
    color = "orange"

    @classmethod
    def get_options(cls, contexts):
        """Return loader options shared by the selected representations."""
        return [
            TextDef(
                "location",
                label="Scenegraph location",
                default="",
                tooltip=(
                    "Optional Alembic scenegraph location, for example "
                    "'/root/world/geo'. Leave empty to use Katana's native "
                    "default."
                ),
            )
        ]

    def load(self, context, name=None, namespace=None, options=None):
        """Load an Alembic representation and return its container node."""
        options = options or {}
        product_name = name or context["product"]["name"]
        namespace = namespace or context["folder"]["name"]
        container_node = None
        try:
            container_node = containers.containerise(
                name=product_name,
                namespace=namespace,
                context=context,
                loader=self.__class__.__name__,
            )
            managed_group = containers.get_managed_group(container_node)
            if managed_group is None:
                raise RuntimeError("Failed to create the AYON managed group.")

            source_node = NodegraphAPI.CreateNode("Alembic_In", managed_group)
            source_node.setName(f"{namespace}_{product_name}_AlembicIn")
            source_node.getParameter("abcAsset").setValue(
                self.filepath_from_context(context), 0.0
            )
            location = options.get("location")
            if location:
                source_node.getParameter("name").setValue(location, 0.0)
            containers.set_managed_node_role(source_node, containers.SOURCE_ROLE)
            source_node.getOutputPort("out").connect(managed_group.getReturnPort("out"))
            self[:] = [container_node, source_node]
            return container_node
        except Exception:
            if container_node is not None:
                with suppress(Exception):
                    container_node.delete()
            raise

    def update(self, container, context):
        """Update an Alembic container to a new representation."""
        container_node = container["node"]
        source_node = containers.find_managed_node(
            container_node, containers.SOURCE_ROLE
        )
        if source_node is None:
            raise RuntimeError(
                "The AYON container is missing its managed Alembic_In node."
            )
        filepath = self.filepath_from_context(context)
        file_parameter = source_node.getParameter("abcAsset")
        old_filepath = file_parameter.getValue(0.0)
        old_container_data = containers.parse_container(container_node)
        if old_container_data is None:
            raise RuntimeError("The AYON Alembic container has invalid metadata.")
        old_container_data.pop("node", None)
        old_container_data.pop("objectName", None)
        project = context.get("project") or {}
        try:
            file_parameter.setValue(filepath, 0.0)
            containers.update_container(
                container_node,
                {
                    "representation": context["representation"]["id"],
                    "project_name": project.get("name"),
                    "loader": self.__class__.__name__,
                },
            )
        except Exception:
            with suppress(Exception):
                file_parameter.setValue(old_filepath, 0.0)
            with suppress(Exception):
                containers.update_container(container_node, old_container_data)
            raise

    def remove(self, container):
        """Remove an Alembic container from the Katana project."""
        container["node"].delete()

    def switch(self, container, context):
        """Switch an Alembic container to another representation."""
        self.update(container, context)
