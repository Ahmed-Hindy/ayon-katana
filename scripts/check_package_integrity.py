#!/usr/bin/env python
"""Inspect an AYON Katana addon archive and its extracted payload."""

from __future__ import annotations

import argparse
import ast
import io
import zipfile
from collections.abc import Mapping
from pathlib import Path

PACKAGE_METADATA_ENTRY = "package.py"
CLIENT_ARCHIVE_ENTRY = "private/client.zip"
SERVER_PREFIX = "server/"
CLIENT_PREFIX = "ayon_katana/"
REQUIRED_ARCHIVE_ENTRIES = (
    PACKAGE_METADATA_ENTRY,
    "server/__init__.py",
    "server/addon.py",
    "server/settings/__init__.py",
    "server/settings/main.py",
    CLIENT_ARCHIVE_ENTRY,
)
REQUIRED_CLIENT_ENTRIES = (
    "ayon_katana/__init__.py",
    "ayon_katana/addon.py",
    "ayon_katana/version.py",
    "ayon_katana/hooks/__init__.py",
    "ayon_katana/resources/Startup/init.py",
)


class PackageIntegrityError(RuntimeError):
    """Raised when an addon package does not meet the required layout."""


def _assert_required_entries(
    entries: Mapping[str, bytes], required_entries: tuple[str, ...], location: str
) -> None:
    """Ensure that an addon payload contains its required entries.

    Args:
        entries: File names found in the payload.
        required_entries: File names that must be present.
        location: Human-readable payload description for failure messages.

    Raises:
        PackageIntegrityError: If one or more required entries are missing.
    """
    missing_entries = sorted(set(required_entries).difference(entries))
    if missing_entries:
        raise PackageIntegrityError(
            f"{location} is missing required entries: {', '.join(missing_entries)}"
        )


def _validate_addon_python(
    entries: Mapping[str, bytes], prefix: str, location: str
) -> None:
    """Reject NUL bytes and empty Python files in addon-owned source only.

    Args:
        entries: File contents in the payload.
        prefix: Addon-owned source path to inspect.
        location: Human-readable payload description for failure messages.

    Raises:
        PackageIntegrityError: If an addon-owned Python source is corrupt.
    """
    for name, contents in sorted(entries.items()):
        is_package_metadata = prefix == SERVER_PREFIX and name == PACKAGE_METADATA_ENTRY
        if not (is_package_metadata or name.startswith(prefix)) or not name.endswith(
            ".py"
        ):
            continue
        if not contents:
            raise PackageIntegrityError(
                f"{location} has a zero-byte Python file: {name}"
            )
        if b"\x00" in contents:
            raise PackageIntegrityError(
                f"{location} has NUL bytes in Python file: {name}"
            )


def _read_literal_version(source: bytes, variable_name: str, location: str) -> str:
    """Read a literal string version assignment from packaged Python source.

    Args:
        source: Python source containing the version assignment.
        variable_name: Assignment target expected in the source.
        location: Human-readable source description for failure messages.

    Returns:
        The packaged version string.

    Raises:
        PackageIntegrityError: If the source is invalid or has no literal version.
    """
    try:
        module = ast.parse(source.decode("utf-8"), filename=location)
    except (SyntaxError, UnicodeDecodeError) as error:
        raise PackageIntegrityError(
            f"Cannot read version metadata from {location}: {error}"
        ) from error

    for statement in module.body:
        if not isinstance(statement, ast.Assign):
            continue
        if not any(
            isinstance(target, ast.Name) and target.id == variable_name
            for target in statement.targets
        ):
            continue
        if isinstance(statement.value, ast.Constant) and isinstance(
            statement.value.value, str
        ):
            return statement.value.value
    raise PackageIntegrityError(
        f"Cannot read literal {variable_name} version metadata from {location}"
    )


def _read_zip_entries(archive: zipfile.ZipFile) -> dict[str, bytes]:
    """Read all file entries from a ZIP archive.

    Args:
        archive: Open archive to inspect.

    Returns:
        A mapping of non-directory archive names to their content bytes.
    """
    return {
        info.filename: archive.read(info)
        for info in archive.infolist()
        if not info.is_dir()
    }


def _inspect_payload(entries: Mapping[str, bytes], location: str) -> tuple[str, str]:
    """Inspect one outer or extracted addon payload.

    Args:
        entries: Files contained in the payload.
        location: Human-readable payload description for failure messages.

    Returns:
        The addon name and version declared in package metadata.

    Raises:
        PackageIntegrityError: If required payload files are missing or corrupt.
    """
    _assert_required_entries(entries, REQUIRED_ARCHIVE_ENTRIES, location)
    _validate_addon_python(entries, SERVER_PREFIX, location)

    with zipfile.ZipFile(io.BytesIO(entries[CLIENT_ARCHIVE_ENTRY])) as client_archive:
        client_entries = _read_zip_entries(client_archive)
    client_location = f"Client archive in {location}"
    _assert_required_entries(client_entries, REQUIRED_CLIENT_ENTRIES, client_location)
    _validate_addon_python(client_entries, CLIENT_PREFIX, client_location)

    package_name = _read_literal_version(
        entries[PACKAGE_METADATA_ENTRY], "name", f"{location}/package.py"
    )
    package_version = _read_literal_version(
        entries[PACKAGE_METADATA_ENTRY], "version", f"{location}/package.py"
    )
    client_version = _read_literal_version(
        client_entries["ayon_katana/version.py"],
        "__version__",
        f"{client_location}/ayon_katana/version.py",
    )
    if package_version != client_version:
        raise PackageIntegrityError(
            "Version mismatch between package.py "
            f"({package_version}) and ayon_katana/version.py ({client_version})"
        )
    return package_name, package_version


def _read_extracted_entries(extracted_path: Path) -> dict[str, bytes]:
    """Read all files from an extracted addon payload.

    Args:
        extracted_path: Root directory of the extracted addon payload.

    Returns:
        A mapping relative to ``extracted_path`` for every contained file.
    """
    return {
        path.relative_to(extracted_path).as_posix(): path.read_bytes()
        for path in extracted_path.rglob("*")
        if path.is_file()
    }


def inspect_package(package_path: Path, extracted_path: Path) -> None:
    """Validate an addon archive and the payload extracted from that archive.

    Args:
        package_path: Path to the uploadable addon archive.
        extracted_path: Path to the extracted addon payload.

    Raises:
        PackageIntegrityError: If either payload is incomplete or corrupt.
    """
    with zipfile.ZipFile(package_path) as addon_archive:
        archive_name, archive_version = _inspect_payload(
            _read_zip_entries(addon_archive), f"Archive {package_path}"
        )
    if not extracted_path.is_dir():
        raise PackageIntegrityError(f"Extracted payload is missing: {extracted_path}")
    extracted_name, extracted_version = _inspect_payload(
        _read_extracted_entries(extracted_path), f"Extracted payload {extracted_path}"
    )
    if (archive_name, archive_version) != (extracted_name, extracted_version):
        raise PackageIntegrityError(
            "Archive and extracted package metadata disagree: "
            f"{archive_name}-{archive_version} != "
            f"{extracted_name}-{extracted_version}"
        )


def _resolve_package_path(path: Path) -> Path:
    """Resolve an addon package ZIP from a ZIP path or output directory.

    Args:
        path: Package ZIP or directory containing exactly one package ZIP.

    Returns:
        The resolved package ZIP path.

    Raises:
        PackageIntegrityError: If a package ZIP cannot be identified.
    """
    if path.is_file():
        return path

    expected_package_path = path / _current_package_filename()
    if expected_package_path.is_file():
        return expected_package_path

    package_paths = sorted(path.glob("*.zip"))
    if len(package_paths) == 1:
        return package_paths[0]
    if not package_paths:
        raise PackageIntegrityError(f"No addon package ZIP found in {path}")
    raise PackageIntegrityError(
        f"Expected one addon package ZIP in {path}, found {len(package_paths)}"
    )


def _current_package_filename() -> str:
    """Return the package filename declared by the checked-out addon source.

    This keeps the command-line check deterministic in a developer workspace
    where the ignored package directory contains historical addon builds.

    Returns:
        Expected upload package filename.
    """
    package_metadata_path = Path(__file__).parents[1] / PACKAGE_METADATA_ENTRY
    source = package_metadata_path.read_bytes()
    package_name = _read_literal_version(
        source,
        "name",
        str(package_metadata_path),
    )
    package_version = _read_literal_version(
        source,
        "version",
        str(package_metadata_path),
    )
    return f"{package_name}-{package_version}.zip"


def main() -> None:
    """Run package-integrity checks from the command line."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "package",
        type=Path,
        help="Addon ZIP path or its output directory.",
    )
    parser.add_argument(
        "--extracted-dir",
        type=Path,
        help="Extracted addon directory. Defaults to <output>/<name>/<version>.",
    )
    arguments = parser.parse_args()

    package_path = _resolve_package_path(arguments.package)
    with zipfile.ZipFile(package_path) as addon_archive:
        package_name, package_version = _inspect_payload(
            _read_zip_entries(addon_archive), f"Archive {package_path}"
        )
    extracted_path = arguments.extracted_dir or (
        package_path.parent / package_name / package_version
    )
    inspect_package(package_path, extracted_path)
    print(f"Package integrity verified: {package_path}")


if __name__ == "__main__":
    main()
