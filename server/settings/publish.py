"""Publisher settings for the Katana addon."""

from ayon_server.settings import BaseSettingsModel, SettingsField

from .common import (
    EnabledPluginModel,
    InstanceContextValidatorModel,
    OptionalPluginModel,
)


class PublishPluginsModel(BaseSettingsModel):
    """Group publisher plugin settings."""

    CollectKatanaCurrentFile: EnabledPluginModel = SettingsField(
        default_factory=EnabledPluginModel,
        title="Collect Current File",
        section="Collectors",
    )
    CollectWorkfile: EnabledPluginModel = SettingsField(
        default_factory=EnabledPluginModel,
        title="Collect Workfile Data",
    )
    CollectWorkfileDependencies: EnabledPluginModel = SettingsField(
        default_factory=EnabledPluginModel,
        title="Collect Workfile Dependencies",
    )
    CollectRender: EnabledPluginModel = SettingsField(
        default_factory=EnabledPluginModel,
        title="Collect Render Products",
    )
    CollectRenderNode: EnabledPluginModel = SettingsField(
        default_factory=EnabledPluginModel,
        title="Collect Render Node",
    )
    CollectRenderFrameRange: EnabledPluginModel = SettingsField(
        default_factory=EnabledPluginModel,
        title="Collect Frame Range",
    )
    CollectAssetHandles: EnabledPluginModel = SettingsField(
        default_factory=EnabledPluginModel,
        title="Collect Task Handles",
    )
    CollectRenderSettings: EnabledPluginModel = SettingsField(
        default_factory=EnabledPluginModel,
        title="Collect Render Settings",
    )
    CollectLocalRenderInstances: EnabledPluginModel = SettingsField(
        default_factory=EnabledPluginModel,
        title="Collect Local Output Instances",
    )
    CollectNodegraph: EnabledPluginModel = SettingsField(
        default_factory=EnabledPluginModel,
        title="Collect Node Graph",
    )
    CollectNodegraphDependencies: EnabledPluginModel = SettingsField(
        default_factory=EnabledPluginModel,
        title="Collect Node Graph Dependencies",
    )
    CollectUsdLayer: EnabledPluginModel = SettingsField(
        default_factory=EnabledPluginModel,
        title="Collect USD Layer",
    )
    CollectImage: EnabledPluginModel = SettingsField(
        default_factory=EnabledPluginModel,
        title="Collect ImageWrite",
    )
    ValidateWorkfileSaved: OptionalPluginModel = SettingsField(
        default_factory=OptionalPluginModel,
        title="Validate Workfile Saved",
        section="Validators",
    )
    ValidateWorkfileContext: OptionalPluginModel = SettingsField(
        default_factory=OptionalPluginModel,
        title="Validate Workfile Context",
    )
    ValidateWorkfilePaths: OptionalPluginModel = SettingsField(
        default_factory=OptionalPluginModel,
        title="Validate Workfile Paths",
    )
    ValidateInstanceInContextKatana: InstanceContextValidatorModel = SettingsField(
        default_factory=InstanceContextValidatorModel,
        title="Instance in Same Context",
    )
    ValidateRender: OptionalPluginModel = SettingsField(
        default_factory=OptionalPluginModel,
        title="Validate Render",
    )
    ValidateRenderProductPathsUnique: OptionalPluginModel = SettingsField(
        default_factory=OptionalPluginModel,
        title="Unique Render Product Paths",
    )
    ValidateRenderCamera: OptionalPluginModel = SettingsField(
        default_factory=OptionalPluginModel,
        title="Validate Render Camera",
    )
    ValidateRenderResolution: OptionalPluginModel = SettingsField(
        default_factory=OptionalPluginModel,
        title="Validate Render Resolution",
    )
    ValidateRenderOutputNames: OptionalPluginModel = SettingsField(
        default_factory=OptionalPluginModel,
        title="Validate Render Output Names",
    )
    ValidateRenderOutputPaths: OptionalPluginModel = SettingsField(
        default_factory=OptionalPluginModel,
        title="Validate Render Output Paths",
    )
    ValidateRenderOutputExtensions: OptionalPluginModel = SettingsField(
        default_factory=OptionalPluginModel,
        title="Validate Render Output Extensions",
    )
    ValidateRenderOutputTokens: OptionalPluginModel = SettingsField(
        default_factory=OptionalPluginModel,
        title="Validate Render Output Tokens",
    )
    ValidateRenderColorspace: OptionalPluginModel = SettingsField(
        default_factory=OptionalPluginModel,
        title="Validate Render Colorspace",
    )
    ValidateNodegraph: OptionalPluginModel = SettingsField(
        default_factory=OptionalPluginModel,
        title="Validate Node Graph",
    )
    ValidateUsdLayer: OptionalPluginModel = SettingsField(
        default_factory=OptionalPluginModel,
        title="Validate USD Layer",
    )
    ValidateUsdAssetContributionDefaultPrim: OptionalPluginModel = SettingsField(
        default_factory=OptionalPluginModel,
        title="Validate USD Asset Contribution Default Prim",
    )
    ValidateUsdLookAssignments: OptionalPluginModel = SettingsField(
        default_factory=OptionalPluginModel,
        title="Validate All Geometry Has Material Assignment",
    )
    ValidateUsdLookDisallowedTypes: EnabledPluginModel = SettingsField(
        default_factory=EnabledPluginModel,
        title="Validate Look No Disallowed Types",
    )
    ValidateUsdLookMaterialDefinitions: OptionalPluginModel = SettingsField(
        default_factory=OptionalPluginModel,
        title="Validate Look Shaders Are Defined",
    )
    ValidateImage: OptionalPluginModel = SettingsField(
        default_factory=OptionalPluginModel,
        title="Validate ImageWrite",
    )
    FinalizeUsdPublish: EnabledPluginModel = SettingsField(
        default_factory=EnabledPluginModel,
        title="Finalize USD",
    )
    IncrementCurrentFile: OptionalPluginModel = SettingsField(
        default_factory=OptionalPluginModel,
        title="Increment current file",
    )
    ExtractWorkfileThumbnail: OptionalPluginModel = SettingsField(
        default_factory=OptionalPluginModel,
        title="Extract Workfile Thumbnail",
    )
    ExtractWorkfile: EnabledPluginModel = SettingsField(
        default_factory=EnabledPluginModel,
        title="Extract Workfile",
        section="Extractors",
    )
    ExtractLocalRender: EnabledPluginModel = SettingsField(
        default_factory=EnabledPluginModel,
        title="Extract Local Output",
    )
    ExtractNodegraph: EnabledPluginModel = SettingsField(
        default_factory=EnabledPluginModel,
        title="Extract Node Graph",
    )
    ExtractUsdLayer: EnabledPluginModel = SettingsField(
        default_factory=EnabledPluginModel,
        title="Extract USD Layer",
    )
