"""Save a dirty Katana workfile without changing its active path."""

import pyblish.api
from ayon_core.pipeline import PublishError, registered_host

from ayon_katana.api import plugin, workio


class SaveCurrentScene(plugin.KatanaContextPlugin):
    """Save unsaved scene edits before the workfile extractor stages the file."""

    order = pyblish.api.ExtractorOrder - 0.49
    label = "Save Katana Current Scene"

    def process(self, context) -> None:
        """Save only the collected current scene after checking its path."""
        host = registered_host()
        try:
            collected_path = workio.validate_workfile_path(
                context.data.get("currentFile", ""),
                require_exists=True,
            )
            current_path = workio.validate_workfile_path(
                host.get_current_workfile(),
                require_exists=True,
            )
        except ValueError as exc:
            raise PublishError(
                f"Katana workfile cannot be saved for publishing: {exc}"
            ) from exc

        if not workio.workfile_paths_match(collected_path, current_path):
            raise PublishError(
                "Collected Katana workfile path differs from the active scene; "
                "reset publishing and try again without changing workfiles."
            )

        if host.workfile_has_unsaved_changes():
            self.log.info("Saving current Katana workfile: %s", current_path)
            host.save_workfile(current_path)

        try:
            saved_path = workio.validate_workfile_path(
                host.get_current_workfile(),
                require_exists=True,
            )
        except ValueError as exc:
            raise PublishError(
                f"Katana workfile save did not leave a valid scene path: {exc}"
            ) from exc

        if not workio.workfile_paths_match(collected_path, saved_path):
            raise PublishError(
                "Katana workfile path changed while saving; refusing to stage a "
                "different scene."
            )
        if host.workfile_has_unsaved_changes():
            raise PublishError(
                "Katana workfile is still dirty after saving; refusing to stage "
                "stale data."
            )

        context.data["currentFile"] = saved_path
