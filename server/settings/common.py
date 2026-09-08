"""Shared AYON Server setting models for Katana plugins."""

from ayon_server.settings import BaseSettingsModel, SettingsField


class EnabledPluginModel(BaseSettingsModel):
    """Store the enabled state shared by discoverable plugins."""

    enabled: bool = SettingsField(True, title="Enabled")


class OptionalPluginModel(EnabledPluginModel):
    """Store the enabled, optional, and active states of a Pyblish plugin."""

    optional: bool = SettingsField(False, title="Optional")
    active: bool = SettingsField(True, title="Active")


class InstanceContextValidatorModel(OptionalPluginModel):
    """Configure the optional persisted-instance context validator."""

    optional: bool = SettingsField(True, title="Optional")
