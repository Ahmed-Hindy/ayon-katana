"""Tests for the Katana workfile host contract."""

from __future__ import annotations

import importlib.util
import sys
import types
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).parents[1]


class FakeKatanaFile:
    """Record native Katana workfile operations."""

    dirty = False
    loaded_paths: list[str] = []
    saved_paths: list[str] = []
    new_calls = 0

    @classmethod
    def IsFileDirty(cls):
        """Return the configured dirty state."""
        return cls.dirty

    @classmethod
    def Save(cls, path):
        """Record a save destination."""
        cls.saved_paths.append(path)

    @classmethod
    def Load(cls, path):
        """Record an opened workfile."""
        cls.loaded_paths.append(path)

    @classmethod
    def New(cls):
        """Record a new-scene operation."""
        cls.new_calls += 1


class FakeNodegraphAPI:
    """Expose a configurable current Katana project path."""

    project_path = ""

    @classmethod
    def GetProjectFile(cls):
        """Return the configured current project path."""
        return cls.project_path


def _load_workio(monkeypatch):
    """Load workio with a compact fake Katana module."""
    FakeKatanaFile.dirty = False
    FakeKatanaFile.loaded_paths = []
    FakeKatanaFile.saved_paths = []
    FakeKatanaFile.new_calls = 0
    FakeNodegraphAPI.project_path = ""

    katana_module = types.ModuleType("Katana")
    katana_module.KatanaFile = FakeKatanaFile
    katana_module.NodegraphAPI = FakeNodegraphAPI
    monkeypatch.setitem(sys.modules, "Katana", katana_module)

    module_name = "ayon_katana_workio_lifecycle_test"
    module_path = PROJECT_ROOT / "client" / "ayon_katana" / "api" / "workio.py"
    module_spec = importlib.util.spec_from_file_location(module_name, module_path)
    assert module_spec is not None
    assert module_spec.loader is not None
    module = importlib.util.module_from_spec(module_spec)
    monkeypatch.setitem(sys.modules, module_name, module)
    module_spec.loader.exec_module(module)
    return module


def test_unsaved_scene_returns_none(monkeypatch) -> None:
    """AYON Core represents an untitled workfile with ``None``."""
    module = _load_workio(monkeypatch)

    assert module.get_current_workfile() is None


def test_saved_scene_returns_native_path(monkeypatch, tmp_path: Path) -> None:
    """A saved Katana project returns its native project path unchanged."""
    module = _load_workio(monkeypatch)
    project_path = tmp_path / "scene.katana"
    FakeNodegraphAPI.project_path = str(project_path)

    assert module.get_current_workfile() == str(project_path)


def test_save_as_uses_normalized_filesystem_path(monkeypatch, tmp_path: Path) -> None:
    """Save As delegates one normalized ``.katana`` path to Katana."""
    module = _load_workio(monkeypatch)
    destination = tmp_path / "folder" / ".." / "scene.katana"

    saved_path = module.save_workfile(str(destination))

    expected_path = str((tmp_path / "scene.katana").resolve())
    assert saved_path == expected_path
    assert FakeKatanaFile.saved_paths == [expected_path]


def test_open_requires_existing_katana_file(monkeypatch, tmp_path: Path) -> None:
    """Opening fails loudly for missing or non-Katana workfiles."""
    module = _load_workio(monkeypatch)
    missing_path = tmp_path / "missing.katana"

    with pytest.raises(ValueError, match="does not exist"):
        module.open_workfile(str(missing_path))

    invalid_path = tmp_path / "scene.blend"
    invalid_path.write_text("invalid", encoding="utf-8")
    with pytest.raises(ValueError, match=".katana extension"):
        module.open_workfile(str(invalid_path))


def test_open_delegates_existing_normalized_path(monkeypatch, tmp_path: Path) -> None:
    """Opening delegates exactly one normalized path to Katana."""
    module = _load_workio(monkeypatch)
    project_path = tmp_path / "scene.katana"
    project_path.write_text("katana", encoding="utf-8")

    opened_path = module.open_workfile(str(project_path))

    expected_path = str(project_path.resolve())
    assert opened_path == expected_path
    assert FakeKatanaFile.loaded_paths == [expected_path]


def test_uri_workfiles_remain_unsupported(monkeypatch) -> None:
    """Katana uses filesystem-backed workfiles consistently."""
    module = _load_workio(monkeypatch)

    with pytest.raises(ValueError, match="asset identifiers"):
        module.save_workfile("ayon://project/folder/workfile.katana")


def test_dirty_state_and_new_scene_delegate_to_katana(monkeypatch) -> None:
    """Dirty-state and new-scene operations remain native host calls."""
    module = _load_workio(monkeypatch)
    FakeKatanaFile.dirty = True

    assert module.workfile_has_unsaved_changes() is True
    module.new_workfile()
    assert FakeKatanaFile.new_calls == 1
