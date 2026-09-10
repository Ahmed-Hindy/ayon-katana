"""Load USD representations into a managed Katana node graph."""

from contextlib import suppress

from ayon_core.lib import TextDef
from Katana import NodegraphAPI

from ayon_katana.api import containers, plugin
from ayon_katana.api.usd import USD_PRODUCT_BASE_TYPES


class UsdLoader(plugin.KatanaLoader):
    """Load and manage a USD representation through a Katana UsdIn node."""

    product_base_types = USD_PRODUCT_BASE_TYPES
    product_types = product_base_types
    label = "Load USD (Scene Graph)"
    representations = {"*"}
    extensions = {"usd", "usda", "usdc", "usdlc", "usdnc", "usdz"}
    order = 1

    icon = "code-fork"
    color = "orange"

    source_node_type = "UsdIn"
    source_node_suffix = "UsdIn"
    filepath_parameter = "fileName"

    @classmethod
    def get_options(cls, contexts):
        """Return loader options shared by the selected representations."""
        return [
            TextDef(
                "location",
                label="Scenegraph location",
                default="",
                tooltip=(
                    "Optional USD scenegraph location, for example "
                    "'/root/world/geo'. Leave empty to use Katana's native "
                    "default."
                ),
            )
        ]

    def load(self, context, name=None, namespace=None, options=None):
        """Load a USD representation and return its AYON container node."""
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

            source_node = NodegraphAPI.CreateNode(
                self.source_node_type,
                managed_group,
            )
            source_node.setName(f"{namespace}_{product_name}_{self.source_node_suffix}")
            source_node.getParameter(self.filepath_parameter).setValue(
                self.filepath_from_context(context), 0.0
            )
            self._apply_options(source_node, options)

            containers.set_managed_node_role(source_node, containers.SOURCE_ROLE)
            source_node.getOutputPort("out").connect(managed_group.getReturnPort("out"))
            self[:] = [container_node, source_node]
            return container_node
        except Exception:
            if container_node is not None:
                with suppress(Exception):
                    container_node.delete()
            raise

    def _apply_options(self, source_node, options) -> None:
        """Apply loader-specific settings to a newly created source node."""
        location = options.get("location")
        if location:
            source_node.getParameter("location").setValue(location, 0.0)

    def update(self, container, context):
        """Update a USD container to a new representation."""
        container_node = container["node"]
        source_node = containers.find_managed_node(
            container_node, containers.SOURCE_ROLE
        )
        if source_node is None:
            raise RuntimeError(
                "The AYON container is missing its managed "
                f"{self.source_node_type} node."
            )

        filepath = self.filepath_from_context(context)
        file_parameter = source_node.getParameter(self.filepath_parameter)
        old_filepath = file_parameter.getValue(0.0)
        old_container_data = containers.parse_container(container_node)
        if old_container_data is None:
            raise RuntimeError("The AYON USD container has invalid metadata.")
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
        """Remove a USD container from the Katana project."""
        container["node"].delete()

    def switch(self, container, context):
        """Switch a USD container to another representation."""
        self.update(container, context)


class UsdSublayerLoader(UsdLoader):
    """Compose a USD representation into Katana's native USD graph."""

    label = "Sublayer USD (Native Graph)"
    extensions = {"usd", "usda", "usdc", "usdlc", "usdnc"}
    order = 0

    source_node_type = "UsdSubLayerAdd"
    source_node_suffix = "UsdSubLayerAdd"
    filepath_parameter = "asset"

    @classmethod
    def get_options(cls, contexts):
        """Return no Geolib-only options for native USD composition."""
        return []

    def _apply_options(self, source_node, options) -> None:
        """Keep native sublayer composition on Katana's node defaults."""
        _ = source_node, options
