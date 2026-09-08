"""Validate render output frame tokens."""

import re

import pyblish.api
from ayon_core.pipeline import (
    OptionalPyblishPluginMixin,
    PublishValidationError,
)

from ayon_katana.api import compat, plugin, render
from ayon_katana.plugins.publish.actions import SelectInvalidOutputNodes

_FRAME_TOKEN_PATTERN = re.compile(r"#+")
_UNSUPPORTED_TOKEN_PATTERN = re.compile(
    r"\$F\d*|%0?\d*d|<frame>|<f\d*>|\{frame(?::[^}]*)?\}",
    re.IGNORECASE,
)


class ValidateRenderOutputTokens(
    plugin.KatanaInstancePlugin,
    OptionalPyblishPluginMixin,
):
    """Validate sequence outputs use one consistent hash frame token."""

    order = pyblish.api.ValidatorOrder + 0.04
    label = "Validate Render Output Tokens"
    families = ["render", "katana.render"]
    actions = [SelectInvalidOutputNodes]
    optional = True

    def process(self, instance):
        """Reject output paths with invalid frame-token syntax."""
        if not self.is_active(instance.data):
            return

        invalid = self._get_invalid_data(instance)
        if not invalid:
            return

        details = "\n".join(f"- {node.getName()}: {reason}" for node, reason in invalid)
        raise PublishValidationError(
            f"Katana render output frame tokens are invalid:\n{details}",
            title=self.label,
        )

    @classmethod
    def get_invalid(cls, instance):
        """Return output nodes with invalid frame-token syntax."""
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

        frame_start = int(instance.data["frameStartHandle"])
        frame_end = int(instance.data["frameEndHandle"])
        frame_step = max(int(instance.data["byFrameStep"]), 1)
        is_sequence = len(range(frame_start, frame_end + 1, frame_step)) > 1

        invalid = []
        token_items = []
        for definition in render.get_output_definitions(instance_node):
            if not definition.path:
                continue
            output_node = compat.get_node(definition.node_name)
            if output_node is None:
                continue

            unsupported = _UNSUPPORTED_TOKEN_PATTERN.search(definition.path)
            if unsupported:
                invalid.append(
                    (
                        output_node,
                        f"path {definition.path!r} uses unsupported token "
                        f"{unsupported.group(0)!r}; use one # token",
                    )
                )
                continue

            tokens = _FRAME_TOKEN_PATTERN.findall(definition.path)
            if len(tokens) > 1:
                invalid.append(
                    (
                        output_node,
                        f"path {definition.path!r} contains multiple # tokens; "
                        "exactly one is allowed",
                    )
                )
                continue
            if is_sequence and not tokens:
                invalid.append(
                    (
                        output_node,
                        f"sequence path {definition.path!r} has no # frame token",
                    )
                )
                continue
            if tokens:
                token_items.append((output_node, definition.path, len(tokens[0])))

        padding_values = {padding for _node, _path, padding in token_items}
        if len(padding_values) > 1:
            expected = ", ".join(str(value) for value in sorted(padding_values))
            for output_node, path, padding in token_items:
                invalid.append(
                    (
                        output_node,
                        f"path {path!r} uses {padding} # characters; all outputs "
                        f"must use consistent padding ({expected})",
                    )
                )
        return invalid
