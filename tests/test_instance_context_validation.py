"""Tests for Katana instance context validation."""

from __future__ import annotations

import ast
import importlib.util
import sys
import types
from pathlib import Path

import pytest

ROOT = Path(__file__).parents[1]


class FakePublishValidationError(RuntimeError):
    """Minimal AYON validation error carrying its description."""

    def __init__(self, message: str, *, description: str | None = None, **_kwargs):
        super().__init__(message)
        self.description = description


class FakeOptionalPyblishPluginMixin:
    """Minimal optional-plugin behavior used by the validator."""

    def is_active(self, data: dict) -> bool:
        """Return the stored active state, defaulting to enabled."""
        values = self.get_attr_values_from_data(data)
        return bool(values.get("active", True))

    def get_attr_values_from_data(self, data: dict) -> dict:
        """Return values stored for this publish plugin."""
        return (data.get("publish_attributes") or {}).get(self.__class__.__name__, {})


class FakeAction:
    """Minimal Pyblish action base class."""


class FakeInstancePlugin:
    """Minimal Katana instance-plugin base class."""


class FakeNode:
    """Minimal Katana node with a stable global name."""

    def __init__(self, name: str) -> None:
        self.name = name

    def getName(self) -> str:
        """Return the Katana node name."""
        return self.name


class FakeContext(list):
    """List-like publish context with current AYON context data."""

    def __init__(self, folder_path: str, task: str, errored_instances=None):
        super().__init__(errored_instances or [])
        self.data = {"folderPath": folder_path, "task": task}
        self.errored_instances = list(errored_instances or [])


class FakeInstance:
    """Minimal persisted or runtime publish instance."""

    def __init__(self, name: str, data: dict, context: FakeContext) -> None:
        self.name = name
        self.data = data
        self.context = context


class FakeCreateContext:
    """Record metadata updates performed by the repair action."""

    def __init__(self, instances: dict[str, dict]) -> None:
        self.instances = instances
        self.save_calls = 0

    def get_instance_by_id(self, instance_id: str):
        """Return one persisted creator instance."""
        return self.instances.get(instance_id)

    def save_changes(self) -> None:
        """Record persistence through AYON Core."""
        self.save_calls += 1


def _load_modules(monkeypatch):
    """Load production actions and validator with compact dependency fakes."""
    selections = []
    nodes = {"renderMain": FakeNode("renderMain")}

    pyblish_api = types.ModuleType("pyblish.api")
    pyblish_api.Action = FakeAction
    pyblish_api.ContextPlugin = type("ContextPlugin", (), {})
    pyblish_module = types.ModuleType("pyblish")
    pyblish_module.api = pyblish_api
    monkeypatch.setitem(sys.modules, "pyblish", pyblish_module)
    monkeypatch.setitem(sys.modules, "pyblish.api", pyblish_api)

    publish_module = types.ModuleType("ayon_core.pipeline.publish")
    publish_module.OptionalPyblishPluginMixin = FakeOptionalPyblishPluginMixin
    publish_module.PublishValidationError = FakePublishValidationError
    publish_module.RepairAction = type("RepairAction", (FakeAction,), {})
    publish_module.ValidateContentsOrder = 1.1
    publish_module.get_errored_instances_from_context = lambda context, plugin=None: (
        context.errored_instances
    )
    pipeline_module = types.ModuleType("ayon_core.pipeline")
    pipeline_module.publish = publish_module
    core_module = types.ModuleType("ayon_core")
    core_module.pipeline = pipeline_module
    monkeypatch.setitem(sys.modules, "ayon_core", core_module)
    monkeypatch.setitem(sys.modules, "ayon_core.pipeline", pipeline_module)
    monkeypatch.setitem(sys.modules, "ayon_core.pipeline.publish", publish_module)

    compat_module = types.SimpleNamespace(
        get_node=lambda name: nodes.get(name),
        set_selected_nodes=lambda selected: selections.append(list(selected)),
    )
    render_module = types.SimpleNamespace()
    plugin_module = types.SimpleNamespace(KatanaInstancePlugin=FakeInstancePlugin)

    ayon_katana = types.ModuleType("ayon_katana")
    ayon_katana.__path__ = []
    api_package = types.ModuleType("ayon_katana.api")
    api_package.__path__ = []
    api_package.compat = compat_module
    api_package.plugin = plugin_module
    api_package.render = render_module
    plugins_package = types.ModuleType("ayon_katana.plugins")
    plugins_package.__path__ = []
    publish_package = types.ModuleType("ayon_katana.plugins.publish")
    publish_package.__path__ = []
    monkeypatch.setitem(sys.modules, "ayon_katana", ayon_katana)
    monkeypatch.setitem(sys.modules, "ayon_katana.api", api_package)
    monkeypatch.setitem(sys.modules, "ayon_katana.api.compat", compat_module)
    monkeypatch.setitem(sys.modules, "ayon_katana.api.plugin", plugin_module)
    monkeypatch.setitem(sys.modules, "ayon_katana.api.render", render_module)
    monkeypatch.setitem(sys.modules, "ayon_katana.plugins", plugins_package)
    monkeypatch.setitem(sys.modules, "ayon_katana.plugins.publish", publish_package)

    actions_path = (
        ROOT / "client" / "ayon_katana" / "plugins" / "publish" / "actions.py"
    )
    actions_spec = importlib.util.spec_from_file_location(
        "ayon_katana.plugins.publish.actions", actions_path
    )
    assert actions_spec is not None and actions_spec.loader is not None
    actions = importlib.util.module_from_spec(actions_spec)
    monkeypatch.setitem(sys.modules, "ayon_katana.plugins.publish.actions", actions)
    actions_spec.loader.exec_module(actions)

    validator_path = (
        ROOT
        / "client"
        / "ayon_katana"
        / "plugins"
        / "publish"
        / "validate_instance_in_context.py"
    )
    validator_spec = importlib.util.spec_from_file_location(
        "ayon_katana.plugins.publish.validate_instance_in_context",
        validator_path,
    )
    assert validator_spec is not None and validator_spec.loader is not None
    validator = importlib.util.module_from_spec(validator_spec)
    monkeypatch.setitem(
        sys.modules,
        "ayon_katana.plugins.publish.validate_instance_in_context",
        validator,
    )
    validator_spec.loader.exec_module(validator)
    return actions, validator, nodes, selections


def _instance(context: FakeContext, **overrides) -> FakeInstance:
    """Return a persisted Katana instance matching the current context."""
    data = {
        "folderPath": context.data["folderPath"],
        "task": context.data["task"],
        "instance_node": "renderMain",
        "instance_id": "instance-id",
    }
    data.update(overrides)
    return FakeInstance("renderMain", data, context)


def test_valid_instance_matches_current_context(monkeypatch) -> None:
    """Matching persisted folder and task data pass validation."""
    _actions, validator, _nodes, _selections = _load_modules(monkeypatch)
    context = FakeContext("/shots/sq01/sh010", "lighting")

    validator.ValidateInstanceInContextKatana().process(_instance(context))


def test_mismatched_folder_or_task_fails_loudly(monkeypatch) -> None:
    """A persisted context mismatch raises publish validation errors."""
    _actions, validator, _nodes, _selections = _load_modules(monkeypatch)
    context = FakeContext("/shots/sq01/sh010", "lighting")

    with pytest.raises(FakePublishValidationError, match="different asset"):
        validator.ValidateInstanceInContextKatana().process(
            _instance(context, folderPath="/shots/sq01/sh020")
        )
    with pytest.raises(FakePublishValidationError, match="different asset"):
        validator.ValidateInstanceInContextKatana().process(
            _instance(context, task="compositing")
        )


def test_optional_disable_and_runtime_instances_are_skipped(monkeypatch) -> None:
    """Disabled validation and derived runtime instances do not fail."""
    _actions, validator, _nodes, _selections = _load_modules(monkeypatch)
    context = FakeContext("/shots/sq01/sh010", "lighting")
    disabled = _instance(
        context,
        folderPath="/shots/sq01/sh020",
        publish_attributes={"ValidateInstanceInContextKatana": {"active": False}},
    )
    runtime = FakeInstance(
        "beautyAOV",
        {"folderPath": "/shots/sq01/sh020", "task": "compositing"},
        context,
    )

    plugin = validator.ValidateInstanceInContextKatana()
    plugin.process(disabled)
    plugin.process(runtime)


def test_selection_action_selects_failed_instance_node(monkeypatch) -> None:
    """The existing Katana action selects the failed outer instance node."""
    actions, validator, nodes, selections = _load_modules(monkeypatch)
    context = FakeContext("/shots/sq01/sh010", "lighting")
    instance = _instance(context, folderPath="/shots/sq01/sh020")
    context.errored_instances = [instance]

    actions.SelectInvalidInstanceNodes().process(
        context,
        validator.ValidateInstanceInContextKatana,
    )

    assert selections == [[nodes["renderMain"]]]


def test_repair_updates_creator_metadata_and_persists(monkeypatch) -> None:
    """Repair changes AYON metadata only and saves through CreateContext."""
    _actions, validator, _nodes, _selections = _load_modules(monkeypatch)
    context = FakeContext("/shots/sq01/sh010", "lighting")
    stored_instance = {
        "folderPath": "/shots/sq01/sh020",
        "task": "compositing",
    }
    create_context = FakeCreateContext({"instance-id": stored_instance})
    context.data["create_context"] = create_context
    instance = _instance(
        context,
        folderPath=stored_instance["folderPath"],
        task=stored_instance["task"],
    )

    validator.ValidateInstanceInContextKatana.repair(instance)

    assert stored_instance == {
        "folderPath": "/shots/sq01/sh010",
        "task": "lighting",
    }
    assert create_context.save_calls == 1


def test_server_settings_enable_optional_instance_context_validation() -> None:
    """Server defaults keep the optional validator disabled."""
    settings_source = (ROOT / "server" / "settings" / "main.py").read_text(
        encoding="utf-8"
    )
    settings_tree = ast.parse(settings_source)
    defaults_assignment = next(
        node
        for node in settings_tree.body
        if isinstance(node, ast.Assign)
        and any(
            isinstance(target, ast.Name) and target.id == "DEFAULT_VALUES"
            for target in node.targets
        )
    )
    defaults = ast.literal_eval(defaults_assignment.value)

    assert defaults["publish"]["ValidateInstanceInContextKatana"] == {
        "enabled": True,
        "optional": True,
        "active": True,
    }
