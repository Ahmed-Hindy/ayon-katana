"""Validate ImageWrite outputs before publishing."""

from __future__ import annotations

from pathlib import Path

import pyblish.api
from ayon_core.pipeline import OptionalPyblishPluginMixin
from ayon_core.pipeline.publish import PublishValidationError

from ayon_katana.api import compat, plugin
from ayon_katana.api.image import (
    IMAGE_FILE_FORMATS,
    expand_image_output_pattern,
    read_image_write_settings,
)


class ValidateImage(
    plugin.KatanaInstancePlugin,
    OptionalPyblishPluginMixin,
):
    """Validate ImageWrite connectivity, output, range, and review colorspace."""

    label = "Validate ImageWrite"
    order = pyblish.api.ValidatorOrder
    families = ["image", "katana.image"]
    optional = False

    def process(self, instance) -> None:
        """Validate the node, connection, and output settings."""
        if not self.is_active(instance.data):
            return
        node_name = instance.data["instance_node"]
        image_write_node = compat.get_node(node_name)
        if image_write_node is None:
            raise PublishValidationError(
                f"Katana ImageWrite node does not exist: {node_name!r}",
                title="ImageWrite node missing",
            )
        if image_write_node.getType() != "ImageWrite":
            raise PublishValidationError(
                "Image publish instance is not an ImageWrite node.",
                title="ImageWrite node invalid",
            )
        input_port = image_write_node.getInputPort("in")
        connected_ports = (
            list(input_port.getConnectedPorts()) if input_port is not None else []
        )
        if len(connected_ports) != 1:
            raise PublishValidationError(
                "ImageWrite requires exactly one source on its 'in' port.",
                title="ImageWrite source missing",
            )

        try:
            settings = read_image_write_settings(image_write_node)
        except Exception as exc:
            raise PublishValidationError(
                f"Failed to read ImageWrite settings: {exc}",
                title="ImageWrite settings invalid",
            ) from exc
        if not settings["output_path"]:
            raise PublishValidationError(
                "ImageWrite has no output path.",
                title="ImageWrite output missing",
            )
        if settings["file_format"] not in IMAGE_FILE_FORMATS:
            raise PublishValidationError(
                f"Unsupported ImageWrite format: {settings['file_format']!r}.",
                title="ImageWrite format invalid",
            )
        extension = Path(settings["output_path"]).suffix.lower().lstrip(".")
        if extension != settings["file_format"]:
            raise PublishValidationError(
                "ImageWrite path extension does not match its file format.",
                title="ImageWrite format mismatch",
            )

        frame_start = int(instance.data["frameStartHandle"])
        frame_end = int(instance.data["frameEndHandle"])
        frame_step = int(instance.data["byFrameStep"])
        try:
            expected_files = expand_image_output_pattern(
                settings["output_path"],
                frame_start,
                frame_end,
                frame_step,
            )
        except ValueError as exc:
            raise PublishValidationError(
                str(exc),
                title="ImageWrite frame pattern invalid",
            ) from exc
        collected_files = (instance.data.get("expectedFiles") or [{}])[0].get("", [])
        if expected_files != collected_files:
            raise PublishValidationError(
                "ImageWrite expected files are stale; recollect the instance.",
                title="ImageWrite output stale",
            )

        review = bool(
            (instance.data.get("creator_attributes") or {}).get("review", False)
        )
        if review and not str(instance.data.get("imageOutputColorspace") or "").strip():
            raise PublishValidationError(
                "Review images require an explicit ImageWrite output colorspace.",
                title="Review colorspace missing",
            )
