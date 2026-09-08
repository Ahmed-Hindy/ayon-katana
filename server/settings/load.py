"""Loader settings for the Katana addon."""

from ayon_server.settings import BaseSettingsModel, SettingsField

from .common import EnabledPluginModel


class UsdPathLoaderModel(EnabledPluginModel):
    """Configure a loader whose native node resolves a USD asset path."""

    use_ayon_entity_uri: bool = SettingsField(
        False,
        title="Use AYON Entity URI",
        description=(
            "Write an AYON entity URI into the USD source node instead of a "
            "resolved path. Enable only when the optional AYON USD Resolver "
            "is installed."
        ),
    )


class LoadPluginsModel(BaseSettingsModel):
    """Group loader plugin settings."""

    UsdSublayerLoader: UsdPathLoaderModel = SettingsField(
        default_factory=UsdPathLoaderModel,
        title="Sublayer USD into Native Graph",
    )
    UsdLoader: UsdPathLoaderModel = SettingsField(
        default_factory=UsdPathLoaderModel,
        title="Load USD into Scene Graph with UsdIn",
    )
    AbcLoader: EnabledPluginModel = SettingsField(
        default_factory=EnabledPluginModel,
        title="Load Alembic with Alembic_In",
    )
    KatanaImportLoader: EnabledPluginModel = SettingsField(
        default_factory=EnabledPluginModel,
        title="Import Katana Graph",
    )
    ImageLoader: EnabledPluginModel = SettingsField(
        default_factory=EnabledPluginModel,
        title="Load Image with ImageRead",
    )
    ClearUsdResolverCache: EnabledPluginModel = SettingsField(
        default_factory=EnabledPluginModel,
        title="Clear AYON USD Resolver Cache",
    )
