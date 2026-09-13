"""Tests for the AYON Katana server package builder."""

from __future__ import annotations

import io
import os
import re
import runpy
import subprocess
import sys
import zipfile
from pathlib import Path

from create_package import (
    _ZIP_TIMESTAMP,
    _sync_client_version,
    _write_file,
    build_package,
    extract_package,
)

ROOT = Path(__file__).parents[1]
PACKAGE_METADATA = runpy.run_path(str(ROOT / "package.py"))
ADDON_NAME = PACKAGE_METADATA["name"]
ADDON_VERSION = PACKAGE_METADATA["version"]


def test_package_contains_server_and_client_payload(tmp_path) -> None:
    """Build an addon archive with server files and packaged client code."""
    package_path = build_package(tmp_path)

    assert package_path.name == f"{ADDON_NAME}-{ADDON_VERSION}.zip"
    with zipfile.ZipFile(package_path) as addon_archive:
        addon_files = set(addon_archive.namelist())
        assert {
            "package.py",
            "server/__init__.py",
            "server/addon.py",
            "server/settings/__init__.py",
            "server/settings/main.py",
            "private/client.zip",
        }.issubset(addon_files)

        client_payload = addon_archive.read("private/client.zip")

    with zipfile.ZipFile(io.BytesIO(client_payload)) as client_archive:
        client_files = set(client_archive.namelist())
        assert "ayon_katana/addon.py" in client_files
        assert "ayon_katana/hooks/__init__.py" in client_files
        assert {
            "ayon_katana/hooks/pre_add_workfile_arg.py",
            "ayon_katana/hooks/set_paths.py",
        } <= client_files
        assert "ayon_katana/hooks/prepare_kitsu_credentials.py" not in client_files
        assert "ayon_katana/resources/Startup/init.py" in client_files
        assert {
            "ayon_katana/api/compat.py",
            "ayon_katana/api/image.py",
            "ayon_katana/api/instances.py",
            "ayon_katana/api/lib.py",
            "ayon_katana/api/render.py",
            "ayon_katana/api/usd.py",
            "ayon_katana/plugins/create/create_render.py",
            "ayon_katana/plugins/create/create_image.py",
            "ayon_katana/plugins/create/create_usd_layer.py",
            "ayon_katana/plugins/deadline/submit_katana_deadline.py",
            "ayon_katana/plugins/load/load_alembic.py",
            "ayon_katana/plugins/load/load_katana.py",
            "ayon_katana/plugins/load/load_image.py",
            "ayon_katana/plugins/load/load_usd.py",
            "ayon_katana/plugins/load/clear_usd_resolver_cache.py",
            "ayon_katana/plugins/publish/collect_render.py",
            "ayon_katana/plugins/publish/collect_image.py",
            "ayon_katana/plugins/publish/collect_usd_layer.py",
            "ayon_katana/plugins/publish/extract_usd_layer.py",
            "ayon_katana/plugins/publish/validate_render.py",
            "ayon_katana/plugins/publish/validate_image.py",
            "ayon_katana/plugins/publish/validate_usd_layer.py",
            "ayon_katana/plugins/workfile_build/create_placeholder.py",
            "ayon_katana/plugins/workfile_build/script_placeholder.py",
        }.issubset(client_files)


def test_package_build_is_reproducible(tmp_path: Path) -> None:
    """Identical sources must produce byte-for-byte identical addon archives."""
    first_path = build_package(tmp_path / "first")
    second_path = build_package(tmp_path / "second")

    assert first_path.read_bytes() == second_path.read_bytes()

    with zipfile.ZipFile(first_path) as addon_archive:
        assert all(
            info.date_time == _ZIP_TIMESTAMP for info in addon_archive.infolist()
        )
        client_payload = addon_archive.read("private/client.zip")

    with zipfile.ZipFile(io.BytesIO(client_payload)) as client_archive:
        assert all(
            info.date_time == _ZIP_TIMESTAMP for info in client_archive.infolist()
        )


def test_package_normalizes_python_line_endings_only(tmp_path: Path) -> None:
    """Package Python source identically across Windows and Linux checkouts."""
    python_source = tmp_path / "module.py"
    binary_resource = tmp_path / "resource.bin"
    python_source.write_bytes(b'print("katana")\r\nvalue = 1\r')
    binary_resource.write_bytes(b"\x00\r\n\x01\r")

    output_stream = io.BytesIO()
    with zipfile.ZipFile(output_stream, "w", zipfile.ZIP_DEFLATED) as archive:
        _write_file(archive, python_source, "module.py")
        _write_file(archive, binary_resource, "resource.bin")

    with zipfile.ZipFile(io.BytesIO(output_stream.getvalue())) as archive:
        assert archive.read("module.py") == b'print("katana")\nvalue = 1\n'
        assert archive.read("resource.bin") == b"\x00\r\n\x01\r"


def test_package_matches_across_lf_and_crlf_checkouts(
    monkeypatch,
    tmp_path: Path,
) -> None:
    """Equivalent LF and CRLF source trees must produce identical archives."""

    def build_fixture(root: Path, newline: bytes) -> bytes:
        package_path = root / "package.py"
        server_root = root / "server"
        client_root = root / "client" / "ayon_katana"
        version_path = client_root / "version.py"
        server_root.mkdir(parents=True)
        client_root.mkdir(parents=True)

        package_path.write_bytes(
            newline.join((b'name = "katana"', b'version = "0.1.64"', b""))
        )
        (server_root / "addon.py").write_bytes(newline.join((b'HOST = "katana"', b"")))
        version_path.write_bytes(newline.join((b'__version__ = "0.1.64"', b"")))
        (client_root / "addon.py").write_bytes(newline.join((b'HOST = "katana"', b"")))
        (client_root / "resource.bin").write_bytes(b"\x00\r\n\x01\r")

        monkeypatch.setattr("create_package.PACKAGE_METADATA_PATH", package_path)
        monkeypatch.setattr("create_package.SERVER_ROOT", server_root)
        monkeypatch.setattr("create_package.CLIENT_ROOT", client_root)
        monkeypatch.setattr("create_package.CLIENT_VERSION_PATH", version_path)

        built_path = build_package(root / "output")
        return built_path.read_bytes()

    lf_package = build_fixture(tmp_path / "lf", b"\n")
    crlf_package = build_fixture(tmp_path / "crlf", b"\r\n")

    assert lf_package == crlf_package


def test_package_requires_core_workfile_builder_triggers() -> None:
    """The addon cannot resolve against Core versions missing trigger APIs."""
    assert PACKAGE_METADATA["ayon_required_addons"]["core"] == ">=1.9.9"


def test_package_builder_syncs_client_version(monkeypatch, tmp_path: Path) -> None:
    """Ynput release builds must synchronize client metadata from package.py."""
    version_path = tmp_path / "version.py"
    version_path.write_text(
        '"""Client version."""\n\n__version__ = "0.1.62+dev"\n',
        encoding="utf-8",
    )
    monkeypatch.setattr("create_package.CLIENT_VERSION_PATH", version_path)

    _sync_client_version("0.1.63")

    assert version_path.read_text(encoding="utf-8") == (
        '"""Client version."""\n\n__version__ = "0.1.63"\n'
    )


def test_addon_version_is_declared_only_in_runtime_metadata() -> None:
    """Keep runtime version assignments centralized in package/client metadata."""
    expected_paths = {
        Path("package.py"),
        Path("client/ayon_katana/version.py"),
    }
    ignored_parts = {".artifacts", ".git", ".idea", ".venv", "package", "site"}
    assignment = re.compile(
        rf"(?m)^(?:version|__version__)\s*=\s*[\"']"
        rf"{re.escape(ADDON_VERSION)}[\"']\s*$"
    )
    matching_paths = set()
    for path in ROOT.rglob("*.py"):
        relative_path = path.relative_to(ROOT)
        if ignored_parts.intersection(relative_path.parts) or any(
            part.startswith(".pytest-") for part in relative_path.parts
        ):
            continue
        if assignment.search(path.read_text(encoding="utf-8")):
            matching_paths.add(relative_path)

    assert matching_paths == expected_paths


def test_extracted_client_imports_without_repository_client(tmp_path: Path) -> None:
    """Import the extracted client archive without the repository on ``sys.path``."""
    package_path = build_package(tmp_path)
    extracted_path = extract_package(package_path, tmp_path)
    client_archive = extracted_path / "private" / "client.zip"
    stub_root = tmp_path / "stubs"
    ayon_core_root = stub_root / "ayon_core"
    ayon_core_root.mkdir(parents=True)
    (ayon_core_root / "__init__.py").write_text("", encoding="utf-8")
    (ayon_core_root / "addon.py").write_text(
        "class AYONAddon:\n    pass\n\nclass IHostAddon:\n    pass\n",
        encoding="utf-8",
    )
    environment = os.environ.copy()
    environment["PYTHONPATH"] = os.pathsep.join((str(stub_root), str(client_archive)))
    command = (
        "import ayon_katana; "
        f"assert ayon_katana.__version__ == {ADDON_VERSION!r}; "
        "assert 'client.zip' in ayon_katana.__file__"
    )

    result = subprocess.run(
        [sys.executable, "-c", command],
        cwd=tmp_path,
        env=environment,
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
