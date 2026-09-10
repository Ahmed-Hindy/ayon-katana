"""Validate Katana USD layer instances."""

from __future__ import annotations

import pyblish.api
from ayon_core.pipeline import OptionalPyblishPluginMixin
from ayon_core.pipeline.publish import PublishValidationError

from ayon_katana.api import compat, plugin
from ayon_katana.api.usd import (
    USD_EXPORT_METHODS,
    USD_FILE_FORMATS,
    USD_TIME_SAMPLE_MODES,
    is_native_usd_node,
    read_usd_layer_export_settings,
)


class ValidateUsdLayer(
    plugin.KatanaInstancePlugin,
    OptionalPyblishPluginMixin,
):
    """Validate ``UsdLayerExport`` nodes and settings."""

    label = "Validate USD Layer"
    order = pyblish.api.ValidatorOrder
    families = ["katana.usd"]
    optional = False

    def process(self, instance) -> None:
        """Validate the export node, source, and settings."""
        if not self.is_active(instance.data):
            return

        node_name = instance.data["instance_node"]
        export_node = compat.get_node(node_name)
        if export_node is None:
            raise PublishValidationError(
                f"Katana USD export node does not exist: {node_name!r}",
                title="USD export node missing",
            )
        if export_node.getType() != "UsdLayerExport":
            raise PublishValidationError(
                "USD publish instance is not a UsdLayerExport node.",
                title="USD export node invalid",
            )

        input_port = export_node.getInputPort("in")
        connected_ports = (
            list(input_port.getConnectedPorts()) if input_port is not None else []
        )
        if len(connected_ports) != 1:
            raise PublishValidationError(
                "UsdLayerExport requires exactly one native USD source on its "
                "'in' port.",
                title="USD source missing",
            )
        source_node = connected_ports[0].getNode()
        if not is_native_usd_node(source_node):
            raise PublishValidationError(
                f"UsdLayerExport source {source_node.getName()!r} is not a "
                f"native USD node (type: {source_node.getType()!r}). Connect "
                "a node with Katana's 'nativeusd' flavor.",
                title="USD source is not native",
            )

        try:
            settings = read_usd_layer_export_settings(export_node)
        except Exception as exc:
            raise PublishValidationError(
                f"Failed to read UsdLayerExport settings: {exc}",
                title="USD export settings invalid",
            ) from exc
        if settings["file_format"] not in USD_FILE_FORMATS:
            raise PublishValidationError(
                f"Unsupported USD file format: {settings['file_format']!r}.",
                title="USD format invalid",
            )
        if settings["time_samples"] not in USD_TIME_SAMPLE_MODES:
            raise PublishValidationError(
                f"Unsupported USD time sampling: {settings['time_samples']!r}.",
                title="USD time sampling invalid",
            )
        if settings["export_method"] not in USD_EXPORT_METHODS:
            raise PublishValidationError(
                f"Unsupported USD export method: {settings['export_method']!r}.",
                title="USD export method invalid",
            )
        if settings["samples_per_frame"] <= 0:
            raise PublishValidationError(
                "USD samples per frame must be greater than zero.",
                title="USD time sampling invalid",
            )
        if (
            settings["time_samples"] == "Frame Range"
            and settings["frame_end"] < settings["frame_start"]
        ):
            raise PublishValidationError(
                "USD frame range end is before its start.",
                title="USD frame range invalid",
            )
