"""Validate Katana Viewer Scene Review capture readiness."""

from __future__ import annotations

import pyblish.api
from ayon_core.pipeline import OptionalPyblishPluginMixin
from ayon_core.pipeline.publish import PublishValidationError

from ayon_katana.api import plugin, review, thumbnail


class ValidateReview(
    plugin.KatanaInstancePlugin,
    OptionalPyblishPluginMixin,
):
    """Validate that a review range and an unambiguous visible Viewer exist."""

    label = "Validate Scene Review"
    order = pyblish.api.ValidatorOrder
    families = ["review", "katana.review"]
    optional = False

    def process(self, instance) -> None:
        """Validate the captured range, FPS, and Viewer selection."""
        if not self.is_active(instance.data):
            return

        try:
            review.frame_numbers(
                int(instance.data["frameStartHandle"]),
                int(instance.data["frameEndHandle"]),
                int(instance.data["byFrameStep"]),
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise PublishValidationError(
                f"Scene Review has an invalid frame range: {exc}",
                title="Scene Review range invalid",
            ) from exc

        try:
            fps = float(instance.data["fps"])
        except (KeyError, TypeError, ValueError) as exc:
            raise PublishValidationError(
                "Scene Review requires a valid AYON task FPS.",
                title="Scene Review FPS missing",
            ) from exc
        if fps <= 0:
            raise PublishValidationError(
                "Scene Review requires a positive AYON task FPS.",
                title="Scene Review FPS invalid",
            )

        viewer_widget, reason = thumbnail.select_viewer_widget()
        if viewer_widget is None:
            raise PublishValidationError(
                f"Scene Review cannot select a Katana Viewer: {reason}.",
                title="Scene Review Viewer unavailable",
            )
