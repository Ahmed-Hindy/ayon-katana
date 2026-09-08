"""Load products into Katana Workfile Builder placeholders."""

from __future__ import annotations

from ayon_core.pipeline.workfile.workfile_template_builder import (
    LoadPlaceholderItem,
    PlaceholderLoadMixin,
)

from ayon_katana.api import compat
from ayon_katana.api.workfile_template_builder import KatanaPlaceholderPlugin


class KatanaPlaceholderLoadPlugin(KatanaPlaceholderPlugin, PlaceholderLoadMixin):
    """Replace Workfile Builder load placeholders with AYON products."""

    identifier = "ayon.load.placeholder"
    label = "Katana Load"

    def populate_placeholder(self, placeholder):
        """Populate a load placeholder."""
        self.populate_load_placeholder(placeholder)

    def repopulate_placeholder(self, placeholder):
        """Populate a placeholder while preserving existing representations."""
        placeholder_node = self._get_placeholder_node(placeholder)
        loaded_ids = self.get_loaded_representation_ids(placeholder_node)
        self.populate_load_placeholder(placeholder, loaded_ids)

    def get_placeholder_options(self, options=None):
        """Return the Workfile Builder load options."""
        return self.get_load_plugin_options(options)

    def collect_placeholders(self):
        """Return load placeholders stored in the current Katana project."""
        output = []
        load_placeholders = self.collect_scene_placeholders()
        for node in load_placeholders:
            placeholder_data = self._read(node)
            if not placeholder_data:
                continue
            if placeholder_data.get("plugin_identifier") != self.identifier:
                continue
            output.append(LoadPlaceholderItem(node.getName(), placeholder_data, self))
        return output

    def load_succeed(self, placeholder, container):
        """Connect a successfully loaded container to its placeholder."""
        placeholder_node = self._get_placeholder_node(placeholder)
        container_node = (
            container.get("node") if isinstance(container, dict) else container
        )
        if container_node is None:
            raise RuntimeError("The Katana loader did not return a container node.")
        self.connect_loaded_container(placeholder_node, container_node)

    @staticmethod
    def _get_placeholder_node(placeholder):
        """Resolve a placeholder's Katana node."""
        placeholder_node = compat.get_node(placeholder.scene_identifier)
        if placeholder_node is None:
            raise RuntimeError(
                f"Katana placeholder no longer exists: {placeholder.scene_identifier}"
            )
        return placeholder_node
