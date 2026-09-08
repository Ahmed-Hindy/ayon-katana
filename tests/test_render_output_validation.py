"""Tests for strict Katana render output validation."""

from __future__ import annotations

import ast
import importlib.util
import sys
import types
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).parents[1]
PUBLISH_ROOT = PROJECT_ROOT / "client" / "ayon_katana" / "plugins" / "publish"


class FakeOptionalPyblishPluginMixin:
    """Minimal optional plugin mixin."""

    def is_active(self, data):
        attributes = (data.get("publish_attributes") or {}).get(
            self.__class__.__name__, {}
        )
        return bool(attributes.get("active", True))


class FakeInstancePlugin:
    """Minimal Katana instance plugin base."""

    log = types.SimpleNamespace(error=lambda *_args, **_kwargs: None)


class FakeContextPlugin:
    """Minimal Pyblish context plugin base."""


class FakeAction:
    """Minimal Pyblish action base."""


class FakePublishValidationError(RuntimeError):
    """Minimal AYON validation error."""

    def __init__(self, message, *, title=None, description=None):
        super().__init__(message)
        self.title = title
        self.description = description


class FakeNode:
    """Minimal Katana node."""

    def __init__(self, name):
        self.name = name

    def getName(self):
        return self.name


class FakeInstance:
    """Minimal publish instance."""

    def __init__(self, data):
        self.data = data


class FakeContext(list):
    """List-like context storing failed instances."""

    def __init__(self, instances, errored_instances=None):
        super().__init__(instances)
        self.data = {}
        self.errored_instances = errored_instances or []


def _definition(
    node_name,
    name,
    path,
    extension="exr",
    channel="rgba",
    aov_identifier=None,
):
    if aov_identifier is None:
        aov_identifier = "" if channel.casefold() in {"rgba", "beauty"} else channel
    return types.SimpleNamespace(
        node_name=node_name,
        name=name,
        path=path,
        extension=extension,
        channel=channel,
        aov_identifier=aov_identifier,
    )


def _install_runtime(monkeypatch, nodes, definitions):
    pyblish_api = types.ModuleType("pyblish.api")
    pyblish_api.ValidatorOrder = 1.0
    pyblish_api.ContextPlugin = FakeContextPlugin
    pyblish_api.Action = FakeAction
    pyblish_module = types.ModuleType("pyblish")
    pyblish_module.api = pyblish_api
    monkeypatch.setitem(sys.modules, "pyblish", pyblish_module)
    monkeypatch.setitem(sys.modules, "pyblish.api", pyblish_api)

    pipeline_module = types.ModuleType("ayon_core.pipeline")
    pipeline_module.OptionalPyblishPluginMixin = FakeOptionalPyblishPluginMixin
    pipeline_module.PublishValidationError = FakePublishValidationError
    publish_module = types.ModuleType("ayon_core.pipeline.publish")
    publish_module.PublishValidationError = FakePublishValidationError
    ayon_core_module = types.ModuleType("ayon_core")
    ayon_core_module.pipeline = pipeline_module
    monkeypatch.setitem(sys.modules, "ayon_core", ayon_core_module)
    monkeypatch.setitem(sys.modules, "ayon_core.pipeline", pipeline_module)
    monkeypatch.setitem(sys.modules, "ayon_core.pipeline.publish", publish_module)

    compat_module = types.SimpleNamespace(get_node=lambda name: nodes.get(name))
    render_module = types.SimpleNamespace(
        get_output_definitions=lambda _node: definitions
    )
    plugin_module = types.SimpleNamespace(KatanaInstancePlugin=FakeInstancePlugin)

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
    actions_module = types.ModuleType("ayon_katana.plugins.publish.actions")
    actions_module.SelectInvalidOutputNodes = type("SelectInvalidOutputNodes", (), {})
    monkeypatch.setitem(sys.modules, "ayon_katana", ayon_katana_module)
    monkeypatch.setitem(sys.modules, "ayon_katana.api", api_module)
    monkeypatch.setitem(sys.modules, "ayon_katana.api.compat", compat_module)
    monkeypatch.setitem(sys.modules, "ayon_katana.api.plugin", plugin_module)
    monkeypatch.setitem(sys.modules, "ayon_katana.api.render", render_module)
    monkeypatch.setitem(sys.modules, "ayon_katana.plugins", plugins_module)
    monkeypatch.setitem(sys.modules, "ayon_katana.plugins.publish", publish_package)
    monkeypatch.setitem(
        sys.modules,
        "ayon_katana.plugins.publish.actions",
        actions_module,
    )


def _load_validator(monkeypatch, filename, definitions):
    nodes = {"instance": FakeNode("instance")}
    nodes.update(
        {
            definition.node_name: FakeNode(definition.node_name)
            for definition in definitions
        }
    )
    _install_runtime(monkeypatch, nodes, definitions)
    module_name = f"ayon_katana.plugins.publish.{filename[:-3]}"
    module_path = PUBLISH_ROOT / filename
    spec = importlib.util.spec_from_file_location(module_name, module_path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    monkeypatch.setitem(sys.modules, module_name, module)
    spec.loader.exec_module(module)
    return module, nodes


def _instance(**data):
    values = {
        "instance_node": "instance",
        "frameStartHandle": 1001,
        "frameEndHandle": 1002,
        "byFrameStep": 1,
    }
    values.update(data)
    return FakeInstance(values)


def test_valid_outputs_pass_all_strict_validators(monkeypatch):
    definitions = [
        _definition(
            "beautyOutput",
            "primary",
            "C:/renders/beauty.####.exr",
            channel="rgba",
        ),
        _definition(
            "depthOutput",
            "Z",
            "C:/renders/depth.####.exr",
            channel="Z",
        ),
    ]
    validators = [
        ("validate_render_output_names.py", "ValidateRenderOutputNames"),
        ("validate_render_output_paths.py", "ValidateRenderOutputPaths"),
        (
            "validate_render_output_extensions.py",
            "ValidateRenderOutputExtensions",
        ),
        ("validate_render_output_tokens.py", "ValidateRenderOutputTokens"),
    ]

    for filename, class_name in validators:
        module, _nodes = _load_validator(monkeypatch, filename, definitions)
        getattr(module, class_name)().process(_instance())


def test_output_name_validator_reports_empty_and_duplicate_names(monkeypatch):
    definitions = [
        _definition("emptyOutput", "", "C:/renders/empty.####.exr"),
        _definition("firstOutput", "Z", "C:/renders/z1.####.exr", channel="Z"),
        _definition("secondOutput", "Z", "C:/renders/z2.####.exr", channel="Z"),
    ]
    module, nodes = _load_validator(
        monkeypatch,
        "validate_render_output_names.py",
        definitions,
    )
    plugin = module.ValidateRenderOutputNames()

    with pytest.raises(FakePublishValidationError) as exc_info:
        plugin.process(_instance())

    message = str(exc_info.value)
    assert "emptyOutput: output name is empty" in message
    assert "firstOutput: output name 'Z' is duplicated" in message
    assert "multiple outputs resolve to AOV 'Z'" in message
    assert [node.getName() for node in plugin.get_invalid(_instance())] == [
        nodes["emptyOutput"].getName(),
        nodes["firstOutput"].getName(),
        nodes["secondOutput"].getName(),
    ]


def test_output_path_validator_reports_empty_and_colliding_paths(monkeypatch):
    definitions = [
        _definition("emptyOutput", "empty", ""),
        _definition("beautyOutput", "primary", "C:/renders/shared.####.exr"),
        _definition(
            "depthOutput",
            "Z",
            "C:/renders/shared.####.exr",
            channel="Z",
        ),
    ]
    module, _nodes = _load_validator(
        monkeypatch,
        "validate_render_output_paths.py",
        definitions,
    )

    with pytest.raises(FakePublishValidationError) as exc_info:
        module.ValidateRenderOutputPaths().process(_instance())

    message = str(exc_info.value)
    assert "emptyOutput: output path is empty" in message
    assert "path 'C:/renders/shared.####.exr' is shared" in message
    assert "primary, Z" in message


def test_output_extension_validator_reports_missing_and_mismatched_extensions(
    monkeypatch,
):
    definitions = [
        _definition("missingOutput", "primary", "C:/renders/beauty.####"),
        _definition(
            "mismatchOutput",
            "Z",
            "C:/renders/depth.####.png",
            extension="exr",
            channel="Z",
        ),
    ]
    module, _nodes = _load_validator(
        monkeypatch,
        "validate_render_output_extensions.py",
        definitions,
    )

    with pytest.raises(FakePublishValidationError) as exc_info:
        module.ValidateRenderOutputExtensions().process(_instance())

    message = str(exc_info.value)
    assert "has no file extension" in message
    assert "uses .png; native output requires .exr" in message


@pytest.mark.parametrize(
    ("path", "message"),
    [
        ("C:/renders/beauty.exr", "has no # frame token"),
        ("C:/renders/beauty.##.####.exr", "contains multiple # tokens"),
        ("C:/renders/beauty.$F4.exr", "uses unsupported token '$F4'"),
        ("C:/renders/beauty.%04d.exr", "uses unsupported token '%04d'"),
    ],
)
def test_output_token_validator_fails_loudly(monkeypatch, path, message):
    definitions = [_definition("beautyOutput", "primary", path)]
    module, _nodes = _load_validator(
        monkeypatch,
        "validate_render_output_tokens.py",
        definitions,
    )

    with pytest.raises(FakePublishValidationError) as exc_info:
        module.ValidateRenderOutputTokens().process(_instance())

    assert message in str(exc_info.value)


def test_output_token_validator_rejects_inconsistent_padding(monkeypatch):
    definitions = [
        _definition("beautyOutput", "primary", "C:/renders/beauty.####.exr"),
        _definition(
            "depthOutput",
            "Z",
            "C:/renders/depth.###.exr",
            channel="Z",
        ),
    ]
    module, _nodes = _load_validator(
        monkeypatch,
        "validate_render_output_tokens.py",
        definitions,
    )

    with pytest.raises(FakePublishValidationError) as exc_info:
        module.ValidateRenderOutputTokens().process(_instance())

    assert "all outputs must use consistent padding (3, 4)" in str(exc_info.value)


def test_output_selection_action_supports_instance_validators(monkeypatch):
    selections = []
    pyblish_api = types.ModuleType("pyblish.api")
    pyblish_api.ContextPlugin = FakeContextPlugin
    pyblish_api.Action = FakeAction
    pyblish_module = types.ModuleType("pyblish")
    pyblish_module.api = pyblish_api
    monkeypatch.setitem(sys.modules, "pyblish", pyblish_module)
    monkeypatch.setitem(sys.modules, "pyblish.api", pyblish_api)

    publish_module = types.ModuleType("ayon_core.pipeline.publish")
    publish_module.get_errored_instances_from_context = lambda context, plugin: (
        context.errored_instances
    )
    pipeline_module = types.ModuleType("ayon_core.pipeline")
    pipeline_module.publish = publish_module
    ayon_core_module = types.ModuleType("ayon_core")
    ayon_core_module.pipeline = pipeline_module
    monkeypatch.setitem(sys.modules, "ayon_core", ayon_core_module)
    monkeypatch.setitem(sys.modules, "ayon_core.pipeline", pipeline_module)
    monkeypatch.setitem(sys.modules, "ayon_core.pipeline.publish", publish_module)

    output_node = FakeNode("invalidOutput")
    compat_module = types.SimpleNamespace(
        get_node=lambda _name: None,
        set_selected_nodes=lambda nodes: selections.append(list(nodes)),
    )
    render_module = types.SimpleNamespace()
    ayon_katana_module = types.ModuleType("ayon_katana")
    ayon_katana_module.__path__ = []
    api_module = types.ModuleType("ayon_katana.api")
    api_module.__path__ = []
    api_module.compat = compat_module
    api_module.render = render_module
    monkeypatch.setitem(sys.modules, "ayon_katana", ayon_katana_module)
    monkeypatch.setitem(sys.modules, "ayon_katana.api", api_module)
    monkeypatch.setitem(sys.modules, "ayon_katana.api.compat", compat_module)
    monkeypatch.setitem(sys.modules, "ayon_katana.api.render", render_module)

    module_name = "ayon_katana.plugins.publish.actions"
    spec = importlib.util.spec_from_file_location(
        module_name,
        PUBLISH_ROOT / "actions.py",
    )
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    monkeypatch.setitem(sys.modules, module_name, module)
    spec.loader.exec_module(module)

    failed_instance = FakeInstance({"instance_node": "instance"})
    context = FakeContext([failed_instance], [failed_instance])

    class FailedOutputValidator:
        @classmethod
        def get_invalid(cls, instance):
            assert instance is failed_instance
            return [output_node]

    module.SelectInvalidOutputNodes().process(context, FailedOutputValidator)

    assert [[node.getName() for node in nodes] for nodes in selections] == [
        ["invalidOutput"]
    ]


def test_render_output_validators_expose_no_repair_actions():
    filenames = [
        "validate_render_output_extensions.py",
        "validate_render_output_names.py",
        "validate_render_output_paths.py",
        "validate_render_output_tokens.py",
        "validate_render_product_paths_unique.py",
    ]
    for filename in filenames:
        source = (PUBLISH_ROOT / filename).read_text(encoding="utf-8")
        tree = ast.parse(source)
        assert "RepairAction" not in source
        assert not any(
            isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
            and node.name == "repair"
            for node in ast.walk(tree)
        )


def test_server_settings_enable_strict_output_validators():
    settings_path = PROJECT_ROOT / "server" / "settings" / "main.py"
    source = settings_path.read_text(encoding="utf-8")
    tree = ast.parse(source)
    defaults_assignment = next(
        node
        for node in tree.body
        if isinstance(node, ast.Assign)
        and any(
            isinstance(target, ast.Name) and target.id == "DEFAULT_VALUES"
            for target in node.targets
        )
    )
    defaults = ast.literal_eval(defaults_assignment.value)
    plugin_names = [
        "ValidateRenderOutputNames",
        "ValidateRenderOutputPaths",
        "ValidateRenderOutputExtensions",
        "ValidateRenderOutputTokens",
        "ValidateRenderProductPathsUnique",
    ]
    for plugin_name in plugin_names:
        assert plugin_name in source
        assert defaults["publish"][plugin_name] == {
            "enabled": True,
            "optional": False,
            "active": True,
        }
