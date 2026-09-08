"""Validate Katana render frames after applying task handles."""

from __future__ import annotations

import pyblish.api
from ayon_core.pipeline import PublishValidationError
from ayon_core.pipeline.publish import RepairAction

from ayon_katana.api import plugin
from ayon_katana.plugins.publish.actions import SelectInvalidInstanceNodes


class DisableUseTaskHandlesAction(RepairAction):
    """Disable task handles on a render creator instance."""

    label = "Disable use task handles"
    icon = "mdi.toggle-switch-off"


class ValidateFrameRange(plugin.KatanaInstancePlugin):
    """Validate Frame Range.

    Due to the usage of start and end handles, the cut frame range must remain
    valid after handles are applied to the native Katana render range.
    """

    label = "Validate Frame Range"
    order = pyblish.api.ValidatorOrder - 0.1
    families = ["render", "katana.render"]
    actions = [DisableUseTaskHandlesAction, SelectInvalidInstanceNodes]

    def process(self, instance):
        """Reject native or handled frame ranges that cannot be rendered."""
        frame_start_handle = int(instance.data["frameStartHandle"])
        frame_end_handle = int(instance.data["frameEndHandle"])
        frame_step = int(instance.data["byFrameStep"])
        if frame_end_handle < frame_start_handle:
            raise PublishValidationError(
                "Katana native frame end is before its native frame start."
            )
        if frame_step < 1:
            raise PublishValidationError("Katana frame step must be at least 1.")
        if self.get_invalid(instance):
            raise PublishValidationError(
                title="Invalid Frame Range",
                message=(
                    "Invalid frame range because the instance start frame "
                    f"({instance.data['frameStart']}) is higher than the end "
                    f"frame ({instance.data['frameEnd']})."
                ),
                description=(
                    "## Invalid Frame Range\n"
                    "The frame range is invalid after task handles were applied. "
                    "Disable task handles or extend the native Katana Render range."
                ),
            )

    @classmethod
    def get_invalid(cls, instance):
        """Return the instance when its handled frame range is reversed."""
        frame_start = instance.data.get("frameStart")
        frame_end = instance.data.get("frameEnd")
        if frame_start is None or frame_end is None:
            return []
        if frame_start > frame_end:
            return [instance]
        return []

    @classmethod
    def repair(cls, instance):
        """Disable task handles on an invalid creator instance."""
        if not cls.get_invalid(instance):
            return

        context = instance.context
        create_context = context.data.get("create_context")
        if create_context is None:
            cls.log.warning(
                "Create context is unavailable; task handles were not changed."
            )
            return

        instance_id = instance.data.get("instance_id")
        if not instance_id:
            cls.log.warning("Publish instance has no creator instance id.")
            return

        created_instance = create_context.get_instance_by_id(instance_id)
        if created_instance is None:
            cls.log.warning("Creator instance %s was not found.", instance_id)
            return

        created_instance.publish_attributes["CollectAssetHandles"]["use_handles"] = (
            False
        )
        create_context.save_changes()
