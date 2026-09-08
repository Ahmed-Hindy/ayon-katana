"""Collect workfile data from the current Katana project."""

import pyblish.api

from ayon_katana.api import plugin


class CollectWorkfile(plugin.KatanaInstancePlugin):
    """Inject workfile representation into instance"""

    order = pyblish.api.CollectorOrder - 0.01
    label = "Katana Workfile Data"
    families = ["workfile"]

    def process(self, instance):
        """Add the staged Katana workfile representation to an instance."""
        current_file = instance.context.data.get("currentFile", "")
        instance.data["setMembers"] = [current_file] if current_file else []
        instance.data.setdefault("productType", "workfile")
        instance.data.setdefault("productBaseType", "workfile")

        for key in ("frameStart", "frameEnd", "handleStart", "handleEnd"):
            if key in instance.context.data:
                instance.data[key] = instance.context.data[key]
