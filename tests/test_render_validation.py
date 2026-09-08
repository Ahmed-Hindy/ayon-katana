"""Tests for Katana cross-instance render validation and repair actions."""

from __future__ import annotations

import ast
import importlib.util
import sys
import types
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).parents[1]


class FakeOptionalPyblishPluginMixin:
    """Minimal optional-plugin activation mixin."""

    def is_active(self, data: dict) -> bool:
        """Return the stored active state, defaulting to enabled."""
        attributes = (data.get("publish_attributes") or {}).get(
            self.__class__.__name__, {}
        )
        return bool(attributes.get("active", True))


class FakePublishValidationError(RuntimeError):
    """Minimal AYON Core validation error carrying Publisher metadata."""

    def __init__(
        self,
        message: str,
        *,
        title: str | None = None,
        description: str | None = None,
    ) -> None:
        super().__init__(message)
        self.title = title
        self.description = description


class FakeContextPlugin:
    """Minimal Pyblish context-plugin base class."""


class FakeAction:
    """Minimal Pyblish action base class."""


class FakeNode:
    """Minimal Katana node with a stable global name."""

    def __init__(self, name: str) -> None:
        self.name = name

    def getName(self) -> str:
        """Return the Katana node name."""
        return self.name


class FakeInstance:
    """Minimal render publish instance backed by an outer Katana Group."""

    def __init__(
        self,
        name: str,
        expected_files: list,
        *,
        integrate: bool = True,
        creator_identifier: str | None = "io.ayon.creators.katana.render",
    ) -> None:
        self.id = name
        self.data = {
            "productName": name,
            "instance_node": name,
            "expectedFiles": expected_files,
            "integrate": integrate,
        }
        if creator_identifier is not None:
            self.data["creator_identifier"] = creator_identifier


class FakeContext(list):
    """List-like Pyblish context exposing instances that failed a plugin."""

    def __init__(self, instances: list, errored_instances: list | None = None):
        super().__init__(instances)
        self.data = {}
        self.errored_instances = errored_instances or []


def _install_packages(monkeypatch, host, output_definitions):
    """Load the new validator and actions with compact Katana and AYON fakes."""
    pyblish_api = types.ModuleType("pyblish.api")
    pyblish_api.ValidatorOrder = 1.0
    pyblish_api.ContextPlugin = FakeContextPlugin
    pyblish_api.Action = FakeAction
    pyblish_api.instances_by_plugin = lambda instances, _plugin: instances
    pyblish_module = types.ModuleType("pyblish")
    pyblish_module.api = pyblish_api
    monkeypatch.setitem(sys.modules, "pyblish", pyblish_module)
    monkeypatch.setitem(sys.modules, "pyblish.api", pyblish_api)

    publish_module = types.ModuleType("ayon_core.pipeline.publish")
    publish_module.PublishValidationError = FakePublishValidationError
    publish_module.get_errored_instances_from_context = lambda context, plugin: (
        context.errored_instances
    )
    pipeline_module = types.ModuleType("ayon_core.pipeline")
    pipeline_module.OptionalPyblishPluginMixin = FakeOptionalPyblishPluginMixin
    pipeline_module.PublishValidationError = FakePublishValidationError
    pipeline_module.publish = publish_module
    ayon_core_module = types.ModuleType("ayon_core")
    ayon_core_module.pipeline = pipeline_module
    monkeypatch.setitem(sys.modules, "ayon_core", ayon_core_module)
    monkeypatch.setitem(sys.modules, "ayon_core.pipeline", pipeline_module)
    monkeypatch.setitem(sys.modules, "ayon_core.pipeline.publish", publish_module)

    compat_module = types.SimpleNamespace(
        get_node=lambda name: host.nodes.get(name),
        set_selected_nodes=lambda nodes: host.selections.append(list(nodes)),
    )
    plugin_module = types.SimpleNamespace(
        KatanaContextPlugin=type("KatanaContextPlugin", (FakeContextPlugin,), {})
    )
    render_module = types.SimpleNamespace(
        get_output_definitions=lambda node: output_definitions.get(node.getName(), []),
        reconnect_render_graph=lambda node: host.reconnected.append(node),
    )

    ayon_katana_module = types.ModuleType("ayon_katana")
    ayon_katana_module.__path__ = []
    api_module = types.ModuleType("ayon_katana.api")
    api_module.__path__ = []
    api_module.compat = compat_module
    api_module.plugin = plugin_module
    api_module.render = render_module
    plugins_module = types.ModuleType("ayon_katana.plugins")
    plugins_module.__path__ = []
    publish_package = types.ModuleType("ayon_katana.plugins.publish")
    publish_package.__path__ = []
    monkeypatch.setitem(sys.modules, "ayon_katana", ayon_katana_module)
    monkeypatch.setitem(sys.modules, "ayon_katana.api", api_module)
    monkeypatch.setitem(sys.modules, "ayon_katana.api.compat", compat_module)
    monkeypatch.setitem(sys.modules, "ayon_katana.api.plugin", plugin_module)
    monkeypatch.setitem(sys.modules, "ayon_katana.api.render", render_module)
    monkeypatch.setitem(sys.modules, "ayon_katana.plugins", plugins_module)
    monkeypatch.setitem(sys.modules, "ayon_katana.plugins.publish", publish_package)

    actions_path = (
        PROJECT_ROOT / "client" / "ayon_katana" / "plugins" / "publish" / "actions.py"
    )
    actions_spec = importlib.util.spec_from_file_location(
        "ayon_katana.plugins.publish.actions",
        actions_path,
    )
    assert actions_spec is not None
    assert actions_spec.loader is not None
    actions_module = importlib.util.module_from_spec(actions_spec)
    monkeypatch.setitem(
        sys.modules,
        "ayon_katana.plugins.publish.actions",
        actions_module,
    )
    actions_spec.loader.exec_module(actions_module)

    validator_path = (
        PROJECT_ROOT
        / "client"
        / "ayon_katana"
        / "plugins"
        / "publish"
        / "validate_render_product_paths_unique.py"
    )
    validator_spec = importlib.util.spec_from_file_location(
        "ayon_katana.plugins.publish.validate_render_product_paths_unique",
        validator_path,
    )
    assert validator_spec is not None
    assert validator_spec.loader is not None
    validator_module = importlib.util.module_from_spec(validator_spec)
    monkeypatch.setitem(
        sys.modules,
        "ayon_katana.plugins.publish.validate_render_product_paths_unique",
        validator_module,
    )
    validator_spec.loader.exec_module(validator_module)
    return actions_module, validator_module


def _new_host() -> types.SimpleNamespace:
    """Return a node registry and side-effect recorders for one test."""
    return types.SimpleNamespace(nodes={}, selections=[], reconnected=[])


def _expected_files(*paths: str) -> list[dict[str, list[str]]]:
    """Return the collected generic AYON expected-files structure."""
    return [{"": list(paths)}]


def test_rejects_identical_sequences_across_two_instances(monkeypatch) -> None:
    """Two render instances cannot write the same concrete sequence."""
    host = _new_host()
    first = FakeInstance(
        "renderMain",
        _expected_files("C:/renders/main.1001.exr", "C:/renders/main.1002.exr"),
    )
    second = FakeInstance(
        "renderAlt",
        _expected_files("C:/renders/main.1001.exr", "C:/renders/main.1002.exr"),
    )
    host.nodes = {name: FakeNode(name) for name in ("renderMain", "renderAlt")}
    _actions, module = _install_packages(monkeypatch, host, {})

    with pytest.raises(FakePublishValidationError) as exc_info:
        module.ValidateRenderProductPathsUnique().process(FakeContext([first, second]))

    message = str(exc_info.value)
    assert "main.1001.exr (renderAlt, renderMain)" in message
    assert "main.1002.exr (renderAlt, renderMain)" in message


def test_optional_collision_validator_can_be_disabled(monkeypatch) -> None:
    """Inactive optional validators do not block colliding render instances."""
    host = _new_host()
    first = FakeInstance("renderMain", _expected_files("C:/renders/main.1001.exr"))
    second = FakeInstance("renderAlt", _expected_files("C:/renders/main.1001.exr"))
    _actions, module = _install_packages(monkeypatch, host, {})
    context = FakeContext([first, second])
    context.data["publish_attributes"] = {
        "ValidateRenderProductPathsUnique": {"active": False}
    }

    module.ValidateRenderProductPathsUnique().process(context)


def test_rejects_partially_overlapping_concrete_sequences(monkeypatch) -> None:
    """Only overlapping concrete frames need to collide for validation to fail."""
    host = _new_host()
    first = FakeInstance(
        "renderMain",
        _expected_files("C:/renders/main.1001.exr", "C:/renders/main.1002.exr"),
    )
    second = FakeInstance(
        "renderAlt",
        _expected_files("C:/renders/main.1002.exr", "C:/renders/main.1003.exr"),
    )
    _actions, module = _install_packages(monkeypatch, host, {})

    with pytest.raises(FakePublishValidationError) as exc_info:
        module.ValidateRenderProductPathsUnique().process(FakeContext([first, second]))

    assert "main.1002.exr" in str(exc_info.value)
    assert "main.1001.exr" not in str(exc_info.value)


def test_treats_case_only_windows_paths_as_collisions(monkeypatch) -> None:
    """Windows output paths collide even when their spelling differs by case."""
    host = _new_host()
    first = FakeInstance("renderMain", _expected_files("C:/Renders/Main.1001.exr"))
    second = FakeInstance("renderAlt", _expected_files("c:/renders/main.1001.exr"))
    _actions, module = _install_packages(monkeypatch, host, {})
    monkeypatch.setattr(module, "_is_windows", lambda: True)

    with pytest.raises(FakePublishValidationError):
        module.ValidateRenderProductPathsUnique().process(FakeContext([first, second]))


def test_allows_same_basename_in_different_directories(monkeypatch) -> None:
    """Directory components remain part of every concrete output path."""
    host = _new_host()
    first = FakeInstance("renderMain", _expected_files("C:/renders/a/main.1001.exr"))
    second = FakeInstance("renderAlt", _expected_files("C:/renders/b/main.1001.exr"))
    _actions, module = _install_packages(monkeypatch, host, {})

    assert (
        module.ValidateRenderProductPathsUnique().get_invalid(
            FakeContext([first, second])
        )
        == []
    )


def test_context_validator_ignores_duplicate_paths_within_one_instance(
    monkeypatch,
) -> None:
    """The instance validator owns duplicate paths within one render graph."""
    host = _new_host()
    instance = FakeInstance(
        "renderMain",
        [
            {"": ["C:/renders/main.1001.exr"]},
            {"diffuse": ["C:/renders/main.1001.exr"]},
        ],
    )
    _actions, module = _install_packages(monkeypatch, host, {})

    assert (
        module.ValidateRenderProductPathsUnique().get_invalid(FakeContext([instance]))
        == []
    )


def test_ignores_non_integrating_render_instance(monkeypatch) -> None:
    """A non-integrating runtime instance cannot block the source render job."""
    host = _new_host()
    first = FakeInstance("renderMain", _expected_files("C:/renders/main.1001.exr"))
    skipped = FakeInstance(
        "runtimeAov",
        _expected_files("C:/renders/main.1001.exr"),
        integrate=False,
    )
    _actions, module = _install_packages(monkeypatch, host, {})

    assert (
        module.ValidateRenderProductPathsUnique().get_invalid(
            FakeContext([first, skipped])
        )
        == []
    )


def test_selection_actions_resolve_outer_and_colliding_output_nodes(
    monkeypatch,
) -> None:
    """Failed validation actions select live Katana instance and output nodes."""
    host = _new_host()
    first = FakeInstance("renderMain", _expected_files("C:/renders/main.1001.exr"))
    second = FakeInstance("renderAlt", _expected_files("C:/renders/main.1001.exr"))
    host.nodes = {
        "renderMain": FakeNode("renderMain"),
        "renderAlt": FakeNode("renderAlt"),
        "outputMain": FakeNode("outputMain"),
        "outputAlt": FakeNode("outputAlt"),
    }
    output_definitions = {
        "renderMain": [
            types.SimpleNamespace(aov_identifier="", node_name="outputMain")
        ],
        "renderAlt": [types.SimpleNamespace(aov_identifier="", node_name="outputAlt")],
    }
    actions, module = _install_packages(monkeypatch, host, output_definitions)
    context = FakeContext([first, second])

    actions.SelectInvalidInstanceNodes().process(
        context,
        module.ValidateRenderProductPathsUnique,
    )
    actions.SelectInvalidOutputNodes().process(
        context,
        module.ValidateRenderProductPathsUnique,
    )

    assert [[node.getName() for node in nodes] for nodes in host.selections] == [
        ["renderAlt", "renderMain"],
        ["outputMain", "outputAlt"],
    ]


def test_reconnect_action_only_touches_ayon_created_render_instances(
    monkeypatch,
) -> None:
    """Reconnect action never rewires a graph without the AYON creator identity."""
    host = _new_host()
    ayon_instance = FakeInstance("ayonRender", _expected_files("C:/renders/a.exr"))
    artist_instance = FakeInstance(
        "artistRender",
        _expected_files("C:/renders/b.exr"),
        creator_identifier=None,
    )
    host.nodes = {
        "ayonRender": FakeNode("ayonRender"),
        "artistRender": FakeNode("artistRender"),
    }
    actions, _module = _install_packages(monkeypatch, host, {})
    context = FakeContext(
        [ayon_instance, artist_instance],
        [ayon_instance, artist_instance],
    )

    actions.ReconnectAYONRenderGraphAction().process(
        context,
        type("FailedRenderPlugin", (), {}),
    )

    assert [node.getName() for node in host.reconnected] == ["ayonRender"]
    assert [[node.getName() for node in nodes] for nodes in host.selections] == [
        ["ayonRender"]
    ]


def test_instance_selection_action_supports_failed_instance_validators(
    monkeypatch,
) -> None:
    """Instance-validator failures select their failed outer instance nodes."""
    host = _new_host()
    first = FakeInstance("renderMain", _expected_files("C:/renders/main.exr"))
    second = FakeInstance("renderAlt", _expected_files("C:/renders/alt.exr"))
    host.nodes = {
        "renderMain": FakeNode("renderMain"),
        "renderAlt": FakeNode("renderAlt"),
    }
    actions, _module = _install_packages(monkeypatch, host, {})
    context = FakeContext([first, second], [first, second])

    actions.SelectInvalidInstanceNodes().process(
        context,
        type("FailedRenderPlugin", (), {}),
    )

    assert [[node.getName() for node in nodes] for nodes in host.selections] == [
        ["renderMain", "renderAlt"]
    ]


def test_server_settings_register_unique_render_path_validator() -> None:
    """The new validator is enabled by default in the server settings schema."""
    settings_source = (PROJECT_ROOT / "server" / "settings" / "main.py").read_text(
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

    assert "ValidateRenderProductPathsUnique" in settings_source
    assert defaults["publish"]["ValidateRenderProductPathsUnique"] == {
        "enabled": True,
        "optional": False,
        "active": True,
    }
