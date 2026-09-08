"""AYON client addon definition for Katana."""

import os

from ayon_core.addon import AYONAddon, IHostAddon

from .version import __version__

KATANA_HOST_DIR = os.path.dirname(os.path.abspath(__file__))


class KatanaAddon(AYONAddon, IHostAddon):
    """Configure AYON launches for the Katana host integration."""

    name = "katana"
    version = __version__
    host_name = "katana"

    def add_implementation_envs(self, env, _app):
        """Add the Katana integration to the launch environment."""
        # Add the integration resources to KATANA_RESOURCES.
        resources_path = os.path.normpath(os.path.join(KATANA_HOST_DIR, "resources"))
        new_katana_resources = [resources_path]

        old_katana_resources = env.get("KATANA_RESOURCES") or ""
        for path in old_katana_resources.split(os.pathsep):
            if not path:
                continue

            norm_path = os.path.normpath(path)
            if os.path.normcase(norm_path) not in {
                os.path.normcase(item) for item in new_katana_resources
            }:
                new_katana_resources.append(norm_path)

        env["KATANA_RESOURCES"] = os.pathsep.join(new_katana_resources)

        # Make the addon package importable from Katana's Python environment
        package_parent = os.path.normpath(os.path.dirname(KATANA_HOST_DIR))
        new_python_path = [package_parent]

        old_python_path = env.get("PYTHONPATH") or ""
        for path in old_python_path.split(os.pathsep):
            if not path:
                continue

            norm_path = os.path.normpath(path)
            if os.path.normcase(norm_path) not in {
                os.path.normcase(item) for item in new_python_path
            }:
                new_python_path.append(norm_path)

        env["PYTHONPATH"] = os.pathsep.join(new_python_path)

    def get_launch_hook_paths(self, app):
        """Return Katana prelaunch hook paths for a matching application."""
        if app.host_name != self.host_name:
            return []
        return [os.path.join(KATANA_HOST_DIR, "hooks")]

    def get_workfile_extensions(self):
        """Return workfile extensions supported by Katana."""
        return [".katana"]
