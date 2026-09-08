"""Validate render output names."""

from collections import defaultdict

import pyblish.api
from ayon_core.pipeline import (
    OptionalPyblishPluginMixin,
    PublishValidationError,
)

from ayon_katana.api import compat, plugin, render
from ayon_katana.plugins.publish.actions import SelectInvalidOutputNodes


class ValidateRenderOutputNames(
    plugin.KatanaInstancePlugin,
    OptionalPyblishPluginMixin,
):
    """Validate output names and AOV identifiers are present and unique."""

    order = pyblish.api.ValidatorOrder + 0.01
    label = "Validate Render Output Names"
    families = ["render", "katana.render"]
    actions = [SelectInvalidOutputNodes]
    optional = True

    def process(self, instance):
        """Reject missing, invalid, or duplicate render output names."""
        if not self.is_active(instance.data):
            return

        invalid = self._get_invalid_data(instance)
        if not invalid:
            return

        details = "\n".join(f"- {node.getName()}: {reason}" for node, reason in invalid)
        raise PublishValidationError(
            f"Katana render output names are invalid:\n{details}",
            title=self.label,
        )

    @classmethod
    def get_invalid(cls, instance):
        """Return output nodes with invalid names or AOV identifiers."""
        return cls._unique_nodes(
            node for node, _reason in cls._get_invalid_data(instance)
        )

    @classmethod
    def _get_invalid_data(cls, instance):
        instance_node = compat.get_node(instance.data.get("instance_node"))
        if instance_node is None:
            raise PublishValidationError("Katana render instance node is unavailable.")

        definitions = render.get_output_definitions(instance_node)
        definitions_by_name = defaultdict(list)
        definitions_by_aov = defaultdict(list)
        invalid = []
        for definition in definitions:
            output_node = compat.get_node(definition.node_name)
            if output_node is None:
                continue
            if not definition.name:
                invalid.append((output_node, "output name is empty"))
                continue
            definitions_by_name[definition.name].append((definition, output_node))
            definitions_by_aov[definition.aov_identifier].append(
                (definition, output_node)
            )

        for name, items in definitions_by_name.items():
            if len(items) < 2:
                continue
            for _definition, output_node in items:
                invalid.append((output_node, f"output name {name!r} is duplicated"))

        for aov_identifier, items in definitions_by_aov.items():
            if len(items) < 2:
                continue
            label = aov_identifier or "main"
            for _definition, output_node in items:
                invalid.append(
                    (output_node, f"multiple outputs resolve to AOV {label!r}")
                )
        return invalid

    @staticmethod
    def _unique_nodes(nodes):
        output = []
        seen = set()
        for node in nodes:
            node_name = node.getName()
            if node_name in seen:
                continue
            seen.add(node_name)
            output.append(node)
        return output
