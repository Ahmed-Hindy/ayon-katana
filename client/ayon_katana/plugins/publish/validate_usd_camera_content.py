"""Validate semantic Katana USD camera publish content."""

from __future__ import annotations

import pyblish.api
from ayon_core.pipeline import OptionalPyblishPluginMixin
from ayon_core.pipeline.publish import PublishValidationError

from ayon_katana.api import plugin
from ayon_katana.api.usd import collect_schema_prim_paths, open_extracted_usd_stage


class ValidateUsdCameraContent(
    plugin.KatanaInstancePlugin,
    OptionalPyblishPluginMixin,
):
    """Require semantic USD camera products to contain a Camera prim."""

    label = "Validate USD Camera Content"
    order = pyblish.api.ExtractorOrder - 0.499
    families = ["katana.usd"]
    optional = False

    def process(self, instance) -> None:
        """Reject semantic camera products without composed camera content."""
        if not self.is_active(instance.data):
            return

        product_base_type = instance.data.get("productBaseType") or instance.data.get(
            "productType"
        )
        if product_base_type not in {"camera", "usdCamera"}:
            return

        try:
            stage = open_extracted_usd_stage(instance.data)
        except (ValueError, RuntimeError) as exc:
            raise PublishValidationError(
                f"Failed to inspect exported USD camera content: {exc}",
                title="USD camera stage invalid",
            ) from exc

        from pxr import UsdGeom

        camera_paths = collect_schema_prim_paths(stage, UsdGeom.Camera)
        if camera_paths:
            return

        raise PublishValidationError(
            "The exported USD camera product does not contain a composed Camera prim. "
            "Connect native USD camera content to the UsdLayerExport source before "
            "publishing, or publish it as a generic USD product instead.",
            title="USD camera content missing",
        )
