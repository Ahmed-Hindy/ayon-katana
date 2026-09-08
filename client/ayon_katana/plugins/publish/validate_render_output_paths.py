"""Validate render output paths."""

import os
from collections import defaultdict

import pyblish.api
from ayon_core.pipeline import (
    OptionalPyblishPluginMixin,
    PublishValidationError,
)

from ayon_katana.api import compat, plugin, render
from ayon_katana.plugins.publish.actions import SelectInvalidOutputNodes


class ValidateRenderOutputPaths(
    plugin.KatanaInstancePlugin,
    OptionalPyblishPluginMixin,
):
    """Validate output paths are present and unique within one render graph."""

    order = pyblish.api.ValidatorOrder + 0.02
    label = "Validate Render Output Paths"
    families = ["render", "katana.render"]
    actions = [SelectInvalidOutputNodes]
    optional = True

    def process(self, instance):
        """Reject empty or duplicate paths within a render instance."""
        if not self.is_active(instance.data):
            return

        invalid = self._get_invalid_data(instance)
        if not invalid:
            return

        details = "\n".join(f"- {node.getName()}: {reason}" for node, reason in invalid)
        raise PublishValidationError(
            f"Katana render output paths are invalid:\n{details}",
            title=self.label,
        )

    @classmethod
    def get_invalid(cls, instance):
        """Return output nodes with empty or colliding paths."""
        output = []
        seen = set()
        for node, _reason in cls._get_invalid_data(instance):
            node_name = node.getName()
            if node_name in seen:
                continue
            seen.add(node_name)
            output.append(node)
        return output

    @classmethod
    def _get_invalid_data(cls, instance):
        instance_node = compat.get_node(instance.data.get("instance_node"))
        if instance_node is None:
            raise PublishValidationError("Katana render instance node is unavailable.")

        definitions_by_path = defaultdict(list)
        invalid = []
        for definition in render.get_output_definitions(instance_node):
            output_node = compat.get_node(definition.node_name)
            if output_node is None:
                continue
            if not definition.path:
                invalid.append((output_node, "output path is empty"))
                continue
            normalized_path = os.path.normcase(os.path.normpath(definition.path))
            definitions_by_path[normalized_path].append((definition, output_node))

        for items in definitions_by_path.values():
            if len(items) < 2:
                continue
            path = items[0][0].path
            names = ", ".join(
                definition.name or definition.node_name
                for definition, _output_node in items
            )
            for _definition, output_node in items:
                invalid.append(
                    (
                        output_node,
                        f"path {path!r} is shared by outputs {names}",
                    )
                )
        return invalid
