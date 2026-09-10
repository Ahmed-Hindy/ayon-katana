"""Validate the AYON context embedded in a Katana project."""

import pyblish.api
from ayon_core.pipeline import OptionalPyblishPluginMixin, registered_host
from ayon_core.pipeline.publish import PublishValidationError

from ayon_katana.api import plugin


class ValidateWorkfileContext(
    plugin.KatanaInstancePlugin,
    OptionalPyblishPluginMixin,
):
    """Require embedded project, folder, and task to match publish context."""

    order = pyblish.api.ValidatorOrder
    label = "Validate Katana Workfile Context"
    families = ["workfile"]
    optional = True

    def process(self, instance) -> None:
        """Reject workfiles whose embedded context differs from publishing."""
        if not self.is_active(instance.data):
            return

        embedded = registered_host().get_context_data()
        publish_context = instance.context.data

        expected = {
            "project": publish_context["projectName"],
            "folder": instance.data.get("folderPath"),
            "task": instance.data.get("task"),
        }
        actual = {
            "project": embedded.get("project_name"),
            "folder": embedded.get("folder_path"),
            "task": embedded.get("task_name"),
        }

        mismatches = {
            key: (expected[key], actual[key])
            for key in expected
            if expected[key] != actual[key]
        }
        if not mismatches:
            return

        details = "; ".join(
            f"{key}: expected {expected_value!r}, embedded {actual_value!r}"
            for key, (expected_value, actual_value) in mismatches.items()
        )
        raise PublishValidationError(
            f"Katana workfile context does not match the publish context: {details}",
            title="Katana workfile context mismatch",
        )
