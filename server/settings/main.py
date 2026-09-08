"""Top-level AYON Server settings model for Katana."""

from ayon_server.settings import BaseSettingsModel, SettingsField

from .create import CreatePluginsModel
from .imageio import KatanaImageIOModel
from .load import LoadPluginsModel
from .publish import PublishPluginsModel
from .templated_workfile_build import TemplatedWorkfileBuildModel


class KatanaSettings(BaseSettingsModel):
    """Combine all Katana addon setting groups."""

    imageio: KatanaImageIOModel = SettingsField(
        default_factory=KatanaImageIOModel,
        title="Color Management",
    )
    create: CreatePluginsModel = SettingsField(
        default_factory=CreatePluginsModel,
        title="Creator Plugins",
    )
    load: LoadPluginsModel = SettingsField(
        default_factory=LoadPluginsModel,
        title="Loader Plugins",
    )
    publish: PublishPluginsModel = SettingsField(
        default_factory=PublishPluginsModel,
        title="Publish Plugins",
    )
    templated_workfile_build: TemplatedWorkfileBuildModel = SettingsField(
        default_factory=TemplatedWorkfileBuildModel,
        title="Templated Workfile Build",
    )


DEFAULT_VALUES = {
    "imageio": {
        "activate_host_color_management": True,
        "file_rules": {
            "activate_host_rules": False,
            "rules": [],
        },
        "workfile": {
            "enabled": False,
            "default_display": "",
            "default_view": "",
            "review_color_space": "",
        },
    },
    "create": {
        "CreateWorkfile": {
            "enabled": True,
            "is_mandatory": False,
        },
        "CreateRender": {
            "enabled": True,
            "default_render_target": "farm",
            "default_renderer": "",
            "default_extension": "exr",
            "default_channel": "rgba",
            "default_frame_padding": 4,
        },
        "CreateNodegraph": {"enabled": True},
        "CreateUsdLayer": {
            "enabled": True,
            "default_usd_format": "usd",
            "default_time_samples": "Current Frame",
            "default_export_method": "Keep Composition Arcs",
            "default_samples_per_frame": 1.0,
        },
        "CreateUsdLook": {
            "enabled": True,
            "default_usd_format": "usd",
            "default_time_samples": "Current Frame",
            "default_export_method": "Keep Composition Arcs",
            "default_samples_per_frame": 1.0,
        },
        "CreateUsdCamera": {
            "enabled": True,
            "default_usd_format": "usd",
            "default_time_samples": "Frame Range",
            "default_export_method": "Keep Composition Arcs",
            "default_samples_per_frame": 1.0,
        },
        "CreateUsdLayout": {
            "enabled": True,
            "default_usd_format": "usd",
            "default_time_samples": "Current Frame",
            "default_export_method": "Keep Composition Arcs",
            "default_samples_per_frame": 1.0,
        },
        "CreateUsdAssembly": {
            "enabled": True,
            "default_usd_format": "usd",
            "default_time_samples": "Current Frame",
            "default_export_method": "Keep Composition Arcs",
            "default_samples_per_frame": 1.0,
        },
        "CreateRenderSetup": {"enabled": True},
        "CreateImage": {
            "enabled": True,
            "default_render_target": "local",
            "default_extension": "exr",
            "default_colorspace": "",
            "default_frame_padding": 4,
            "default_review": False,
        },
    },
    "load": {
        "UsdSublayerLoader": {
            "enabled": True,
            "use_ayon_entity_uri": False,
        },
        "UsdLoader": {
            "enabled": True,
            "use_ayon_entity_uri": False,
        },
        "AbcLoader": {"enabled": True},
        "KatanaImportLoader": {"enabled": True},
        "ImageLoader": {"enabled": True},
        "ClearUsdResolverCache": {"enabled": True},
    },
    "publish": {
        "CollectKatanaCurrentFile": {"enabled": True},
        "CollectWorkfile": {"enabled": True},
        "CollectWorkfileDependencies": {"enabled": True},
        "CollectRender": {"enabled": True},
        "CollectRenderNode": {"enabled": True},
        "CollectRenderFrameRange": {"enabled": True},
        "CollectAssetHandles": {"enabled": True},
        "CollectRenderSettings": {"enabled": True},
        "CollectLocalRenderInstances": {"enabled": True},
        "CollectNodegraph": {"enabled": True},
        "CollectNodegraphDependencies": {"enabled": True},
        "CollectUsdLayer": {"enabled": True},
        "CollectImage": {"enabled": True},
        "ValidateWorkfileSaved": {
            "enabled": True,
            "optional": False,
            "active": True,
        },
        "ValidateWorkfileContext": {
            "enabled": True,
            "optional": False,
            "active": True,
        },
        "ValidateWorkfilePaths": {
            "enabled": True,
            "optional": True,
            "active": True,
        },
        "ValidateInstanceInContextKatana": {
            "enabled": True,
            "optional": True,
            "active": True,
        },
        "ValidateRender": {
            "enabled": True,
            "optional": False,
            "active": True,
        },
        "ValidateRenderProductPathsUnique": {
            "enabled": True,
            "optional": False,
            "active": True,
        },
        "ValidateRenderCamera": {
            "enabled": True,
            "optional": False,
            "active": True,
        },
        "ValidateRenderResolution": {
            "enabled": True,
            "optional": False,
            "active": True,
        },
        "ValidateRenderOutputNames": {
            "enabled": True,
            "optional": False,
            "active": True,
        },
        "ValidateRenderOutputPaths": {
            "enabled": True,
            "optional": False,
            "active": True,
        },
        "ValidateRenderOutputExtensions": {
            "enabled": True,
            "optional": False,
            "active": True,
        },
        "ValidateRenderOutputTokens": {
            "enabled": True,
            "optional": False,
            "active": True,
        },
        "ValidateRenderColorspace": {
            "enabled": True,
            "optional": False,
            "active": True,
        },
        "ValidateNodegraph": {
            "enabled": True,
            "optional": False,
            "active": True,
        },
        "ValidateUsdLayer": {
            "enabled": True,
            "optional": False,
            "active": True,
        },
        "ValidateUsdAssetContributionDefaultPrim": {
            "enabled": True,
            "optional": True,
            "active": True,
        },
        "ValidateUsdLookAssignments": {
            "enabled": True,
            "optional": True,
            "active": True,
        },
        "ValidateUsdLookDisallowedTypes": {"enabled": True},
        "ValidateUsdLookMaterialDefinitions": {
            "enabled": True,
            "optional": True,
            "active": True,
        },
        "ValidateImage": {
            "enabled": True,
            "optional": False,
            "active": True,
        },
        "FinalizeUsdPublish": {"enabled": True},
        "IncrementCurrentFile": {
            "enabled": True,
            "optional": True,
            "active": False,
        },
        "ExtractWorkfileThumbnail": {
            "enabled": True,
            "optional": True,
            "active": True,
        },
        "ExtractWorkfile": {"enabled": True},
        "ExtractLocalRender": {"enabled": True},
        "ExtractNodegraph": {"enabled": True},
        "ExtractUsdLayer": {"enabled": True},
    },
    "templated_workfile_build": {"profiles": []},
}
