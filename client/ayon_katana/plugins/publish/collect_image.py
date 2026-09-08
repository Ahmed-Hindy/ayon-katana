"""Collect Katana ImageWrite publish data."""

from __future__ import annotations

from pathlib import Path

import pyblish.api

from ayon_katana.api import colorspace, compat, lib, plugin, render
from ayon_katana.api.image import (
    expand_image_output_pattern,
    read_image_write_settings,
)


class CollectImage(plugin.KatanaInstancePlugin):
    """Collect one ImageWrite output for local or farm processing."""

    label = "Collect ImageWrite"
    order = pyblish.api.CollectorOrder + 0.410
    families = ["image", "katana.image"]

    def process(self, instance) -> None:
        """Collect live node settings, range, expected files, and metadata."""
        transient_data = instance.data.get("transientData") or {}
        image_write_node = transient_data.get("node")
        if image_write_node is not None:
            try:
                node_name = image_write_node.getName()
            except Exception:
                image_write_node = None
        if image_write_node is None:
            node_name = instance.data.get("image_write_node") or instance.data.get(
                "instance_node"
            )
            image_write_node = compat.get_node(str(node_name)) if node_name else None
        if image_write_node is None:
            raise RuntimeError(
                f"Katana ImageWrite instance node does not exist: {node_name!r}"
            )

        node_name = image_write_node.getName()
        instance.data.update(
            {
                "instance_node": node_name,
                "image_write_node": node_name,
                "render_node": node_name,
            }
        )
        settings = read_image_write_settings(image_write_node)
        if settings["single_frame"]:
            frame_start = frame_end = settings["frame"]
            frame_step = 1
            range_source = "image_write"
        else:
            frame_start, frame_end = render.get_project_frame_range()
            frame_step = render.get_project_frame_step()
            range_source = "project"
        expected_files = expand_image_output_pattern(
            settings["output_path"],
            frame_start,
            frame_end,
            frame_step,
        )

        creator_attributes = instance.data.get("creator_attributes") or {}
        render_target = creator_attributes.get("render_target", "local")
        if render_target not in {"local", "farm", "local_no_render"}:
            raise RuntimeError(f"Unsupported Katana image target: {render_target!r}.")
        review = bool(creator_attributes.get("review", False))
        render_products = colorspace.ARenderProduct(
            [""],
            settings["colorspace"],
        )
        effective_colorspace = render_products.layer_data.products[0].colorspace
        color_data = lib.get_color_management_preferences() or {}
        if color_data:
            instance.data["colorspaceConfig"] = color_data["config"]

        instance.data.update(
            {
                "instance_node": image_write_node.getName(),
                "image_write_node": image_write_node.getName(),
                "render_node": image_write_node.getName(),
                "imageOutputPath": settings["output_path"],
                "imageFileFormat": settings["file_format"],
                "imageOutputColorspace": settings["colorspace"],
                "imageSingleFrame": settings["single_frame"],
                "frameStartHandle": frame_start,
                "frameEndHandle": frame_end,
                "byFrameStep": frame_step,
                "katanaFrameRangeSource": range_source,
                "expectedFiles": [{"": expected_files}],
                "files": [settings["output_path"]],
                "outputDir": str(Path(expected_files[0]).parent),
                "multipartExr": False,
                "attachTo": [],
                "farm": render_target == "farm",
                "colorspace": effective_colorspace,
                "renderProducts": render_products,
            }
        )
        families = instance.data.setdefault("families", [])
        for family in ("image", "katana.image"):
            if family not in families:
                families.append(family)
        if instance.data["farm"] and "render.farm" not in families:
            families.append("render.farm")
        if not instance.data["farm"] and "render.farm" in families:
            families.remove("render.farm")
        if review and "review" not in families:
            families.append("review")
        if not review and "review" in families:
            families.remove("review")
