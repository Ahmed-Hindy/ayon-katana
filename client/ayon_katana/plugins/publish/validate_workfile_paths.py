"""Validate external file references stored in the Katana workfile."""

from __future__ import annotations

import os

import pyblish.api
from ayon_core.pipeline import OptionalPyblishPluginMixin
from ayon_core.pipeline.publish import (
    PublishValidationError,
    RepairAction,
    get_errored_instances_from_context,
)

from ayon_katana.api import compat, dependencies, plugin


class SelectInvalidWorkfileReferences(pyblish.api.Action):
    """Select Katana nodes with invalid registered file references."""

    label = "Select Invalid"
    icon = "search"
    on = "failed"

    def process(self, context, plugin) -> None:
        """Select nodes with invalid references."""
        references = []
        for instance in get_errored_instances_from_context(context, plugin=plugin):
            references.extend(plugin.get_invalid(instance))
        nodes = dependencies.unique_reference_nodes(references)
        if nodes:
            compat.set_selected_nodes(nodes)


class ValidateWorkfilePaths(
    plugin.KatanaInstancePlugin,
    OptionalPyblishPluginMixin,
):
    """Validate external paths used by published workfiles."""

    order = pyblish.api.ValidatorOrder
    families = ["workfile"]
    label = "Validate Workfile Paths"
    optional = True
    actions = [SelectInvalidWorkfileReferences, RepairAction]

    def process(self, instance) -> None:
        """Validate external references and relative paths."""
        if not self.is_active(instance.data):
            return

        issues = self.get_invalid_with_reasons(instance)
        if not issues:
            return

        details = "\n".join(
            f"- {reference.label}: {reason}" for reference, reason in issues
        )
        raise PublishValidationError(
            f"Workfile contains invalid external file references:\n{details}",
            title=self.label,
        )

    @classmethod
    def get_invalid(cls, instance) -> list[dependencies.WorkfileReference]:
        """Return invalid references."""
        return [
            reference for reference, _reason in cls.get_invalid_with_reasons(instance)
        ]

    @classmethod
    def get_invalid_with_reasons(
        cls,
        instance,
    ) -> list[tuple[dependencies.WorkfileReference, str]]:
        """Return invalid references and their validation messages."""
        frame_start, frame_end, frame_step = cls._required_frame_range(instance)
        invalid = []
        for reference in dependencies.collect_workfile_references():
            reason = cls._reference_error(
                reference,
                frame_start=frame_start,
                frame_end=frame_end,
                frame_step=frame_step,
            )
            if reason:
                invalid.append((reference, reason))
        return invalid

    @classmethod
    def repair(cls, instance) -> None:
        """Make valid relative paths absolute."""
        frame_start, frame_end, frame_step = cls._required_frame_range(instance)
        repairable = []
        for reference, reason in cls.get_invalid_with_reasons(instance):
            if reason != "path is relative to the current workfile":
                continue
            if not reference.is_relative_literal or not reference.resolved_value:
                continue
            repairable.append(reference)

        if not repairable:
            return

        from Katana import Utils

        undo_stack = Utils.UndoStack
        undo_stack.OpenGroup("Repair AYON workfile paths")
        try:
            for reference in repairable:
                cls._repair_reference(
                    reference,
                    frame_start=frame_start,
                    frame_end=frame_end,
                    frame_step=frame_step,
                )
        finally:
            undo_stack.CloseGroup()

    @classmethod
    def _repair_reference(
        cls,
        reference: dependencies.WorkfileReference,
        *,
        frame_start: int | None,
        frame_end: int | None,
        frame_step: int,
    ) -> None:
        parameter = reference.parameter
        if parameter.isExpression():
            return

        current_value = parameter.getValue(0.0)
        current_value = "" if current_value is None else str(current_value)
        if current_value != reference.authored_value:
            return
        if not reference.is_relative_literal or not reference.resolved_value:
            return
        if frame_start is not None and frame_end is not None:
            frame_values = {
                str(parameter.getValue(float(frame)) or "")
                for frame in range(frame_start, frame_end + 1, frame_step)
            }
            if frame_values != {current_value}:
                return

        required_paths = dependencies.required_reference_paths(
            reference,
            frame_start=frame_start,
            frame_end=frame_end,
            frame_step=frame_step,
        )
        if not required_paths or any(
            not os.path.isfile(path) for path in required_paths
        ):
            return

        parameter.setValue(reference.resolved_value.replace("\\", "/"), 0.0)

    @staticmethod
    def _required_frame_range(instance) -> tuple[int | None, int | None, int]:
        data = instance.data
        context_data = instance.context.data
        frame_start = data.get("frameStart", context_data.get("frameStart"))
        frame_end = data.get("frameEnd", context_data.get("frameEnd"))
        if frame_start is None or frame_end is None:
            return None, None, 1

        handle_start = int(
            data.get("handleStart", context_data.get("handleStart", 0)) or 0
        )
        handle_end = int(data.get("handleEnd", context_data.get("handleEnd", 0)) or 0)
        frame_step = int(data.get("frameStep", context_data.get("frameStep", 1)) or 1)
        return (
            int(frame_start) - handle_start,
            int(frame_end) + handle_end,
            frame_step,
        )

    @staticmethod
    def _reference_error(
        reference: dependencies.WorkfileReference,
        *,
        frame_start: int | None,
        frame_end: int | None,
        frame_step: int,
    ) -> str | None:
        has_frame_range = frame_start is not None and frame_end is not None
        if reference.is_entity_uri:
            return "entity URI cannot be filesystem-validated and is not repairable"
        if not has_frame_range:
            if not reference.authored_value:
                return "path is empty"
            if not reference.resolved_value:
                return "path could not be resolved"

        try:
            required_paths = dependencies.required_reference_paths(
                reference,
                frame_start=frame_start,
                frame_end=frame_end,
                frame_step=frame_step,
            )
        except ValueError as exc:
            return str(exc)
        if (
            not has_frame_range
            and reference.resolved_value
            and dependencies.has_sequence_token(reference.resolved_value)
            and not required_paths
        ):
            return "sequence cannot be validated without a scene frame range"
        missing = [path for path in required_paths if not os.path.isfile(path)]
        if missing:
            preview = ", ".join(missing[:3])
            if len(missing) > 3:
                preview += f" (+{len(missing) - 3} more)"
            return f"required file does not exist: {preview}"
        if reference.is_relative_literal:
            return "path is relative to the current workfile"
        return None
