"""Validate exported Katana layers before USD asset contribution."""

from __future__ import annotations

import pyblish.api
from ayon_core.pipeline import OptionalPyblishPluginMixin
from ayon_core.pipeline.publish import PublishValidationError

from ayon_katana.api import plugin
from ayon_katana.api.usd import get_extracted_usd_layer_path


class ValidateUsdAssetContributionDefaultPrim(
    plugin.KatanaInstancePlugin,
    OptionalPyblishPluginMixin,
):
    """Require an asset contribution layer to own its expected default prim.

    This intent must be validated before extraction. Katana's
    native ``UsdLayerExport`` does not expose an equivalent default-prim
    parameter, so this plug-in validates the staged layer immediately after
    extraction and before AYON Core composes contribution products.
    """

    label = "Validate USD Asset Contribution Default Prim"
    order = pyblish.api.ExtractorOrder - 0.48
    families = ["katana.usd"]
    optional = True

    def process(self, instance) -> None:
        """Reject an asset contribution without the required root prim."""
        if not self.is_active(instance.data):
            return

        contribution = self._get_contribution_settings(instance.data)
        if (
            not contribution.get("contribution_enabled", False)
            or contribution.get("contribution_target_product_init") != "asset"
        ):
            return

        try:
            layer_path = get_extracted_usd_layer_path(instance.data)
        except ValueError as exc:
            raise PublishValidationError(
                str(exc),
                title="USD contribution representation invalid",
            ) from exc
        from ayon_core.pipeline.usdlib import get_standard_default_prim_name
        from pxr import Sdf

        layer = Sdf.Layer.FindOrOpen(layer_path.as_posix())
        if layer is None:
            raise PublishValidationError(
                f"Failed to open the extracted USD layer: {layer_path}",
                title="USD contribution layer invalid",
            )

        expected_name = get_standard_default_prim_name(instance.data["folderPath"])
        default_prim = str(layer.defaultPrim or "").lstrip("/")
        if default_prim != expected_name:
            actual = f"/{default_prim}" if default_prim else "not set"
            raise PublishValidationError(
                "USD Contribution is configured to initialize an asset, but "
                f"the exported layer default prim is {actual}. Author a root "
                f"prim named '/{expected_name}' and make it the layer default "
                "prim, choose 'Initialize as shot' for a shot-style layer, or "
                "disable USD Contribution for this product.",
                title="USD asset contribution default prim invalid",
            )

        expected_path = f"/{expected_name}"
        if layer.GetPrimAtPath(expected_path) is None:
            raise PublishValidationError(
                f"The exported layer declares '{expected_path}' as its default "
                "prim, but that root prim does not exist in the layer.",
                title="USD asset contribution root prim missing",
            )

    @staticmethod
    def _get_contribution_settings(data: dict) -> dict:
        """Return the shared Core contribution attributes for an instance."""
        return data.get("publish_attributes", {}).get(
            "CollectUSDLayerContributions", {}
        )
