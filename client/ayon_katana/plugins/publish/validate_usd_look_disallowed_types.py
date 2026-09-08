"""Reject authored geometry and composition arcs in Katana USD looks."""

from __future__ import annotations

import pyblish.api
from ayon_core.pipeline.publish import PublishValidationError

from ayon_katana.api import plugin
from ayon_katana.api.usd_look import (
    collect_disallowed_authored_look_items,
    is_look_instance,
    open_extracted_look_layer,
)


class ValidateUsdLookDisallowedTypes(plugin.KatanaInstancePlugin):
    """Validate the look does not define disallowed content."""

    label = "Validate Look No Disallowed Types"
    order = pyblish.api.ExtractorOrder - 0.498
    families = ["katana.usd"]
    optional = False

    def process(self, instance) -> None:
        """Validate authored look content."""
        if not is_look_instance(instance.data):
            return
        try:
            layer = open_extracted_look_layer(instance.data)
            invalid_items = collect_disallowed_authored_look_items(layer)
        except Exception as exc:
            raise PublishValidationError(
                f"Failed to inspect the extracted USD look layer: {exc}",
                title="USD look layer inspection failed",
            ) from exc

        if invalid_items:
            formatted = "\n".join(
                f"- {path}: {'; '.join(reasons)}"
                for path, reasons in invalid_items.items()
            )
            raise PublishValidationError(
                "Invalid look members found.\n"
                f"Invalid authored prims:\n{formatted}\n"
                "Author only materials, bindings, and render-geometry settings in "
                "the look layer. Keep geometry, cameras, render settings, references, "
                "and payloads in upstream composition layers.",
                title="Look Invalid Members",
            )
