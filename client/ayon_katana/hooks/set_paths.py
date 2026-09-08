"""Set Katana's process working directory before launch."""

from ayon_applications import LaunchTypes, PreLaunchHook


class SetPath(PreLaunchHook):
    """Set current dir to workdir.

    Hook `GlobalHostDataHook` must be executed before this hook.
    """

    app_groups = {"katana"}
    launch_types = {LaunchTypes.local}

    def execute(self):
        """Set the process working directory from ``AYON_WORKDIR``."""
        workdir = self.launch_context.env.get("AYON_WORKDIR", "")
        if not workdir:
            self.log.warning("BUG: Workdir is not filled.")
            return

        self.launch_context.kwargs["cwd"] = workdir
