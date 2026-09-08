"""Creator settings for the Katana addon."""

from ayon_server.settings import BaseSettingsModel, SettingsField

from .common import EnabledPluginModel


def render_targets_enum():
    """Return supported Katana render targets."""
    return [
        {"value": "farm", "label": "Farm"},
        {"value": "local", "label": "Local"},
        {"value": "local_no_render", "label": "Use existing frames"},
    ]


def usd_formats_enum():
    """Return supported USD layer formats."""
    return [
        {"value": "usd", "label": "USD"},
        {"value": "usda", "label": "USD ASCII"},
        {"value": "usdc", "label": "USD Crate"},
    ]


def usd_time_samples_enum():
    """Return supported USD time-sampling modes."""
    return [
        {"value": "Current Frame", "label": "Current Frame"},
        {"value": "Frame Range", "label": "Frame Range"},
        {"value": "Project Settings", "label": "Project Settings"},
        {
            "value": "Defined Layer Metadata",
            "label": "Defined Layer Metadata",
        },
    ]


def usd_export_methods_enum():
    """Return supported USD layer composition methods."""
    return [
        {"value": "Keep Composition Arcs", "label": "Keep Composition Arcs"},
        {
            "value": "Flatten Sublayers, Keep References",
            "label": "Flatten Sublayers, Keep References",
        },
        {"value": "Flatten All", "label": "Flatten All"},
    ]


class CreateWorkfileModel(EnabledPluginModel):
    """Configure the automatic workfile creator."""

    is_mandatory: bool = SettingsField(
        False,
        title="Mandatory workfile",
        description="Prevent artists from disabling the workfile instance.",
    )


class CreateRenderModel(EnabledPluginModel):
    """Configure Katana render instances."""

    default_render_target: str = SettingsField(
        "farm",
        title="Default render target",
        enum_resolver=render_targets_enum,
    )
    default_renderer: str = SettingsField(
        "",
        title="Default renderer",
        description=(
            "Registered Katana renderer ID. When empty, DEFAULT_RENDERER must "
            "name a registered renderer or render creation fails."
        ),
    )
    default_extension: str = SettingsField("exr", title="Default extension")
    default_channel: str = SettingsField("rgba", title="Default channel / AOV")
    default_frame_padding: int = SettingsField(
        4,
        title="Frame padding",
        ge=1,
        le=12,
    )


class CreateNodegraphModel(EnabledPluginModel):
    """Configure selected Katana Group node graph instances."""


class CreateUsdLayerModel(EnabledPluginModel):
    """Configure USD layer export instances."""

    default_usd_format: str = SettingsField(
        "usd",
        title="Default USD format",
        enum_resolver=usd_formats_enum,
    )
    default_time_samples: str = SettingsField(
        "Current Frame",
        title="Default time samples",
        enum_resolver=usd_time_samples_enum,
    )
    default_export_method: str = SettingsField(
        "Keep Composition Arcs",
        title="Default export method",
        enum_resolver=usd_export_methods_enum,
    )
    default_samples_per_frame: float = SettingsField(
        1.0,
        title="Default samples per frame",
        gt=0,
    )


class CreateImageModel(EnabledPluginModel):
    """Configure image output instances."""

    default_render_target: str = SettingsField(
        "local",
        title="Default render target",
        enum_resolver=render_targets_enum,
    )
    default_extension: str = SettingsField("exr", title="Default extension")
    default_colorspace: str = SettingsField(
        "",
        title="Default output colorspace",
        description="Required on instances marked for review.",
    )
    default_frame_padding: int = SettingsField(
        4,
        title="Frame padding",
        ge=1,
        le=12,
    )
    default_review: bool = SettingsField(False, title="Review by default")


class CreatePluginsModel(BaseSettingsModel):
    """Group creator plugin settings."""

    CreateWorkfile: CreateWorkfileModel = SettingsField(
        default_factory=CreateWorkfileModel,
        title="Create Workfile",
    )
    CreateRender: CreateRenderModel = SettingsField(
        default_factory=CreateRenderModel,
        title="Create Render",
    )
    CreateNodegraph: CreateNodegraphModel = SettingsField(
        default_factory=CreateNodegraphModel,
        title="Create Node Graph",
    )
    CreateUsdLayer: CreateUsdLayerModel = SettingsField(
        default_factory=CreateUsdLayerModel,
        title="Create USD Layer",
    )
    CreateUsdLook: CreateUsdLayerModel = SettingsField(
        default_factory=CreateUsdLayerModel,
        title="Create USD Look",
    )
    CreateUsdCamera: CreateUsdLayerModel = SettingsField(
        default_factory=CreateUsdLayerModel,
        title="Create USD Camera",
    )
    CreateUsdLayout: CreateUsdLayerModel = SettingsField(
        default_factory=CreateUsdLayerModel,
        title="Create USD Layout",
    )
    CreateUsdAssembly: CreateUsdLayerModel = SettingsField(
        default_factory=CreateUsdLayerModel,
        title="Create USD Assembly",
    )
    CreateRenderSetup: CreateNodegraphModel = SettingsField(
        default_factory=CreateNodegraphModel,
        title="Create Render Setup",
    )
    CreateImage: CreateImageModel = SettingsField(
        default_factory=CreateImageModel,
        title="Create Image",
    )
