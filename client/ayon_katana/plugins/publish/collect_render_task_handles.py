"""Collector plugin for frame data on Katana render instances."""

from __future__ import annotations

import pyblish.api
from ayon_core.lib import BoolDef
from ayon_core.pipeline import AYONPyblishPluginMixin

from ayon_katana.api import plugin


def _handle_value(attributes: dict, name: str) -> int:
    value = attributes.get(name, 0)
    try:
        return int(value or 0)
    except (TypeError, ValueError) as exc:
        raise RuntimeError(
            f"AYON {name} handle is not a whole number: {value!r}"
        ) from exc


class CollectAssetHandles(
    plugin.KatanaInstancePlugin,
    AYONPyblishPluginMixin,
):
    """Apply instance's task entity handles.

    If the instance has a handle-inclusive native render range, retrieve the
    task handles to compute the exclusive frame range and actual handle values.
    """

    label = "Collect Task Handles"
    order = pyblish.api.CollectorOrder + 0.499
    families = ["render", "katana.render"]
    use_asset_handles = True

    def process(self, instance):
        """Apply optional task handles to the render frame range."""
        if "frameStartHandle" not in instance.data:
            return
        if "frameEndHandle" not in instance.data:
            return

        attr_values = self.get_attr_values_from_data(instance.data)
        use_handles = bool(attr_values.get("use_handles", self.use_asset_handles))
        entity = instance.data.get("taskEntity") or instance.data.get("folderEntity")
        attributes = (entity or {}).get("attrib") or {}
        handle_start = _handle_value(attributes, "handleStart") if use_handles else 0
        handle_end = _handle_value(attributes, "handleEnd") if use_handles else 0
        frame_start = int(instance.data["frameStartHandle"]) + handle_start
        frame_end = int(instance.data["frameEndHandle"]) - handle_end
        instance.data.update(
            {
                "handleStart": handle_start,
                "handleEnd": handle_end,
                "frameStart": frame_start,
                "frameEnd": frame_end,
            }
        )

    @classmethod
    def get_attr_defs_for_instance(cls, create_context, instance):
        """Return task-handle controls for a render creator instance."""
        if not cls.instance_matches_plugin_families(instance):
            return []
        return [
            BoolDef(
                "use_handles",
                label="Use task handles",
                default=cls.use_asset_handles,
                tooltip=(
                    "Apply task handles while deriving the AYON cut range "
                    "from Katana's native Render range."
                ),
            )
        ]
