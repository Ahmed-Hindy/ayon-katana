#!/usr/bin/env python
"""Build an AYON Server addon package for Katana."""

from __future__ import annotations

import argparse
import importlib.util
import io
import logging
import shutil
import zipfile
from pathlib import Path
from types import ModuleType

REPOSITORY_ROOT = Path(__file__).resolve().parent
PACKAGE_METADATA_PATH = REPOSITORY_ROOT / "package.py"
SERVER_ROOT = REPOSITORY_ROOT / "server"
CLIENT_ROOT = REPOSITORY_ROOT / "client" / "ayon_katana"
CLIENT_VERSION_PATH = CLIENT_ROOT / "version.py"
DEFAULT_OUTPUT_ROOT = REPOSITORY_ROOT / "package"
_ZIP_TIMESTAMP = (1980, 1, 1, 0, 0, 0)
_ZIP_FILE_MODE = 0o100644


def _zip_info(destination: str) -> zipfile.ZipInfo:
    """Return deterministic ZIP metadata for one package file.

    Args:
        destination: POSIX archive path.

    Returns:
        Stable ZIP metadata independent of filesystem mtimes and build time.
    """
    info = zipfile.ZipInfo(destination, date_time=_ZIP_TIMESTAMP)
    info.compress_type = zipfile.ZIP_DEFLATED
    info.create_system = 3
    info.external_attr = _ZIP_FILE_MODE << 16
    return info


def _write_file(
    archive: zipfile.ZipFile,
    filepath: Path,
    destination: str,
) -> None:
    """Write one file with deterministic ZIP metadata.

    Args:
        archive: Destination ZIP archive.
        filepath: Source filesystem path.
        destination: POSIX path stored in the archive.
    """
    archive.writestr(_zip_info(destination), filepath.read_bytes())


def _load_package_metadata() -> ModuleType:
    """Load addon metadata from ``package.py``.

    Returns:
        Imported package metadata module.

    Raises:
        RuntimeError: If the metadata module cannot be loaded.
    """
    module_spec = importlib.util.spec_from_file_location(
        "ayon_katana_package_metadata",
        PACKAGE_METADATA_PATH,
    )
    if module_spec is None or module_spec.loader is None:
        raise RuntimeError(f"Cannot load package metadata: {PACKAGE_METADATA_PATH}")

    module = importlib.util.module_from_spec(module_spec)
    module_spec.loader.exec_module(module)
    return module


def _iter_files(root: Path):
    """Yield packageable files below a directory.

    Args:
        root: Directory whose files should be yielded.

    Yields:
        Files excluding Python caches and bytecode.
    """
    for filepath in sorted(root.rglob("*")):
        if not filepath.is_file():
            continue
        relative_parts = filepath.relative_to(root).parts
        if "__pycache__" in relative_parts or filepath.suffix == ".pyc":
            continue
        yield filepath


def _sync_client_version(addon_version: str) -> None:
    """Synchronize the client version with ``package.py`` metadata.

    Ynput's shared release automation rewrites ``package.py`` before invoking
    ``create_package.py``. Mature AYON addons update their packaged client
    version during this build step so the generated archive and committed
    client metadata stay in lockstep.

    Args:
        addon_version: Version loaded from ``package.py``.

    Raises:
        RuntimeError: If the client version declaration cannot be identified
            unambiguously.
    """
    source = CLIENT_VERSION_PATH.read_text(encoding="utf-8")
    lines = source.splitlines()
    matches = [
        index for index, line in enumerate(lines) if line.startswith("__version__ = ")
    ]
    if len(matches) != 1:
        raise RuntimeError(
            f"Expected exactly one __version__ declaration in {CLIENT_VERSION_PATH}."
        )

    expected = f'__version__ = "{addon_version}"'
    index = matches[0]
    if lines[index] == expected:
        return
    lines[index] = expected
    suffix = "\n" if source.endswith(("\n", "\r")) else ""
    CLIENT_VERSION_PATH.write_text("\n".join(lines) + suffix, encoding="utf-8")


def _build_client_zip() -> bytes:
    """Build the private client archive expected by AYON Launcher.

    Returns:
        Serialized ZIP archive.
    """
    if not CLIENT_ROOT.is_dir():
        raise FileNotFoundError(f"Katana client package not found: {CLIENT_ROOT}")

    output_stream = io.BytesIO()
    with zipfile.ZipFile(output_stream, "w", zipfile.ZIP_DEFLATED) as archive:
        for filepath in _iter_files(CLIENT_ROOT):
            destination = Path("ayon_katana") / filepath.relative_to(CLIENT_ROOT)
            _write_file(archive, filepath, destination.as_posix())
    return output_stream.getvalue()


def build_package(output_root: Path = DEFAULT_OUTPUT_ROOT) -> Path:
    """Create the uploadable AYON addon ZIP.

    Args:
        output_root: Directory receiving the addon package.

    Returns:
        Path to the generated ZIP archive.
    """
    package_metadata = _load_package_metadata()
    addon_name = package_metadata.name
    addon_version = package_metadata.version
    _sync_client_version(addon_version)

    output_root.mkdir(parents=True, exist_ok=True)
    output_path = output_root / f"{addon_name}-{addon_version}.zip"
    if output_path.exists():
        output_path.unlink()

    with zipfile.ZipFile(output_path, "w", zipfile.ZIP_DEFLATED) as archive:
        _write_file(archive, PACKAGE_METADATA_PATH, "package.py")
        for filepath in _iter_files(SERVER_ROOT):
            destination = Path("server") / filepath.relative_to(SERVER_ROOT)
            _write_file(archive, filepath, destination.as_posix())
        archive.writestr(_zip_info("private/client.zip"), _build_client_zip())

    return output_path


def extract_package(package_path: Path, output_root: Path) -> Path:
    """Extract a built package into AYON's addon directory layout.

    Args:
        package_path: Generated addon ZIP.
        output_root: Destination package directory.

    Returns:
        Versioned addon directory.
    """
    package_metadata = _load_package_metadata()
    destination = output_root / package_metadata.name / package_metadata.version
    if destination.exists():
        shutil.rmtree(destination)
    destination.mkdir(parents=True)
    with zipfile.ZipFile(package_path) as archive:
        archive.extractall(destination)
    return destination


def main() -> None:
    """Command-line package builder."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output",
        type=Path,
        default=DEFAULT_OUTPUT_ROOT,
        help="Output directory for the addon ZIP.",
    )
    parser.add_argument(
        "--extract",
        action="store_true",
        help="Also extract the package to <output>/<name>/<version>.",
    )
    arguments = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    package_path = build_package(arguments.output)
    logging.info("Created %s", package_path)
    if arguments.extract:
        extracted_path = extract_package(package_path, arguments.output)
        logging.info("Extracted %s", extracted_path)


if __name__ == "__main__":
    main()
