"""Workfile Builder settings for the Katana addon."""

from ayon_server.settings import (
    BaseSettingsModel,
    SettingsField,
    folder_types_enum,
    task_types_enum,
)


class TemplatedWorkfileProfileModel(BaseSettingsModel):
    """Select a Katana workfile template for an AYON context."""

    task_types: list[str] = SettingsField(
        default_factory=list,
        title="Task types",
        enum_resolver=task_types_enum,
    )
    task_names: list[str] = SettingsField(
        default_factory=list,
        title="Task names",
    )
    folder_types: list[str] = SettingsField(
        default_factory=list,
        title="Folder types",
        enum_resolver=folder_types_enum,
    )
    folder_paths: list[str] = SettingsField(
        default_factory=list,
        title="Folder paths",
    )
    path: str = SettingsField(
        "",
        title="Template path",
        description="Path to a Katana template project.",
    )
    keep_placeholder: bool = SettingsField(False, title="Keep placeholders")
    execute_on_new_file: bool = SettingsField(
        False,
        title="Apply to New Scene",
    )
    execute_on_app_launch: bool = SettingsField(
        True,
        title="Apply on Katana Launch",
    )
    create_first_version: bool = SettingsField(
        True,
        title="Save first workfile version",
    )


class TemplatedWorkfileBuildModel(BaseSettingsModel):
    """Store Workfile Builder profiles."""

    profiles: list[TemplatedWorkfileProfileModel] = SettingsField(
        default_factory=list,
        title="Profiles",
    )
