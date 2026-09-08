"""Apply optional Katana OCIO display/view launch overrides."""

from __future__ import annotations

from ayon_applications import LaunchTypes, PreLaunchHook


def prepend_unique_ocio_values(configured: str, existing: str = "") -> str:
    """Prepend colon-separated OCIO values without introducing duplicates.

    Args:
        configured: Preferred display or view values from Katana settings.
        existing: Existing environment value to preserve after preferences.

    Returns:
        Colon-separated values in first-seen order.
    """
    output = []
    seen = set()
    for raw_value in (configured, existing):
        for value in str(raw_value or "").split(":"):
            value = value.strip()
            if not value or value in seen:
                continue
            seen.add(value)
            output.append(value)
    return ":".join(output)


class SetDefaultDisplayView(PreLaunchHook):
    """Prepend optional OCIO active display/view values for Katana."""

    app_groups = {"katana"}
    launch_types = {LaunchTypes.local}

    def execute(self) -> None:
        """Apply enabled workfile display/view overrides to launch environment."""
        environment = self.launch_context.env
        if not environment.get("OCIO"):
            return

        katana_settings = (self.data.get("project_settings") or {}).get("katana", {})
        imageio_settings = katana_settings.get("imageio") or {}
        if not imageio_settings.get("activate_host_color_management", True):
            return

        workfile_settings = imageio_settings.get("workfile") or {}
        if not workfile_settings.get("enabled", False):
            return

        for setting_key, environment_key in (
            ("default_display", "OCIO_ACTIVE_DISPLAYS"),
            ("default_view", "OCIO_ACTIVE_VIEWS"),
        ):
            configured = str(workfile_settings.get(setting_key) or "")
            if not configured:
                continue
            environment[environment_key] = prepend_unique_ocio_values(
                configured,
                environment.get(environment_key, ""),
            )
