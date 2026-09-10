"""Extract Katana USD layers into AYON representations."""

from __future__ import annotations

from pathlib import Path

import pyblish.api
from ayon_core.pipeline.publish import PublishError

from ayon_katana.api import compat, plugin
from ayon_katana.api.usd import export_usd_layer, read_usd_layer_export_settings


class ExtractUsdLayer(plugin.KatanaExtractorPlugin):
    """Write a USD representation with ``UsdLayerExport.write``."""

    label = "Extract USD Layer"
    # UsdLayerExport temporarily edits its parameters. Run before
    # SaveCurrentScene so restored values are saved before workfile staging.
    order = pyblish.api.ExtractorOrder - 0.5
    families = ["katana.usd"]

    def process(self, instance) -> None:
        """Export the USD layer into the instance staging path."""
        node_name = instance.data["instance_node"]
        export_node = compat.get_node(node_name)
        if export_node is None:
            raise PublishError(f"Katana USD export node does not exist: {node_name!r}")

        existing_representations = instance.data.get("representations") or []
        if existing_representations:
            raise PublishError("USD layer instance already has representations.")

        settings = read_usd_layer_export_settings(export_node)
        file_format = settings["file_format"]
        product_name = instance.data.get("productName") or export_node.getName()
        filename = f"{product_name}.{file_format}"
        staging_dir = Path(self.staging_dir(instance))
        destination = staging_dir / filename
        try:
            export_usd_layer(export_node, destination)
        except Exception as exc:
            raise PublishError(
                f"Katana USD layer export failed for {product_name!r}: {exc}"
            ) from exc

        instance.data["stagingDir"] = str(staging_dir)
        instance.data["representations"] = [
            {
                "name": "usd",
                "ext": file_format,
                "files": filename,
                "stagingDir": str(staging_dir),
            }
        ]
        instance.data["setMembers"] = [destination.as_posix()]
        self.log.info("Exported USD layer: %s", destination)
