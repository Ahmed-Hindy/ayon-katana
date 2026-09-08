"""Katana workfile operations."""

import os
import re
from typing import Optional

from Katana import KatanaFile, NodegraphAPI

WORKFILE_EXTENSIONS = [".katana"]


_URI_SCHEME_PATTERN = re.compile(r"^[a-z][a-z0-9+.-]*://", re.IGNORECASE)


def is_filesystem_workfile_path(value: str) -> bool:
    """Return whether a value is a filesystem path to a Katana workfile.

    Asset identifiers and other URI-style values are intentionally unsupported
    until Katana has a safe, explicit asset-backed workfile workflow.
    """
    return bool(
        value
        and not _URI_SCHEME_PATTERN.match(value)
        and os.path.splitext(value)[1].lower() in WORKFILE_EXTENSIONS
    )


def normalize_workfile_path(value: str) -> str:
    """Return a normalized filesystem workfile path.

    Args:
        value: Filesystem path to normalize.

    Raises:
        ValueError: The value is empty, URI-style, or not a ``.katana`` file.
    """
    if not value:
        raise ValueError("Katana workfile path is empty.")
    if _URI_SCHEME_PATTERN.match(value):
        raise ValueError(
            "Katana asset identifiers are not supported for workfile publishing."
        )
    if not is_filesystem_workfile_path(value):
        raise ValueError("Katana workfile path must use the .katana extension.")
    return os.path.abspath(os.path.normpath(value))


def validate_workfile_path(value: str, *, require_exists: bool = False) -> str:
    """Normalize and validate a Katana filesystem workfile path.

    Args:
        value: Workfile path to validate.
        require_exists: Whether the path must exist on disk.

    Returns:
        Normalized filesystem path.

    Raises:
        ValueError: The path is not a supported existing Katana workfile.
    """
    normalized_path = normalize_workfile_path(value)
    if require_exists and not os.path.isfile(normalized_path):
        raise ValueError(f"Katana workfile does not exist on disk: {normalized_path}")
    return normalized_path


def workfile_paths_match(first_path: str, second_path: str) -> bool:
    """Return whether two validated workfile paths identify the same file."""
    return os.path.normcase(normalize_workfile_path(first_path)) == os.path.normcase(
        normalize_workfile_path(second_path)
    )


def get_current_workfile() -> Optional[str]:
    """Return the current Katana project path, or ``None`` when unsaved."""
    return NodegraphAPI.GetProjectFile() or None


def get_workfile_extensions() -> list[str]:
    """Return supported Katana project extensions."""
    return list(WORKFILE_EXTENSIONS)


def workfile_has_unsaved_changes() -> bool:
    """Return whether the current Katana project is dirty."""
    return bool(KatanaFile.IsFileDirty())


def save_workfile(dst_path: Optional[str] = None) -> str:
    """Save the current Katana project.

    Args:
        dst_path: Optional destination filesystem path.

    Returns:
        Saved project path.

    Raises:
        ValueError: No supported filesystem destination is available.
    """
    destination = validate_workfile_path(dst_path or get_current_workfile())
    KatanaFile.Save(destination)
    return destination


def open_workfile(filepath: str) -> str:
    """Open a Katana project and return its normalized filesystem path."""
    normalized_path = validate_workfile_path(filepath, require_exists=True)
    KatanaFile.Load(normalized_path)
    return normalized_path


def new_workfile() -> None:
    """Create a new Katana project."""
    KatanaFile.New()
