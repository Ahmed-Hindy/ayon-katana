"""Stage a copy of the current Katana workfile for publishing."""

import os
import shutil

import pyblish.api
from ayon_core.pipeline import registered_host
from ayon_core.pipeline.publish import PublishError

from ayon_katana.api import plugin, workio


class ExtractWorkfile(plugin.KatanaExtractorPlugin):
    """Copy the saved Katana project into the instance staging directory."""

    label = "Extract Katana Workfile"
    order = pyblish.api.ExtractorOrder
    families = ["workfile"]

    def process(self, instance) -> None:
        """Copy the clean current project without changing Katana's active path."""
        context = instance.context
        try:
            source_path = workio.validate_workfile_path(
                context.data.get("currentFile", ""),
                require_exists=True,
            )
            active_path = workio.validate_workfile_path(
                registered_host().get_current_workfile(),
                require_exists=True,
            )
        except ValueError as exc:
            raise PublishError(f"Katana workfile cannot be staged: {exc}") from exc

        if not workio.workfile_paths_match(source_path, active_path):
            raise PublishError(
                "Katana workfile path changed during publishing; refusing to "
                "stage a different scene."
            )
        if registered_host().workfile_has_unsaved_changes():
            raise PublishError(
                "Katana workfile has unsaved changes; refusing to stage stale data."
            )

        context.data["currentFile"] = source_path
        staging_dir = self.staging_dir(instance)
        filename = os.path.basename(source_path)
        destination_path = os.path.join(staging_dir, filename)

        destination_path = os.path.abspath(os.path.normpath(destination_path))
        if not workio.workfile_paths_match(source_path, destination_path):
            shutil.copy2(source_path, destination_path)

        extension = os.path.splitext(filename)[1].lstrip(".")
        representation = {
            "name": extension,
            "ext": extension,
            "files": filename,
            "stagingDir": staging_dir,
        }
        instance.data.setdefault("representations", []).append(representation)
        self.log.info("Staged Katana workfile: %s", destination_path)
