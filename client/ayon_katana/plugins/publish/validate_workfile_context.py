"""Validate the AYON context embedded in a Katana project."""

import pyblish.api
from ayon_core.pipeline import OptionalPyblishPluginMixin, registered_host
from ayon_core.pipeline.publish import PublishValidationError

from ayon_katana.api import plugin


def _first_value(data: dict, *keys: str):
    """Return the first non-empty value from candidate keys."""
    for key in keys:
        value = data.get(key)
        if value not in (None, ""):
            return value
    return None


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

        """Compare the root-node context with the current publish context."""
        embedded = registered_host().get_context_data()
        publish_context = instance.context.data

        expected = {
            "project": _first_value(publish_context, "projectName", "project_name"),
            "folder": _first_value(instance.data, "folderPath", "folder_path")
            or _first_value(publish_context, "folderPath", "folder_path"),
            "task": _first_value(instance.data, "task", "taskName", "task_name")
            or _first_value(publish_context, "task", "taskName", "task_name"),
        }
        actual = {
            "project": _first_value(embedded, "project_name", "projectName"),
            "folder": _first_value(embedded, "folder_path", "folderPath"),
            "task": _first_value(embedded, "task_name", "taskName", "task"),
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
