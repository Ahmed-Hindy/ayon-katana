"""Loader action for the optional AYON USD Resolver cache."""

from ayon_katana.api import plugin
from ayon_katana.api.usd import USD_PRODUCT_BASE_TYPES, clear_resolver_cache


class ClearUsdResolverCache(plugin.KatanaLoader):
    """Clear the optional resolver cache and flush native UsdIn stages."""

    product_base_types = USD_PRODUCT_BASE_TYPES
    product_types = product_base_types
    representations = {"*"}
    extensions = {"usd", "usda", "usdc", "usdlc", "usdnc", "usdz"}
    label = "Clear AYON USD Resolver Cache"
    order = 12
    icon = "refresh"
    color = "white"

    def load(self, context, name=None, namespace=None, options=None):
        """Clear caches without creating or changing a container."""
        return clear_resolver_cache()
