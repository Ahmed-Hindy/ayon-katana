"""Optionally save the next workfile version after publishing."""

from __future__ import annotations

import os

import pyblish.api
from ayon_core.pipeline import OptionalPyblishPluginMixin, registered_host
from ayon_core.pipeline.publish import (
    PublishError,
    get_errored_plugins_from_context,
)

from ayon_katana.api import plugin, workio

_INCREMENT_ATTEMPTED_KEY = "_ayon_katana_increment_current_file_attempted"


class IncrementCurrentFile(
    plugin.KatanaContextPlugin,
    OptionalPyblishPluginMixin,
):
    """Save the next workfile version after a successful publish."""

    label = "Increment current file"
    order = pyblish.api.IntegratorOrder + 9.0
    optional = True

    def process(self, context) -> None:
        """Increment the published workfile once."""
        if not self.is_active(context.data):
            return
        if context.data.get(_INCREMENT_ATTEMPTED_KEY):
            self.log.debug("Workfile increment already attempted for this publish.")
            return
        if get_errored_plugins_from_context(context):
            self.log.debug("Skipping workfile increment after publish failure.")
            return
        if not self._has_active_workfile_instance(context):
            self.log.debug("No workfile instance was published; skipping increment.")
            return

        host = registered_host()
        collected_path = context.data.get("currentFile") or ""
        current_path = host.get_current_workfile() or ""
        try:
            paths_match = workio.workfile_paths_match(collected_path, current_path)
        except ValueError as exc:
            raise PublishError(f"Invalid workfile path: {exc}") from exc
        if not paths_match:
            raise PublishError("Collected workfile differs from the active scene.")

        context.data[_INCREMENT_ATTEMPTED_KEY] = True
        try:
            from ayon_core.host.interfaces import SaveWorkfileOptionalData
            from ayon_core.pipeline.workfile import save_next_version

            prepared_data = SaveWorkfileOptionalData(
                project_entity=context.data.get("projectEntity"),
                anatomy=context.data.get("anatomy"),
                project_settings=context.data.get("project_settings"),
            )
            save_next_version(
                description=(
                    f"Incremented by publishing from {os.path.basename(current_path)}"
                ),
                prepared_data=prepared_data,
            )
        except Exception as exc:
            raise PublishError(
                "Publishing completed, but saving the next workfile version "
                f"failed: {exc}"
            ) from exc

    @staticmethod
    def _has_active_workfile_instance(context) -> bool:
        for instance in context:
            data = instance.data
            if not data.get("active", True) or not data.get("publish", True):
                continue
            if (
                data.get("productBaseType") == "workfile"
                or data.get("productType") == "workfile"
            ):
                return True
            if "workfile" in set(data.get("families") or []):
                return True
        return False
