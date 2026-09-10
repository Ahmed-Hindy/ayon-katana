"""Collect Katana USD layer export settings."""

from __future__ import annotations

import pyblish.api

from ayon_katana.api import compat, plugin
from ayon_katana.api.usd import read_usd_layer_export_settings


class CollectUsdLayer(plugin.KatanaInstancePlugin):
    """Collect the ``UsdLayerExport`` node and its settings."""

    label = "Collect USD Layer"
    order = pyblish.api.CollectorOrder + 0.01
    families = ["katana.usd"]

    def process(self, instance) -> None:
        """Collect the export node settings."""
        node_name = instance.data["instance_node"]
        export_node = compat.get_node(node_name)
        if export_node is None:
            return

        settings = read_usd_layer_export_settings(export_node)
        instance.data.update(
            {
                "usdFileFormat": settings["file_format"],
                "usdTimeSamples": settings["time_samples"],
                "usdFrameStart": settings["frame_start"],
                "usdFrameEnd": settings["frame_end"],
                "usdSamplesPerFrame": settings["samples_per_frame"],
                "usdExportMethod": settings["export_method"],
            }
        )
