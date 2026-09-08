"""Collect the current Katana project path for publishing."""

import pyblish.api

from ayon_katana.api import plugin, workio


class CollectKatanaCurrentFile(plugin.KatanaContextPlugin):
    """Inject the current working file into context"""

    order = pyblish.api.CollectorOrder - 0.5
    label = "Katana Current File"

    def process(self, context):
        """Inject the current working file"""
        current_file = workio.get_current_workfile()
        try:
            current_file = workio.normalize_workfile_path(current_file)
        except ValueError:
            # Keep the collected value so the validator can report the actual
            # unsupported path instead of disguising it as a never-saved scene.
            self.log.warning("Katana workfile is not a supported saved path.")

        context.data["currentFile"] = current_file
        self.log.info("Current workfile path: %s", current_file)
