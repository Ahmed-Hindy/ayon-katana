"""Validate colorspace metadata collected for Katana render products."""

from __future__ import annotations

from pathlib import Path

import pyblish.api
from ayon_core.pipeline import OptionalPyblishPluginMixin
from ayon_core.pipeline.publish import PublishValidationError

from ayon_katana.api import plugin


class ValidateRenderColorspace(
    plugin.KatanaInstancePlugin,
    OptionalPyblishPluginMixin,
):
    """Validate render colorspace settings."""

    label = "Validate Render Colorspace"
    order = pyblish.api.ValidatorOrder + 0.02
    families = ["render", "katana.render"]
    optional = True

    def process(self, instance) -> None:
        """Reject review outputs without a declared colorspace."""
        if not self.is_active(instance.data):
            return

        config_path = str(instance.data.get("colorspaceConfig") or "")
        colorspace = str(instance.data.get("colorspace") or "")
        if not config_path or not Path(config_path).is_file() or not colorspace:
            raise PublishValidationError(
                "Katana has no valid active OCIO config with a scene-linear role."
            )
        render_products = instance.data.get("renderProducts")
        products = getattr(
            getattr(render_products, "layer_data", None),
            "products",
            [],
        )
        if not products:
            raise PublishValidationError(
                "Katana render products have no colorspace data."
            )
        if any(product.colorspace != colorspace for product in products):
            raise PublishValidationError(
                "Katana render products do not share the scene-linear colorspace."
            )
