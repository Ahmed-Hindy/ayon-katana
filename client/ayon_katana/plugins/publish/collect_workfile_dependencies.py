"""Collect AYON representations loaded into the Katana workfile."""

import pyblish.api
from ayon_core.pipeline import registered_host

from ayon_katana.api import plugin


class CollectWorkfileDependencies(plugin.KatanaInstancePlugin):
    """Record all loaded AYON representations as workfile inputs."""

    order = pyblish.api.CollectorOrder + 0.4
    label = "Katana Workfile Dependencies"
    families = ["workfile"]

    def process(self, instance) -> None:
        """Collect representation dependencies referenced by the workfile."""
        host = registered_host()
        representations = {
            container.get("representation")
            for container in host.get_containers()
            if container.get("representation")
        }
        instance.data["inputRepresentations"] = sorted(representations)
        self.log.debug(
            "Collected workfile input representations: %s",
            instance.data["inputRepresentations"],
        )
