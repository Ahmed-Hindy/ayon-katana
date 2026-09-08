"""Validate authored Material prims are definitions in Katana USD looks."""

from __future__ import annotations

import pyblish.api
from ayon_core.pipeline import OptionalPyblishPluginMixin
from ayon_core.pipeline.publish import PublishValidationError

from ayon_katana.api import plugin
from ayon_katana.api.usd_look import (
    collect_invalid_material_definitions,
    get_composed_source_stage,
    is_look_instance,
    open_extracted_look_layer,
)


class ValidateUsdLookMaterialDefinitions(
    plugin.KatanaInstancePlugin,
    OptionalPyblishPluginMixin,
):
    """Validate Material prims are defined instead of overs or classes."""

    label = "Validate Look Shaders Are Defined"
    order = pyblish.api.ExtractorOrder - 0.498
    families = ["katana.usd"]
    optional = True

    def process(self, instance) -> None:
        """Validate authored Material prim definitions."""
        if not self.is_active(instance.data) or not is_look_instance(instance.data):
            return
        try:
            stage = get_composed_source_stage(instance.data)
            layer = open_extracted_look_layer(instance.data)
            invalid_materials = collect_invalid_material_definitions(layer, stage)
        except Exception as exc:
            raise PublishValidationError(
                f"Failed to inspect USD look material definitions: {exc}",
                title="USD look material inspection failed",
            ) from exc

        if invalid_materials:
            formatted = "\n".join(
                f"- {path}: authored as {specifier}"
                for path, specifier in invalid_materials.items()
            )
            raise PublishValidationError(
                "Found materials without authored definitions.\n"
                f"Invalid materials:\n{formatted}\n"
                "Define new Material prims in the look layer. If an upstream look "
                "already defines them, mute or exclude that upstream look while "
                "authoring the replacement.",
                title="Materials not defined",
            )
