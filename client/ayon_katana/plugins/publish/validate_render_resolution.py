"""Validate Katana render resolution against the AYON context."""

from __future__ import annotations

import inspect

import pyblish.api
from ayon_core.pipeline import (
    OptionalPyblishPluginMixin,
    PublishValidationError,
)

from ayon_katana.api import plugin
from ayon_katana.plugins.publish.actions import SelectInvalidInstanceNodes


class ValidateRenderResolution(
    plugin.KatanaInstancePlugin,
    OptionalPyblishPluginMixin,
):
    """Validate the render resolution setting aligned with the context."""

    order = pyblish.api.ValidatorOrder
    families = ["render", "katana.render"]
    label = "Validate Render Resolution"
    actions = [SelectInvalidInstanceNodes]
    optional = True

    def process(self, instance):
        """Reject invalid resolution values or AYON context mismatches."""
        if not self.is_active(instance.data):
            return

        invalid = self.get_invalid_resolution(instance)
        if invalid:
            raise PublishValidationError(
                "Katana RenderSettings has an invalid resolution or does not "
                "match the current AYON context.",
                description=self.get_description(),
            )

    @classmethod
    def get_invalid_resolution(cls, instance):
        """Return invalid resolution fields for the render instance."""
        width = int(instance.data.get("resolutionWidth") or 0)
        height = int(instance.data.get("resolutionHeight") or 0)
        pixel_aspect = float(instance.data.get("pixelAspect") or 0)
        if width < 1 or height < 1 or pixel_aspect <= 0:
            cls.log.error(
                "Katana RenderSettings has invalid resolution data: %sx%s (%s).",
                width,
                height,
                pixel_aspect,
            )
            return ["resolution"]

        expected = cls.get_expected_resolution(instance)
        if expected is None:
            return []

        actual = (width, height, pixel_aspect)
        if actual != expected:
            cls.log.error(
                "Katana render resolution %sx%s (%s) does not match context "
                "resolution %sx%s (%s).",
                width,
                height,
                pixel_aspect,
                expected[0],
                expected[1],
                expected[2],
            )
            return ["resolution"]
        return []

    @classmethod
    def get_expected_resolution(cls, instance):
        """Return the expected resolution from the task or folder entity."""
        entity = instance.data.get("taskEntity")
        if not entity:
            entity = instance.data.get("folderEntity")
        attributes = (entity or {}).get("attrib") or {}
        required_keys = {"resolutionWidth", "resolutionHeight", "pixelAspect"}
        if not required_keys.issubset(attributes):
            return None
        return (
            int(attributes["resolutionWidth"]),
            int(attributes["resolutionHeight"]),
            float(attributes["pixelAspect"]),
        )

    @staticmethod
    def get_description():
        """Return the Publisher help text for resolution mismatches."""
        return inspect.cleandoc(
            """
            ### Render Resolution does not match context

            The Katana render resolution or pixel aspect ratio does not match
            the resolution configured on the current AYON task or folder.
            Check the native RenderSettings resolution before publishing.
            """
        )
