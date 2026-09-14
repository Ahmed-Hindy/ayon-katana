"""Create Katana Viewer review publish instances."""

from __future__ import annotations

from typing import Any

from ayon_katana.api import plugin


class CreateReview(plugin.KatanaCreator):
    """Create a persistent Scene Review marker for the active Katana Viewer."""

    identifier = "io.ayon.creators.katana.review"
    label = "Scene Review"
    product_base_type = "review"
    product_type = product_base_type
    icon = "video-camera"
    description = "Capture the active Katana Viewer as an AYON review sequence"

    def create(
        self,
        product_name: str,
        instance_data: dict[str, Any],
        pre_create_data: dict[str, Any],
    ):
        """Create a node-backed review instance without changing the Viewer."""
        instance_data["review"] = True
        families = instance_data.setdefault("families", [])
        for family in ("review", "katana.review"):
            if family not in families:
                families.append(family)
        return super().create(product_name, instance_data, pre_create_data)
