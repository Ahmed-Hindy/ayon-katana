"""Validate render output file extensions."""

from pathlib import Path

import pyblish.api
from ayon_core.pipeline import (
    OptionalPyblishPluginMixin,
    PublishValidationError,
)

from ayon_katana.api import compat, plugin, render
from ayon_katana.plugins.publish.actions import SelectInvalidOutputNodes


class ValidateRenderOutputExtensions(
    plugin.KatanaInstancePlugin,
    OptionalPyblishPluginMixin,
):
    """Validate output paths match their native file extensions."""

    order = pyblish.api.ValidatorOrder + 0.03
    label = "Validate Render Output Extensions"
    families = ["render", "katana.render"]
    actions = [SelectInvalidOutputNodes]
    optional = True

    def process(self, instance):
        """Reject missing or mismatched render output extensions."""
        if not self.is_active(instance.data):
            return

        invalid = self._get_invalid_data(instance)
        if not invalid:
            return

        details = "\n".join(f"- {node.getName()}: {reason}" for node, reason in invalid)
        raise PublishValidationError(
            f"Katana render output extensions are invalid:\n{details}",
            title=self.label,
        )

    @classmethod
    def get_invalid(cls, instance):
        """Return output nodes with missing or mismatched extensions."""
        return [node for node, _reason in cls._get_invalid_data(instance)]

    @classmethod
    def _get_invalid_data(cls, instance):
        instance_node = compat.get_node(instance.data.get("instance_node"))
        if instance_node is None:
            raise PublishValidationError("Katana render instance node is unavailable.")

        invalid = []
        for definition in render.get_output_definitions(instance_node):
            if not definition.path:
                continue
            output_node = compat.get_node(definition.node_name)
            if output_node is None:
                continue

            path_extension = Path(definition.path).suffix.lstrip(".")
            if not path_extension or set(path_extension) == {"#"}:
                invalid.append(
                    (
                        output_node,
                        f"path {definition.path!r} has no file extension",
                    )
                )
                continue

            expected_extension = definition.extension.lstrip(".")
            if (
                expected_extension
                and path_extension.casefold() != expected_extension.casefold()
            ):
                invalid.append(
                    (
                        output_node,
                        f"path {definition.path!r} uses .{path_extension}; "
                        f"native output requires .{expected_extension}",
                    )
                )
        return invalid
