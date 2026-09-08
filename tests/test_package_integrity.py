"""Tests for deterministic addon package-integrity validation."""

from __future__ import annotations

import io
import zipfile
from collections.abc import Mapping
from pathlib import Path

import pytest
from create_package import build_package, extract_package
from scripts.check_package_integrity import (
    PackageIntegrityError,
    _resolve_package_path,
    inspect_package,
)


def _build_and_extract_package(tmp_path: Path) -> tuple[Path, Path]:
    """Build an addon package and extract it into its AYON destination.

    Args:
        tmp_path: Temporary directory provided by pytest.

    Returns:
        The package ZIP path and its extracted payload directory.
    """
    output_path = tmp_path / "package"
    package_path = build_package(output_path)
    extracted_path = extract_package(package_path, output_path)
    return package_path, extracted_path


def _write_zip_entries(path: Path, entries: Mapping[str, bytes | None]) -> None:
    """Write archive entries, omitting entries assigned ``None``.

    Args:
        path: ZIP path to replace.
        entries: Archive file names mapped to bytes or removal markers.
    """
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as archive:
        for name, contents in sorted(entries.items()):
            if contents is not None:
                archive.writestr(name, contents)


def _rewrite_package(
    package_path: Path,
    *,
    outer_updates: Mapping[str, bytes | None] | None = None,
    client_updates: Mapping[str, bytes | None] | None = None,
) -> None:
    """Rewrite selected outer or client archive entries for a corruption probe.

    Args:
        package_path: Addon ZIP to mutate in place.
        outer_updates: Outer addon archive entries to replace or remove.
        client_updates: Client ZIP entries to replace or remove.
    """
    with zipfile.ZipFile(package_path) as addon_archive:
        outer_entries = {
            info.filename: addon_archive.read(info)
            for info in addon_archive.infolist()
            if not info.is_dir()
        }

    if client_updates:
        with zipfile.ZipFile(
            io.BytesIO(outer_entries["private/client.zip"])
        ) as client_archive:
            client_entries = {
                info.filename: client_archive.read(info)
                for info in client_archive.infolist()
                if not info.is_dir()
            }
        client_entries.update(client_updates)
        client_stream = io.BytesIO()
        _write_zip_entries(client_stream, client_entries)
        outer_entries["private/client.zip"] = client_stream.getvalue()

    if outer_updates:
        outer_entries.update(outer_updates)
    _write_zip_entries(package_path, outer_entries)


def test_package_integrity_accepts_builder_output(tmp_path: Path) -> None:
    """The builder output and extracted payload pass the integrity inspection."""
    package_path, extracted_path = _build_and_extract_package(tmp_path)

    inspect_package(package_path, extracted_path)


def test_package_directory_resolves_the_checked_out_build(tmp_path: Path) -> None:
    """Historical ZIPs do not make the current package selection ambiguous."""
    package_path, _ = _build_and_extract_package(tmp_path)
    (package_path.parent / "katana-0.0.0.zip").write_bytes(b"historical build")

    assert _resolve_package_path(package_path.parent) == package_path


@pytest.mark.parametrize(
    ("outer_updates", "client_updates", "match"),
    [
        (
            {"server/settings/main.py": b"\x00" * 32},
            None,
            "NUL bytes.*server/settings/main.py",
        ),
        (
            None,
            {"ayon_katana/addon.py": b"\x00" * 32},
            "NUL bytes.*ayon_katana/addon.py",
        ),
        (
            {"server/settings/main.py": b""},
            None,
            "zero-byte Python file.*server/settings/main.py",
        ),
        ({"private/client.zip": None}, None, "private/client.zip"),
        ({"server/addon.py": None}, None, "server/addon.py"),
        (
            {"server/settings/main.py": None},
            None,
            "server/settings/main.py",
        ),
        (
            None,
            {"ayon_katana/version.py": b'__version__ = "0.0.0"\n'},
            "Version mismatch",
        ),
    ],
)
def test_package_integrity_rejects_archive_corruption(
    tmp_path: Path,
    outer_updates: Mapping[str, bytes | None] | None,
    client_updates: Mapping[str, bytes | None] | None,
    match: str,
) -> None:
    """Archive corruption triggers a targeted integrity failure.

    Args:
        tmp_path: Temporary directory provided by pytest.
        outer_updates: Outer archive mutations for the corruption probe.
        client_updates: Inner client archive mutations for the corruption probe.
        match: Expected integrity-error text.
    """
    package_path, extracted_path = _build_and_extract_package(tmp_path)
    _rewrite_package(
        package_path,
        outer_updates=outer_updates,
        client_updates=client_updates,
    )

    with pytest.raises(PackageIntegrityError, match=match):
        inspect_package(package_path, extracted_path)


def test_package_integrity_rejects_corrupt_extracted_payload(tmp_path: Path) -> None:
    """The extracted payload is checked independently of the upload ZIP."""
    package_path, extracted_path = _build_and_extract_package(tmp_path)
    settings_path = extracted_path / "server" / "settings" / "main.py"
    settings_path.write_bytes(b"\x00" * 32)

    with pytest.raises(
        PackageIntegrityError,
        match="NUL bytes.*server/settings/main.py",
    ):
        inspect_package(package_path, extracted_path)


def test_package_integrity_ignores_non_addon_python_entries(tmp_path: Path) -> None:
    """Third-party-looking archive entries are outside the integrity scan scope."""
    package_path, extracted_path = _build_and_extract_package(tmp_path)
    _rewrite_package(
        package_path,
        outer_updates={"third_party/corrupt.py": b"\x00"},
        client_updates={"vendor/corrupt.py": b"\x00"},
    )

    inspect_package(package_path, extracted_path)
