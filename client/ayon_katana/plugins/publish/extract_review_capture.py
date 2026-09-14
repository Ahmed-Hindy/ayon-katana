"""Capture the active Katana Viewer as a review image sequence."""

from __future__ import annotations

import math
from pathlib import Path

import pyblish.api
from ayon_core.pipeline.publish import PublishError

from ayon_katana.api import plugin, review, thumbnail


class ExtractReviewCapture(plugin.KatanaExtractorPlugin):
    """Create the source PNG sequence consumed by AYON Core ExtractReview."""

    label = "Extract Scene Review Capture"
    order = pyblish.api.ExtractorOrder - 0.1
    families = ["review", "katana.review"]
    frame_padding = 4

    def process(self, instance) -> None:
        """Capture every review frame from one unambiguous visible Viewer."""
        try:
            frame_start = int(instance.data["frameStartHandle"])
            frame_end = int(instance.data["frameEndHandle"])
            frame_step = int(instance.data["byFrameStep"])
        except (KeyError, TypeError, ValueError) as exc:
            raise PublishError("Scene Review frame data was not collected.") from exc

        try:
            fps = float(instance.data["fps"])
        except (KeyError, TypeError, ValueError) as exc:
            raise PublishError("Scene Review FPS was not collected.") from exc
        if not math.isfinite(fps) or fps <= 0:
            raise PublishError("Scene Review requires a finite positive AYON task FPS.")

        viewer_widget, reason = thumbnail.select_viewer_widget()
        if viewer_widget is None:
            raise PublishError(f"Scene Review cannot select a Katana Viewer: {reason}.")

        staging_dir = Path(self.staging_dir(instance))
        product_name = str(instance.data.get("productName") or "review")
        try:
            filenames = review.capture_viewer_sequence(
                viewer_widget,
                staging_dir,
                product_name,
                frame_start,
                frame_end,
                frame_step,
                frame_padding=self.frame_padding,
            )
        except Exception as exc:
            raise PublishError(f"Katana Viewer review capture failed: {exc}") from exc
        if not filenames:
            raise PublishError("Katana Viewer review capture produced no frames.")

        representation = {
            "name": "png",
            "ext": "png",
            "files": filenames,
            "stagingDir": str(staging_dir),
            "tags": ["review"],
            "frameStart": frame_start,
            "frameEnd": frame_end,
            "fps": fps,
        }
        instance.data.setdefault("representations", []).append(representation)
        self.log.info(
            "Captured %d Katana Viewer review frames to %s.",
            len(filenames),
            staging_dir,
        )
