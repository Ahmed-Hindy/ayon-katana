"""Validate that persisted Katana instances match the publish context."""

from ayon_core.pipeline.publish import (
    OptionalPyblishPluginMixin,
    PublishValidationError,
    RepairAction,
    ValidateContentsOrder,
)

from ayon_katana.api import plugin
from ayon_katana.plugins.publish.actions import SelectInvalidInstanceNodes


class ValidateInstanceInContextKatana(
    plugin.KatanaInstancePlugin,
    OptionalPyblishPluginMixin,
):
    """Validate that an instance publishes to the current folder and task.

    Runtime instances that spawn from a persisted creator instance are skipped
    because their source
    instance is validated instead.
    """

    order = ValidateContentsOrder
    label = "Instance in Same Context"
    optional = True
    actions = [SelectInvalidInstanceNodes, RepairAction]

    def process(self, instance):
        """Reject persisted instances outside the active publish context."""
        if not self.is_active(instance.data):
            return

        attr_values = self.get_attr_values_from_data(instance.data)
        if not attr_values and not instance.data.get("instance_node"):
            return

        folder_path = instance.data.get("folderPath")
        task = instance.data.get("task")
        context = self.get_context(instance)
        if (folder_path, task) != context:
            context_label = f"{context[0]} > {context[1]}"
            instance_label = f"{folder_path} > {task}"

            raise PublishValidationError(
                message=(
                    f"Instance {instance.name!r} publishes to different asset "
                    f"than current context: {instance_label}. Current context: "
                    f"{context_label}"
                ),
                description=(
                    "## Publishing to a different asset\n"
                    "There are publish instances present which are publishing "
                    "into a different asset than your current context.\n\n"
                    "Usually this is not what you want but there can be cases "
                    "where you might want to publish into another asset or "
                    "shot. If that's the case you can disable the validation "
                    "on the instance to ignore it."
                ),
            )

    @classmethod
    def repair(cls, instance):
        """Move persisted instance metadata to the active publish context."""
        context_folder, context_task = cls.get_context(instance)

        create_context = instance.context.data["create_context"]
        instance_id = instance.data["instance_id"]
        created_instance = create_context.get_instance_by_id(instance_id)
        created_instance["folderPath"] = context_folder
        created_instance["task"] = context_task
        create_context.save_changes()

    @staticmethod
    def get_context(instance):
        """Return the current publish folder path and task name."""
        context = instance.context
        return context.data["folderPath"], context.data["task"]
