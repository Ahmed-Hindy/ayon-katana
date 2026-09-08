"""Tests for safe Katana workfile publishing."""

from __future__ import annotations

import importlib.util
import logging
import sys
import types
from pathlib import Path

import pytest

ROOT = Path(__file__).parents[1]


class FakePublishError(RuntimeError):
    """Stand in for AYON's generic publish error."""


class FakeOptionalPyblishPluginMixin:
    """Minimal optional-plugin activation mixin."""

    def is_active(self, data: dict) -> bool:
        """Return the stored active state, defaulting to enabled."""
        attributes = (data.get("publish_attributes") or {}).get(
            self.__class__.__name__, {}
        )
        return bool(attributes.get("active", True))


class FakePublishValidationError(FakePublishError):
    """Stand in for AYON's publish validation error."""

    def __init__(self, message: str, *, title: str | None = None) -> None:
        super().__init__(message)
        self.title = title


class FakeHost:
    """Minimal workfile host that saves to its current path."""

    def __init__(self, path: Path | str, *, dirty: bool = False) -> None:
        self.path = str(path)
        self.dirty = dirty
        self.save_calls: list[str] = []
        self.save_error: Exception | None = None

    def get_current_workfile(self) -> str:
        """Return the current fake scene path."""
        return self.path

    def workfile_has_unsaved_changes(self) -> bool:
        """Return whether the fake scene is dirty."""
        return self.dirty

    def save_workfile(self, path: str) -> str:
        """Save only to the supplied current scene path."""
        self.save_calls.append(path)
        if self.save_error is not None:
            raise self.save_error
        Path(path).write_text("saved scene", encoding="utf-8")
        self.dirty = False
        return path


def _load_module(module_name: str, path: Path, monkeypatch):
    """Load one module under its package-qualified name."""
    module_spec = importlib.util.spec_from_file_location(module_name, path)
    assert module_spec is not None
    assert module_spec.loader is not None
    module = importlib.util.module_from_spec(module_spec)
    monkeypatch.setitem(sys.modules, module_name, module)
    module_spec.loader.exec_module(module)
    return module


def _load_publish_modules(monkeypatch, host: FakeHost):
    """Load workfile publish modules with compact Katana and AYON fakes."""
    pyblish_api = types.ModuleType("pyblish.api")
    pyblish_api.CollectorOrder = 0.1
    pyblish_api.ValidatorOrder = 1.0
    pyblish_api.ExtractorOrder = 2.0
    pyblish_api.ContextPlugin = object
    pyblish_api.InstancePlugin = object
    pyblish_module = types.ModuleType("pyblish")
    pyblish_module.api = pyblish_api
    monkeypatch.setitem(sys.modules, "pyblish", pyblish_module)
    monkeypatch.setitem(sys.modules, "pyblish.api", pyblish_api)

    katana_module = types.ModuleType("Katana")
    katana_module.KatanaFile = types.SimpleNamespace(
        IsFileDirty=lambda: host.dirty,
        Save=host.save_workfile,
        Load=lambda _path: None,
        New=lambda: None,
    )
    katana_module.NodegraphAPI = types.SimpleNamespace(
        GetProjectFile=host.get_current_workfile,
    )
    monkeypatch.setitem(sys.modules, "Katana", katana_module)

    ayon_core_pipeline = types.ModuleType("ayon_core.pipeline")
    ayon_core_pipeline.OptionalPyblishPluginMixin = FakeOptionalPyblishPluginMixin
    ayon_core_pipeline.PublishError = FakePublishError
    ayon_core_pipeline.registered_host = lambda: host
    ayon_core_pipeline.publish = types.SimpleNamespace(
        Extractor=type(
            "Extractor",
            (),
            {"log": logging.getLogger("test_workfile_publish")},
        ),
    )
    ayon_core_publish = types.ModuleType("ayon_core.pipeline.publish")
    ayon_core_publish.PublishError = FakePublishError
    ayon_core_publish.PublishValidationError = FakePublishValidationError
    ayon_core_module = types.ModuleType("ayon_core")
    ayon_core_module.pipeline = ayon_core_pipeline
    monkeypatch.setitem(sys.modules, "ayon_core", ayon_core_module)
    monkeypatch.setitem(sys.modules, "ayon_core.pipeline", ayon_core_pipeline)
    monkeypatch.setitem(
        sys.modules,
        "ayon_core.pipeline.publish",
        ayon_core_publish,
    )

    package_module = types.ModuleType("ayon_katana")
    package_module.__path__ = []
    api_module = types.ModuleType("ayon_katana.api")
    api_module.__path__ = []
    plugin_module = types.ModuleType("ayon_katana.api.plugin")
    plugin_module.KatanaContextPlugin = type(
        "KatanaContextPlugin",
        (),
        {"log": logging.getLogger("test_workfile_publish")},
    )
    plugin_module.KatanaInstancePlugin = type("KatanaInstancePlugin", (), {})
    plugin_module.KatanaExtractorPlugin = ayon_core_pipeline.publish.Extractor
    publish_package = types.ModuleType("ayon_katana.plugins.publish")
    publish_package.__path__ = []
    plugins_package = types.ModuleType("ayon_katana.plugins")
    plugins_package.__path__ = []
    monkeypatch.setitem(sys.modules, "ayon_katana", package_module)
    monkeypatch.setitem(sys.modules, "ayon_katana.api", api_module)
    monkeypatch.setitem(sys.modules, "ayon_katana.api.plugin", plugin_module)
    monkeypatch.setitem(sys.modules, "ayon_katana.plugins", plugins_package)
    monkeypatch.setitem(
        sys.modules,
        "ayon_katana.plugins.publish",
        publish_package,
    )

    workio = _load_module(
        "ayon_katana.api.workio",
        ROOT / "client" / "ayon_katana" / "api" / "workio.py",
        monkeypatch,
    )
    api_module.plugin = plugin_module
    api_module.workio = workio

    modules = {
        "collect": _load_module(
            "ayon_katana.plugins.publish.collect_current_file",
            ROOT
            / "client"
            / "ayon_katana"
            / "plugins"
            / "publish"
            / "collect_current_file.py",
            monkeypatch,
        ),
        "validate": _load_module(
            "ayon_katana.plugins.publish.validate_workfile_saved",
            ROOT
            / "client"
            / "ayon_katana"
            / "plugins"
            / "publish"
            / "validate_workfile_saved.py",
            monkeypatch,
        ),
        "save": _load_module(
            "ayon_katana.plugins.publish.save_current_scene",
            ROOT
            / "client"
            / "ayon_katana"
            / "plugins"
            / "publish"
            / "save_current_scene.py",
            monkeypatch,
        ),
        "extract": _load_module(
            "ayon_katana.plugins.publish.extract_workfile",
            ROOT
            / "client"
            / "ayon_katana"
            / "plugins"
            / "publish"
            / "extract_workfile.py",
            monkeypatch,
        ),
    }
    modules["workio"] = workio
    return modules


def _context(path: Path | str) -> types.SimpleNamespace:
    """Create a lightweight Pyblish context."""
    return types.SimpleNamespace(data={"currentFile": str(path)})


def test_collect_preserves_unsupported_asset_identifier_for_validation(
    monkeypatch,
) -> None:
    """Asset identifiers should be rejected explicitly, not hidden as empty paths."""
    host = FakeHost("asset://project/scene.katana")
    modules = _load_publish_modules(monkeypatch, host)
    context = types.SimpleNamespace(data={})

    modules["collect"].CollectKatanaCurrentFile().process(context)

    assert context.data["currentFile"] == "asset://project/scene.katana"
    with pytest.raises(FakePublishValidationError, match="asset identifiers"):
        modules["validate"].ValidateWorkfileSaved().process(context)


def test_validate_rejects_never_saved_scene(monkeypatch) -> None:
    """An empty scene path must not pass workfile validation."""
    modules = _load_publish_modules(monkeypatch, FakeHost(""))

    with pytest.raises(FakePublishValidationError, match="path is empty"):
        modules["validate"].ValidateWorkfileSaved().process(_context(""))


def test_validate_rejects_wrong_extension(monkeypatch, tmp_path: Path) -> None:
    """Only filesystem .katana workfiles are publishable."""
    scene_path = tmp_path / "scene.hip"
    scene_path.touch()
    modules = _load_publish_modules(monkeypatch, FakeHost(scene_path))

    with pytest.raises(FakePublishValidationError, match=".katana extension"):
        modules["validate"].ValidateWorkfileSaved().process(_context(scene_path))


def test_validate_rejects_missing_workfile(monkeypatch, tmp_path: Path) -> None:
    """A missing filesystem path must not pass workfile validation."""
    scene_path = tmp_path / "missing.katana"
    modules = _load_publish_modules(monkeypatch, FakeHost(scene_path))

    with pytest.raises(FakePublishValidationError, match="does not exist"):
        modules["validate"].ValidateWorkfileSaved().process(_context(scene_path))


def test_save_plugin_runs_after_validation_and_before_extraction(monkeypatch) -> None:
    """The in-place save must finish before workfile staging can begin."""
    modules = _load_publish_modules(monkeypatch, FakeHost(""))

    assert (
        modules["validate"].ValidateWorkfileSaved.order
        < modules["save"].SaveCurrentScene.order
        < modules["extract"].ExtractWorkfile.order
    )


def test_save_current_scene_skips_clean_saved_scene(
    monkeypatch,
    tmp_path: Path,
) -> None:
    """A clean saved scene should pass through without another save."""
    scene_path = tmp_path / "scene.katana"
    scene_path.write_text("clean scene", encoding="utf-8")
    host = FakeHost(scene_path, dirty=False)
    modules = _load_publish_modules(monkeypatch, host)
    context = _context(scene_path)

    modules["save"].SaveCurrentScene().process(context)

    assert host.save_calls == []
    assert context.data["currentFile"] == str(scene_path)


def test_save_current_scene_saves_dirty_scene_in_place(
    monkeypatch,
    tmp_path: Path,
) -> None:
    """A dirty scene should be saved to exactly its collected current path."""
    scene_path = tmp_path / "scene.katana"
    scene_path.write_text("stale scene", encoding="utf-8")
    host = FakeHost(scene_path, dirty=True)
    modules = _load_publish_modules(monkeypatch, host)
    context = _context(scene_path)

    modules["save"].SaveCurrentScene().process(context)

    assert host.save_calls == [str(scene_path)]
    assert scene_path.read_text(encoding="utf-8") == "saved scene"
    assert not host.dirty


def test_save_current_scene_rejects_path_changed_after_collection(
    monkeypatch,
    tmp_path: Path,
) -> None:
    """Changing the active path after collection must stop publishing."""
    collected_path = tmp_path / "collected.katana"
    current_path = tmp_path / "current.katana"
    collected_path.touch()
    current_path.touch()
    host = FakeHost(current_path)
    modules = _load_publish_modules(monkeypatch, host)

    with pytest.raises(FakePublishError, match="differs from the active scene"):
        modules["save"].SaveCurrentScene().process(_context(collected_path))


def test_save_current_scene_rejects_file_deleted_after_collection(
    monkeypatch,
    tmp_path: Path,
) -> None:
    """Deleting the collected scene before saving must stop publishing."""
    scene_path = tmp_path / "deleted.katana"
    scene_path.touch()
    host = FakeHost(scene_path, dirty=True)
    modules = _load_publish_modules(monkeypatch, host)
    scene_path.unlink()

    with pytest.raises(FakePublishError, match="does not exist"):
        modules["save"].SaveCurrentScene().process(_context(scene_path))


def test_save_failure_propagates_without_staging_stale_data(
    monkeypatch,
    tmp_path: Path,
) -> None:
    """A failed save must not make stale on-disk data available to extraction."""
    scene_path = tmp_path / "scene.katana"
    scene_path.write_text("stale scene", encoding="utf-8")
    host = FakeHost(scene_path, dirty=True)
    host.save_error = RuntimeError("disk full")
    modules = _load_publish_modules(monkeypatch, host)
    context = _context(scene_path)
    staging_dir = tmp_path / "staging"

    with pytest.raises(RuntimeError, match="disk full"):
        modules["save"].SaveCurrentScene().process(context)

    assert scene_path.read_text(encoding="utf-8") == "stale scene"
    assert not staging_dir.exists()


def test_extract_stages_only_clean_path_consistent_workfile(
    monkeypatch,
    tmp_path: Path,
) -> None:
    """Extraction should copy only the clean active scene into staging."""
    scene_path = tmp_path / "scene.katana"
    scene_path.write_text("saved scene", encoding="utf-8")
    host = FakeHost(scene_path)
    modules = _load_publish_modules(monkeypatch, host)
    staging_dir = tmp_path / "staging"
    staging_dir.mkdir()
    context = _context(scene_path)
    instance = types.SimpleNamespace(context=context, data={})
    extractor = modules["extract"].ExtractWorkfile()
    extractor.staging_dir = lambda _instance: str(staging_dir)

    extractor.process(instance)

    staged_path = staging_dir / scene_path.name
    assert staged_path.read_text(encoding="utf-8") == "saved scene"
    assert instance.data["representations"] == [
        {
            "name": "katana",
            "ext": "katana",
            "files": scene_path.name,
            "stagingDir": str(staging_dir),
        }
    ]


def test_extract_does_not_copy_when_destination_is_source(
    monkeypatch,
    tmp_path: Path,
) -> None:
    """Staging to the source directory must not copy a file onto itself."""
    scene_path = tmp_path / "scene.katana"
    scene_path.write_text("saved scene", encoding="utf-8")
    host = FakeHost(scene_path)
    modules = _load_publish_modules(monkeypatch, host)
    instance = types.SimpleNamespace(context=_context(scene_path), data={})
    extractor = modules["extract"].ExtractWorkfile()
    extractor.staging_dir = lambda _instance: str(tmp_path)
    monkeypatch.setattr(
        modules["extract"].shutil,
        "copy2",
        lambda *_args: pytest.fail("source must not be copied onto itself"),
    )

    extractor.process(instance)

    assert instance.data["representations"][0]["stagingDir"] == str(tmp_path)


def test_extract_rejects_dirty_scene(monkeypatch, tmp_path: Path) -> None:
    """Extraction must not stage a source that is still dirty."""
    scene_path = tmp_path / "scene.katana"
    scene_path.touch()
    host = FakeHost(scene_path, dirty=True)
    modules = _load_publish_modules(monkeypatch, host)
    instance = types.SimpleNamespace(context=_context(scene_path), data={})
    extractor = modules["extract"].ExtractWorkfile()
    extractor.staging_dir = lambda _instance: str(tmp_path / "staging")

    with pytest.raises(FakePublishError, match="unsaved changes"):
        extractor.process(instance)


def test_extract_rejects_path_changed_after_save(monkeypatch, tmp_path: Path) -> None:
    """Extraction repeats the active-path check before it copies any data."""
    collected_path = tmp_path / "collected.katana"
    active_path = tmp_path / "active.katana"
    collected_path.touch()
    active_path.touch()
    host = FakeHost(active_path)
    modules = _load_publish_modules(monkeypatch, host)
    instance = types.SimpleNamespace(context=_context(collected_path), data={})
    extractor = modules["extract"].ExtractWorkfile()
    extractor.staging_dir = lambda _instance: str(tmp_path / "staging")

    with pytest.raises(FakePublishError, match="path changed"):
        extractor.process(instance)
