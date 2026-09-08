"""ImageIO settings exposed to AYON Core for the Katana host."""

from ayon_server.settings import BaseSettingsModel, SettingsField
from ayon_server.settings.validators import ensure_unique_names
from pydantic import validator


class ImageIOFileRuleModel(BaseSettingsModel):
    """One host-specific colorspace file rule."""

    name: str = SettingsField("", title="Rule name")
    pattern: str = SettingsField("", title="Regex pattern")
    colorspace: str = SettingsField("", title="Colorspace name")
    ext: str = SettingsField("", title="File extension")


class ImageIOFileRulesModel(BaseSettingsModel):
    """Optional host-specific file rules consumed by AYON Core."""

    activate_host_rules: bool = SettingsField(False, title="Use host file rules")
    rules: list[ImageIOFileRuleModel] = SettingsField(
        default_factory=list,
        title="Rules",
    )

    @validator("rules")
    def validate_unique_names(cls, value):
        """Require unique rule names."""
        ensure_unique_names(value)
        return value


class WorkfileImageIOModel(BaseSettingsModel):
    """Optional OCIO display/view overrides applied before Katana launches."""

    enabled: bool = SettingsField(False, title="Enabled")
    default_display: str = SettingsField("", title="Default active displays")
    default_view: str = SettingsField("", title="Default active views")
    review_color_space: str = SettingsField("", title="Review colorspace")


class KatanaImageIOModel(BaseSettingsModel):
    """Katana host colorspace settings compatible with AYON Core lookups."""

    activate_host_color_management: bool = SettingsField(
        True,
        title="Enable Color Management",
    )
    file_rules: ImageIOFileRulesModel = SettingsField(
        default_factory=ImageIOFileRulesModel,
        title="File Rules",
    )
    workfile: WorkfileImageIOModel = SettingsField(
        default_factory=WorkfileImageIOModel,
        title="Workfile",
    )


DEFAULT_IMAGEIO_SETTINGS = {
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
}
