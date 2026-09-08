"""Prepare Katana startup workfiles for AYON Applications launches."""

from __future__ import annotations

import os
import re
from typing import Optional

from ayon_applications import LaunchTypes, PreLaunchHook

REQUESTED_WORKFILE_ENV = "AYON_KATANA_WORKFILE_PATH"
_URI_SCHEME_PATTERN = re.compile(r"^[a-z][a-z0-9+.-]*://", re.IGNORECASE)


class PrepareKatanaWorkfileLaunch(PreLaunchHook):
    """Pass a validated workfile to Katana's startup coordinator.

    Katana executes ``--script`` before loading positional workfile arguments.
    The selected path is therefore passed through the environment and opened by
    the Katana startup resource only after the AYON host has been installed.
    """

    order = 10
    app_groups = {"katana"}
    launch_types = {LaunchTypes.local}

    def execute(self) -> None:
        """Prepare the requested Katana workfile without changing arguments."""
        launch_environment = self.launch_context.env
        launch_environment.pop(REQUESTED_WORKFILE_ENV, None)

        workfile_path = self.data.get("workfile_path")
        if not workfile_path:
            if not self.data.get("start_last_workfile"):
                self.log.info("Katana will start without opening the last workfile.")
                return
            workfile_path = self.data.get("last_workfile_path")

        validated_path = self._validate_workfile_path(workfile_path)
        if validated_path is None:
            return
        launch_environment[REQUESTED_WORKFILE_ENV] = validated_path

    def _validate_workfile_path(self, workfile_path: object) -> Optional[str]:
        """Return a normalized existing Katana workfile path.

        Args:
            workfile_path: Candidate path supplied by AYON Applications.

        Returns:
            Normalized path, or ``None`` when the value is unsupported.
        """
        if not isinstance(workfile_path, str) or not workfile_path:
            self.log.warning("No Katana workfile path was prepared for launch.")
            return None
        if _URI_SCHEME_PATTERN.match(workfile_path):
            self.log.warning(
                "Katana startup does not support workfile URIs: %s",
                workfile_path,
            )
            return None
        if os.path.splitext(workfile_path)[1].lower() != ".katana":
            self.log.warning(
                "Katana startup requires a .katana workfile: %s",
                workfile_path,
            )
            return None

        normalized_path = os.path.abspath(os.path.normpath(workfile_path))
        if not os.path.isfile(normalized_path):
            self.log.warning(
                "The requested Katana workfile does not exist: %s",
                normalized_path,
            )
            return None
        return normalized_path
