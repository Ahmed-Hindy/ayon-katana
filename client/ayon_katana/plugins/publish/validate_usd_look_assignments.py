"""Validate composed geometry material assignments for Katana USD looks."""

from __future__ import annotations

import pyblish.api
from ayon_core.pipeline import OptionalPyblishPluginMixin
from ayon_core.pipeline.publish import PublishValidationError

from ayon_katana.api import plugin
from ayon_katana.api.usd_look import (
    collect_unbound_geometry_paths,
    get_composed_source_stage,
    is_look_instance,
)


class ValidateUsdLookAssignments(
    plugin.KatanaInstancePlugin,
    OptionalPyblishPluginMixin,
):
    """Validate all geometry prims have a material binding."""

    label = "Validate All Geometry Has Material Assignment"
    order = pyblish.api.ExtractorOrder - 0.498
    families = ["katana.usd"]
    optional = True

    def process(self, instance) -> None:
        """Validate material bindings on composed geometry."""
        if not self.is_active(instance.data) or not is_look_instance(instance.data):
            return
        try:
            stage = get_composed_source_stage(instance.data)
            invalid_paths = collect_unbound_geometry_paths(stage)
        except Exception as exc:
            raise PublishValidationError(
                f"Failed to inspect the composed USD look stage: {exc}",
                title="USD look stage inspection failed",
            ) from exc

        if invalid_paths:
            formatted = "\n".join(f"- {path}" for path in invalid_paths)
            raise PublishValidationError(
                "Found geometry without material bindings.\n"
                f"Unbound geometry:\n{formatted}\n"
                "Bind a material directly or through a material-binding subset "
                "using full, preview, or allPurpose.",
                title="No assigned materials",
            )
