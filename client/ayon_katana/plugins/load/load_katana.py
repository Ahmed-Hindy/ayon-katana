"""Load published Katana node graphs into managed containers."""

from contextlib import suppress
from pathlib import Path

from Katana import NodegraphAPI

from ayon_katana.api import compat, containers, plugin

_IMPORT_ROLE = "import_combine"
_TEMP_MANAGED_GROUP_NAME = "AYON_MANAGED_PENDING"


class KatanaImportLoader(plugin.KatanaLoader):
    """Import a published ``.katana`` graph below an AYON container."""

    product_base_types = {"katana", "nodegraph", "rendersetup", "workfile"}
    product_types = product_base_types
    label = "Import Katana Graph"
    representations = {"katana"}
    extensions = {"katana"}
    order = 3

    icon = "sitemap"
    color = "orange"

    def _import_graph(self, managed_group, filepath: str) -> list:
        """Import nodes and connect scenegraph outputs to the managed return."""
        imported_nodes = compat.import_katana_file(
            filepath,
            parent_node=managed_group,
            float_nodes=False,
        )
        if not imported_nodes:
            raise RuntimeError("The Katana import did not create any nodes.")

        imported_set = set(imported_nodes)
        terminal_outputs = []
        for node in imported_nodes:
            for output_port in compat.get_output_ports(node):
                connected_inside_import = any(
                    connected_port.getNode() in imported_set
                    for connected_port in output_port.getConnectedPorts()
                )
                if not connected_inside_import:
                    terminal_outputs.append((node, output_port))
        if not terminal_outputs:
            raise RuntimeError(
                "The imported Katana graph has no usable terminal output port."
            )

        if len(terminal_outputs) == 1:
            output_node, output_port = terminal_outputs[0]
            output_port.connect(managed_group.getReturnPort("out"))
            containers.set_managed_node_role(output_node, containers.SOURCE_ROLE)
            return imported_nodes

        combine_node = NodegraphAPI.CreateNode("Merge", managed_group)
        combine_node.setName("AYON_IMPORTED_MERGE")
        containers.set_managed_node_role(combine_node, _IMPORT_ROLE)
        for index, (_output_node, output_port) in enumerate(terminal_outputs):
            input_port = combine_node.addInputPort(f"i{index}")
            output_port.connect(input_port)
        combine_node.getOutputPort("out").connect(managed_group.getReturnPort("out"))
        return imported_nodes + [combine_node]

    @classmethod
    def _representation_path(cls, context) -> str:
        """Resolve and validate the representation path before graph mutation."""
        filepath = cls.filepath_from_context(context)
        if not filepath:
            raise RuntimeError("The Katana representation does not have a filepath.")

        try:
            resolved_path = Path(filepath).expanduser().resolve(strict=True)
        except OSError as exc:
            raise RuntimeError(
                f"Katana representation file does not exist: {filepath!r}"
            ) from exc
        if not resolved_path.is_file():
            raise RuntimeError(
                f"Katana representation path is not a file: {filepath!r}"
            )
        return resolved_path.as_posix()

    @staticmethod
    def _validate_update_candidate(managed_group, user_group) -> None:
        """Validate that a staged graph can feed the existing user graph."""
        managed_output = managed_group.getOutputPort("out")
        managed_return = managed_group.getReturnPort("out")
        user_input = user_group.getInputPort("in")
        if managed_output is None or managed_return is None or user_input is None:
            raise RuntimeError("The AYON container has incomplete managed/user ports.")
        if not managed_return.getConnectedPorts():
            raise RuntimeError(
                "The imported Katana graph does not connect to its managed output."
            )

    def load(self, context, name=None, namespace=None, options=None):
        """Import a Katana representation and return its container node."""
        filepath = self._representation_path(context)
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
            imported_nodes = self._import_graph(managed_group, filepath)
            self[:] = [container_node, *imported_nodes]
            return container_node
        except Exception:
            if container_node is not None:
                with suppress(Exception):
                    container_node.delete()
            raise

    def update(self, container, context):
        """Replace a container's managed graph with a new representation."""
        container_node = container["node"]
        managed_group = containers.get_managed_group(container_node)
        user_group = containers.get_user_group(container_node)
        if managed_group is None or user_group is None:
            raise RuntimeError("The AYON container is missing its managed/user groups.")

        filepath = self._representation_path(context)
        temporary_group = None
        try:
            temporary_group = containers.create_managed_group(
                container_node,
                name=_TEMP_MANAGED_GROUP_NAME,
                role=None,
            )
            imported_nodes = self._import_graph(temporary_group, filepath)
            self._validate_update_candidate(temporary_group, user_group)
        except Exception:
            if temporary_group is not None:
                with suppress(Exception):
                    temporary_group.delete()
            raise

        containers.disconnect_managed_group_from_user(managed_group, user_group)
        containers.connect_managed_group_to_user(temporary_group, user_group)
        containers.set_managed_group_role(temporary_group)
        managed_group.delete()
        temporary_group.setName(containers.MANAGED_GROUP_NAME)

        project = context.get("project") or {}
        containers.update_container(
            container_node,
            {
                "representation": context["representation"]["id"],
                "project_name": project.get("name"),
            },
        )
        return imported_nodes

    def remove(self, container):
        """Remove an imported graph container from the Katana project."""
        container["node"].delete()

    def switch(self, container, context):
        """Switch an imported graph container to another representation."""
        self.update(container, context)
