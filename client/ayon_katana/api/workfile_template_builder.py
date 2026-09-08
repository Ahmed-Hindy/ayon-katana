"""AYON Workfile Builder integration for Katana."""

from __future__ import annotations

import logging
from typing import Any, Optional

from ayon_core.pipeline import registered_host
from ayon_core.pipeline.workfile.workfile_template_builder import (
    AbstractTemplateBuilder,
    PlaceholderPlugin,
    TemplateProfileNotFound,
)
from Katana import NodegraphAPI

from . import compat, containers, lib

log = logging.getLogger("ayon_katana.workfile_builder")

_PLACEHOLDER_PARAMETER = "user.ayon.placeholder.data"
_PLACEHOLDER_SCHEMA = "ayon:placeholder-1.0"
_PLACEHOLDER_ROLE_PARAMETER = "user.ayon.placeholder.role"
_COMBINE_ROLE = "combine"
_COMBINE_NAME = "AYON_PLACEHOLDER_MERGE"


def _node_from_identifier(scene_identifier: str):
    """Return a Katana node from a Workfile Builder scene identifier.

    Args:
        scene_identifier: Globally unique Katana node name.

    Returns:
        Katana node, or ``None`` when it no longer exists.
    """
    return compat.get_node(scene_identifier)


class KatanaTemplateBuilder(AbstractTemplateBuilder):
    """Implement the AYON Workfile Builder contract for Katana."""

    def import_template(self, path):
        """Import a Katana template into the current project.

        Args:
            path: Template ``.katana`` path.

        Returns:
            ``True`` when Katana imported the template.
        """
        try:
            compat.import_katana_file(path, float_nodes=False)
        except (OSError, RuntimeError, ValueError):
            log.warning("Failed to import Katana template: %s", path, exc_info=True)
            return False
        return True


class KatanaPlaceholderPlugin(PlaceholderPlugin):
    """Provide shared Katana behavior for Workfile Builder placeholders.

    Inherited classes must still implement ``populate_placeholder``.
    """

    def get_placeholder_node_name(self, placeholder_data) -> str:
        """Return a stable Katana node name for placeholder metadata."""
        product_name = placeholder_data.get("product_name") or "product"
        return lib.sanitize_node_name(
            f"AYON_PLACEHOLDER_{product_name}",
            "AYON_PLACEHOLDER",
        )

    def create_placeholder_node(self, node_name=None):
        """Create node to be used as placeholder."""
        placeholder_node = NodegraphAPI.CreateNode("Group", NodegraphAPI.GetRootNode())
        placeholder_node.setName(node_name)
        placeholder_node.addOutputPort("out")
        self.ensure_combine_node(placeholder_node)
        return placeholder_node

    def create_placeholder(self, placeholder_data):
        """Create and imprint a Workfile Builder placeholder node."""
        data = dict(placeholder_data)
        data["plugin_identifier"] = self.identifier
        node_name = self.get_placeholder_node_name(data)
        placeholder_node = self.create_placeholder_node(node_name)
        self._imprint(placeholder_node, data)
        return placeholder_node

    def update_placeholder(self, placeholder_item, placeholder_data):
        """Update a placeholder node and its in-memory item."""
        placeholder_node = _node_from_identifier(placeholder_item.scene_identifier)
        if placeholder_node is None:
            raise RuntimeError(
                f"Katana placeholder no longer exists: "
                f"{placeholder_item.scene_identifier}"
            )

        data = dict(placeholder_data)
        data["plugin_identifier"] = self.identifier
        self._imprint(placeholder_node, data, update=True)
        placeholder_node.setName(self.get_placeholder_node_name(data))
        placeholder_item.data.clear()
        placeholder_item.data.update(data)

    def collect_scene_placeholders(self) -> list:
        """Return cached placeholder Group nodes from the current project."""
        cached_nodes = self.builder.get_shared_populate_data("placeholder_nodes")
        if cached_nodes is not None:
            return cached_nodes

        placeholder_nodes = []
        for node in NodegraphAPI.GetAllNodesByType("Group"):
            data = self._read(node)
            if data:
                placeholder_nodes.append(node)
        self.builder.set_shared_populate_data("placeholder_nodes", placeholder_nodes)
        return placeholder_nodes

    def _imprint(self, placeholder_node, placeholder_data, update=False):
        data = dict(placeholder_data)
        data.setdefault("schema", _PLACEHOLDER_SCHEMA)
        lib.write_json_parameter(
            placeholder_node,
            _PLACEHOLDER_PARAMETER,
            data,
            skip_unchanged=update,
        )

    def _read(self, placeholder_node) -> Optional[dict[str, Any]]:
        """Read placeholder metadata from a Katana Group."""
        return lib.read_json_parameter(
            placeholder_node,
            _PLACEHOLDER_PARAMETER,
        )

    def clear_placeholder(self, placeholder_node) -> None:
        """Remove placeholder semantics while keeping its graph Group.

        Args:
            placeholder_node: Placeholder Group to consume.
        """
        lib.set_string_parameter(placeholder_node, _PLACEHOLDER_PARAMETER, "")
        name = placeholder_node.getName()
        if "PLACEHOLDER" in name:
            name = name.replace("PLACEHOLDER", "LOADED", 1)
        else:
            name = f"{name}_LOADED"
        placeholder_node.setName(
            lib.sanitize_node_name(name, "AYON_PLACEHOLDER_LOADED")
        )

    def ensure_combine_node(self, placeholder_node):
        """Return the Merge node combining loaded placeholder products.

        Args:
            placeholder_node: Placeholder Group.

        Returns:
            Native Katana Merge node.
        """
        for child in placeholder_node.getChildren():
            role = lib.get_string_parameter(child, _PLACEHOLDER_ROLE_PARAMETER)
            if role == _COMBINE_ROLE:
                return child

        combine_node = NodegraphAPI.CreateNode("Merge", placeholder_node)
        combine_node.setName(_COMBINE_NAME)
        lib.set_string_parameter(
            combine_node,
            _PLACEHOLDER_ROLE_PARAMETER,
            _COMBINE_ROLE,
        )
        combine_node.getOutputPort("out").connect(placeholder_node.getReturnPort("out"))
        return combine_node

    def connect_loaded_container(self, placeholder_node, container_node) -> None:
        """Move a loaded container into a placeholder and connect its output.

        Args:
            placeholder_node: Destination placeholder Group.
            container_node: AYON container Group returned by a loader.
        """
        combine_node = self.ensure_combine_node(placeholder_node)
        compat.set_parent(container_node, placeholder_node)

        input_port = next(
            (
                port
                for port in combine_node.getInputPorts()
                if not port.getConnectedPorts()
            ),
            None,
        )
        if input_port is None:
            input_port = combine_node.addInputPort(
                f"i{len(combine_node.getInputPorts())}"
            )
        container_node.getOutputPort("out").connect(input_port)

        index = len(self.get_loaded_containers(placeholder_node)) - 1
        NodegraphAPI.SetNodePosition(container_node, (-250.0, index * 120.0))
        NodegraphAPI.SetNodePosition(combine_node, (100.0, 0.0))

    def get_loaded_containers(self, placeholder_node) -> list:
        """Return AYON containers nested beneath a placeholder Group.

        Args:
            placeholder_node: Placeholder Group.

        Returns:
            Parsed AYON container dictionaries.
        """
        loaded_containers = []
        for node in NodegraphAPI.GetAllNodesByType("Group"):
            if not compat.is_descendant(node, placeholder_node):
                continue
            container = containers.parse_container(node)
            if container is not None:
                loaded_containers.append(container)
        return loaded_containers

    def get_loaded_representation_ids(self, placeholder_node) -> set[str]:
        """Return representation IDs already loaded by a placeholder.

        Args:
            placeholder_node: Placeholder Group.

        Returns:
            Set of AYON representation IDs.
        """
        return {
            container["representation"]
            for container in self.get_loaded_containers(placeholder_node)
            if container.get("representation")
        }

    def delete_placeholder(self, placeholder) -> None:
        """Consume or delete a completed placeholder.

        Loaded containers remain beneath a stable Group so external template
        connections are preserved. Empty placeholders are deleted normally.

        Args:
            placeholder: AYON placeholder item.
        """
        placeholder_node = _node_from_identifier(placeholder.scene_identifier)
        if placeholder_node is None:
            return
        if self.get_loaded_containers(placeholder_node):
            self.clear_placeholder(placeholder_node)
            return
        placeholder_node.delete()


def trigger_on_app_launch() -> bool:
    """Run the Core Workfile Builder application-launch trigger.

    Returns:
        ``True`` when a matching profile was evaluated, otherwise ``False``.
    """
    builder = KatanaTemplateBuilder(registered_host())
    try:
        builder.trigger_on_app_launch()
    except TemplateProfileNotFound:
        log.info("No Katana Workfile Builder profile matches the current task.")
        return False
    return True


def trigger_on_new_file() -> bool:
    """Run the Core Workfile Builder new-file trigger.

    Returns:
        ``True`` when a matching profile was evaluated, otherwise ``False``.
    """
    builder = KatanaTemplateBuilder(registered_host())
    try:
        builder.trigger_on_new_file()
    except TemplateProfileNotFound:
        log.info("No Katana Workfile Builder profile matches the current task.")
        return False
    return True


def build_workfile_template(*args, **kwargs) -> bool:
    """Build the matching template explicitly in the current scene.

    Returns:
        ``True`` when a valid matching template was built.
    """
    builder = KatanaTemplateBuilder(registered_host())
    try:
        preset = builder.get_template_preset()
    except TemplateProfileNotFound:
        log.info("No Katana Workfile Builder profile matches the current task.")
        return False
    if not preset.has_valid_path():
        log.warning(
            "Katana Workfile Builder template path is unavailable: %s",
            preset.path,
        )
        return False
    builder.build_template(preset=preset)
    return True


def update_workfile_template(*args):
    """Rebuild the current project from its matching template profile."""
    builder = KatanaTemplateBuilder(registered_host())
    builder.rebuild_template()


def open_workfile_template(*args) -> None:
    """Open the matching template after Core's destructive-action prompt."""
    from ayon_core.tools.workfile_template_build import open_template_ui

    from .menu import get_main_window

    builder = KatanaTemplateBuilder(registered_host())
    open_template_ui(builder, get_main_window())


def create_placeholder(*args):
    """Open the Workfile Builder dialog in create-placeholder mode."""
    from ayon_core.tools.workfile_template_build import (
        WorkfileBuildPlaceholderDialog,
    )

    from .menu import get_main_window

    host = registered_host()
    builder = KatanaTemplateBuilder(host)
    window = WorkfileBuildPlaceholderDialog(host, builder, parent=get_main_window())
    window.show()


def update_placeholder(*args):
    """Open the Workfile Builder dialog for one selected placeholder."""
    from ayon_core.tools.utils import show_message_dialog
    from ayon_core.tools.workfile_template_build import (
        WorkfileBuildPlaceholderDialog,
    )

    from .menu import get_main_window

    host = registered_host()
    builder = KatanaTemplateBuilder(host)
    placeholder_items_by_id = {
        placeholder_item.scene_identifier: placeholder_item
        for placeholder_item in builder.get_placeholders()
    }
    placeholder_items = []
    for node in compat.get_selected_nodes():
        if node.getName() in placeholder_items_by_id:
            placeholder_items.append(placeholder_items_by_id[node.getName()])

    parent = get_main_window()
    if len(placeholder_items) == 0:
        show_message_dialog(
            "Workfile Placeholder Manager",
            "Select one Katana placeholder Group.",
            "warning",
            parent,
        )
        return
    if len(placeholder_items) > 1:
        show_message_dialog(
            "Workfile Placeholder Manager",
            "Select only one Katana placeholder Group.",
            "warning",
            parent,
        )
        return

    placeholder_item = placeholder_items[0]
    window = WorkfileBuildPlaceholderDialog(host, builder, parent=parent)
    window.set_update_mode(placeholder_item)
    window.exec_()
