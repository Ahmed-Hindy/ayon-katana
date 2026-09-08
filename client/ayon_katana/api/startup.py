"""Katana-specific startup coordination for AYON launches."""

from __future__ import annotations

import logging
import os
from collections.abc import MutableMapping
from typing import Any, Optional

REQUESTED_WORKFILE_ENV = "AYON_KATANA_WORKFILE_PATH"

log = logging.getLogger("ayon_katana.startup")


def has_requested_workfile(
    environment: Optional[MutableMapping[str, str]] = None,
) -> bool:
    """Return whether AYON selected a workfile for this Katana launch.

    Args:
        environment: Process environment containing the launch request.

    Returns:
        ``True`` when a non-empty request is waiting to be consumed.
    """
    if environment is None:
        environment = os.environ
    return bool(environment.get(REQUESTED_WORKFILE_ENV))


def open_requested_workfile(
    environment: Optional[MutableMapping[str, str]] = None, workio_module: Any = None
) -> Optional[str]:
    """Open the launch-requested workfile once after host installation.

    Args:
        environment: Process environment containing the launch request.
        workio_module: Optional workfile API override used by tests.

    Returns:
        The normalized opened path, or ``None`` when no file was opened.
    """
    if environment is None:
        environment = os.environ
    requested_path = environment.pop(REQUESTED_WORKFILE_ENV, None)
    if not requested_path:
        return None

    if workio_module is None:
        from . import workio as workio_module

    try:
        normalized_path = workio_module.validate_workfile_path(
            requested_path,
            require_exists=True,
        )
    except ValueError:
        log.exception(
            "AYON rejected the requested Katana startup workfile: %s",
            requested_path,
        )
        return None

    current_path = workio_module.get_current_workfile()
    if current_path:
        try:
            if workio_module.workfile_paths_match(current_path, normalized_path):
                log.info(
                    "Katana already has the requested workfile open: %s",
                    normalized_path,
                )
                return normalized_path
        except ValueError:
            log.debug(
                "The current Katana project is not a comparable filesystem "
                "workfile: %s",
                current_path,
            )

    try:
        opened_path = workio_module.open_workfile(normalized_path)
    except Exception:
        log.exception(
            "Katana could not open the requested AYON workfile. "
            "AYON did not save or create a replacement scene: %s",
            normalized_path,
        )
        return None

    log.info("Opened the requested Katana workfile: %s", opened_path)
    return opened_path
