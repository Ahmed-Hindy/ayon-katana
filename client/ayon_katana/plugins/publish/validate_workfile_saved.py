"""Validate that the Katana workfile has been saved."""

import pyblish.api
from ayon_core.pipeline import OptionalPyblishPluginMixin
from ayon_core.pipeline.publish import PublishValidationError

from ayon_katana.api import plugin, workio


class ValidateWorkfileSaved(
    plugin.KatanaContextPlugin,
    OptionalPyblishPluginMixin,
):
    """Require an existing Katana project before publishing."""

    order = pyblish.api.ValidatorOrder - 0.1
    label = "Validate Katana Workfile Saved"
    optional = True

    def process(self, context) -> None:
        """Reject unsaved or unsupported Katana project paths."""
        if not self.is_active(context.data):
            return

        current_file = context.data.get("currentFile")
        try:
            context.data["currentFile"] = workio.validate_workfile_path(
                current_file,
                require_exists=True,
            )
        except ValueError as exc:
            raise PublishValidationError(
                f"Katana workfile is not publishable: {exc}",
                title="Katana workfile not saved",
            ) from exc
