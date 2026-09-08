"""Focused tests for optional post-publish Katana workfile incrementing."""

from __future__ import annotations

import ast
import importlib.util
import os
import sys
import types
from pathlib import Path

import pytest

ROOT = Path(__file__).parents[1]


class FakeLog:
    """Small logger used by context plug-in tests."""

    def debug(self, *_args, **_kwargs) -> None:
        return None


class FakeContextPlugin:
    """Minimal Katana context plug-in base."""

    log = FakeLog()


class FakeOptionalMixin:
    """Read an isolated active state from context data."""

    def is_active(self, data: dict) -> bool:
        return bool(data.get("increment_active", True))


class FakePublishError(RuntimeError):
    """Minimal Core publish error."""


class FakeInstance:
    """Publish instance wrapper."""

    def __init__(self, data: dict) -> None:
        self.data = data


class FakeContext(list):
    """Publish context with mutable shared data."""

    def __init__(self, instances=(), data=None) -> None:
        super().__init__(instances)
        self.data = dict(data or {})


def _load_increment(monkeypatch, calls: dict):
    """Load increment plug-in with pinned Core/Katana behavior stubs."""
    pyblish_api = types.ModuleType("pyblish.api")
    pyblish_api.IntegratorOrder = 3.0
    pyblish = types.ModuleType("pyblish")
    pyblish.api = pyblish_api
    monkeypatch.setitem(sys.modules, "pyblish", pyblish)
    monkeypatch.setitem(sys.modules, "pyblish.api", pyblish_api)

    host = types.SimpleNamespace(
        get_current_workfile=lambda: calls.get(
            "current_path", "C:/work/scene_v001.katana"
        )
    )
    core = types.ModuleType("ayon_core")
    core.__path__ = []
    pipeline = types.ModuleType("ayon_core.pipeline")
    pipeline.__path__ = []
    pipeline.OptionalPyblishPluginMixin = FakeOptionalMixin
    pipeline.registered_host = lambda: host
    publish = types.ModuleType("ayon_core.pipeline.publish")
    publish.PublishError = FakePublishError
    publish.get_errored_plugins_from_context = lambda context: list(
        context.data.get("errored_plugins") or []
    )
    monkeypatch.setitem(sys.modules, "ayon_core", core)
    monkeypatch.setitem(sys.modules, "ayon_core.pipeline", pipeline)
    monkeypatch.setitem(sys.modules, "ayon_core.pipeline.publish", publish)

    host_package = types.ModuleType("ayon_core.host")
    host_package.__path__ = []
    interfaces = types.ModuleType("ayon_core.host.interfaces")

    class SaveWorkfileOptionalData:
        """Record prepared Core save data."""

        def __init__(self, **kwargs) -> None:
            self.data = kwargs

    interfaces.SaveWorkfileOptionalData = SaveWorkfileOptionalData
    monkeypatch.setitem(sys.modules, "ayon_core.host", host_package)
    monkeypatch.setitem(sys.modules, "ayon_core.host.interfaces", interfaces)

    workfile = types.ModuleType("ayon_core.pipeline.workfile")

    def save_next_version(**kwargs) -> None:
        calls.setdefault("saves", []).append(kwargs)
        if calls.get("save_error"):
            raise RuntimeError("disk save failed")

    workfile.save_next_version = save_next_version
    monkeypatch.setitem(sys.modules, "ayon_core.pipeline.workfile", workfile)

    package = types.ModuleType("ayon_katana")
    package.__path__ = []
    api = types.ModuleType("ayon_katana.api")
    api.__path__ = []
    api.plugin = types.SimpleNamespace(KatanaContextPlugin=FakeContextPlugin)
    api.workio = types.SimpleNamespace(
        workfile_paths_match=lambda first, second: (
            os.path.normcase(os.path.normpath(first))
            == os.path.normcase(os.path.normpath(second))
        )
    )
    monkeypatch.setitem(sys.modules, "ayon_katana", package)
    monkeypatch.setitem(sys.modules, "ayon_katana.api", api)
    monkeypatch.setitem(sys.modules, "ayon_katana.api.plugin", api.plugin)
    monkeypatch.setitem(sys.modules, "ayon_katana.api.workio", api.workio)

    path = (
        ROOT
        / "client"
        / "ayon_katana"
        / "plugins"
        / "publish"
        / "increment_current_file.py"
    )
    spec = importlib.util.spec_from_file_location("ayon_katana_increment_test", path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _workfile_context(**overrides) -> FakeContext:
    """Return one active workfile publish context."""
    data = {
        "currentFile": "C:/work/scene_v001.katana",
        "projectEntity": {"name": "Demo"},
        "project_settings": {"katana": {}},
        "anatomy": object(),
        "increment_active": True,
    }
    data.update(overrides)
    return FakeContext(
        [FakeInstance({"productType": "workfile", "active": True, "publish": True})],
        data,
    )


def test_increment_success_uses_core_save_contract_once(monkeypatch) -> None:
    """Successful opt-in uses prepared Core data and is idempotent per context."""
    calls = {"current_path": "C:/work/scene_v001.katana"}
    module = _load_increment(monkeypatch, calls)
    context = _workfile_context()
    plugin = module.IncrementCurrentFile()

    plugin.process(context)
    plugin.process(context)

    assert len(calls["saves"]) == 1
    save = calls["saves"][0]
    assert "scene_v001.katana" in save["description"]
    assert save["prepared_data"].data == {
        "project_entity": context.data["projectEntity"],
        "anatomy": context.data["anatomy"],
        "project_settings": context.data["project_settings"],
    }
    assert context.data[module._INCREMENT_ATTEMPTED_KEY] is True
    assert module.IncrementCurrentFile.order == pytest.approx(12.0)


def test_increment_skips_inactive_failed_or_missing_workfile(monkeypatch) -> None:
    """Inactive settings, prior failures, and absent workfiles never save a version."""
    calls = {}
    module = _load_increment(monkeypatch, calls)

    inactive = _workfile_context(increment_active=False)
    module.IncrementCurrentFile().process(inactive)

    failed = _workfile_context(errored_plugins=[type("FarmSubmitFailure", (), {})])
    module.IncrementCurrentFile().process(failed)

    missing = FakeContext([], dict(_workfile_context().data))
    module.IncrementCurrentFile().process(missing)

    assert calls.get("saves", []) == []


@pytest.mark.parametrize(
    "failed_stage",
    [
        "ExtractUsdLayer",
        "ValidateUsdLookAssignments",
        "FinalizeUsdPublish",
        "SaveCurrentScene",
        "ValidateUsdAssetContributionDefaultPrim",
        "ExtractWorkfile",
        "ExtractUSDLayerContribution",
        "Integrate",
        "KatanaSubmitDeadline",
    ],
)
def test_increment_skips_each_failed_publish_boundary(
    monkeypatch,
    failed_stage,
) -> None:
    """Any earlier publish/farm failure prevents post-publish version-up."""
    calls = {}
    module = _load_increment(monkeypatch, calls)
    failed_plugin = type(failed_stage, (), {})
    context = _workfile_context(errored_plugins=[failed_plugin])

    module.IncrementCurrentFile().process(context)

    assert calls.get("saves", []) == []
    assert module._INCREMENT_ATTEMPTED_KEY not in context.data


def test_increment_rejects_changed_active_workfile(monkeypatch) -> None:
    """A scene change after collection refuses version-up without publish mutation."""
    calls = {"current_path": "C:/work/other_v001.katana"}
    module = _load_increment(monkeypatch, calls)
    context = _workfile_context()

    with pytest.raises(FakePublishError, match="differs from the active scene"):
        module.IncrementCurrentFile().process(context)

    assert calls.get("saves", []) == []
    assert module._INCREMENT_ATTEMPTED_KEY not in context.data


def test_increment_save_failure_is_explicit_and_not_retried(monkeypatch) -> None:
    """Integrated publishes remain published when next-version saving fails."""
    calls = {
        "current_path": "C:/work/scene_v001.katana",
        "save_error": True,
    }
    module = _load_increment(monkeypatch, calls)
    context = _workfile_context()
    plugin = module.IncrementCurrentFile()

    with pytest.raises(FakePublishError, match="Publishing completed"):
        plugin.process(context)

    assert len(calls["saves"]) == 1
    assert context.data[module._INCREMENT_ATTEMPTED_KEY] is True
    plugin.process(context)
    assert len(calls["saves"]) == 1


def test_server_default_keeps_increment_inactive() -> None:
    """Post-publish increment is installed but opt-in by default."""
    source = (ROOT / "server" / "settings" / "main.py").read_text(encoding="utf-8")
    tree = ast.parse(source)
    assignment = next(
        node
        for node in tree.body
        if isinstance(node, ast.Assign)
        and any(
            isinstance(target, ast.Name) and target.id == "DEFAULT_VALUES"
            for target in node.targets
        )
    )
    defaults = ast.literal_eval(assignment.value)["publish"]
    assert defaults["IncrementCurrentFile"] == {
        "enabled": True,
        "optional": True,
        "active": False,
    }
