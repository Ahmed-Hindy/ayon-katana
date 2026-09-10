"""Focused contracts for selected-Group Katana nodegraph publishing."""

from __future__ import annotations

import ast
import importlib.util
import logging
import sys
import types
from pathlib import Path

import pytest

ROOT = Path(__file__).parents[1]


class FakeNode:
    """Small Katana Group/node stand-in with hierarchy and output state."""

    def __init__(
        self,
        name: str,
        node_type: str = "Group",
        *,
        output: bool = True,
        parent=None,
    ) -> None:
        self.name = name
        self.node_type = node_type
        self.output = output
        self.parent = parent
        self.children = []
        if parent is not None:
            parent.children.append(self)

    def getName(self) -> str:
        """Return this fake node's globally stable name."""
        return self.name

    def getType(self) -> str:
        """Return the Katana node type."""
        return self.node_type

    def getOutputPort(self, name: str):
        """Return the named output port when exposed."""
        return object() if self.output and name == "out" else None

    def getOutputPorts(self) -> list:
        """Return all exposed output ports."""
        return [object()] if self.output else []

    def getChildren(self) -> list:
        """Return direct child nodes."""
        return list(self.children)

    def getParent(self):
        """Return the direct parent node."""
        return self.parent


class FakeCreatedInstance(dict):
    """CreatedInstance-compatible mapping used by the creator test."""

    def __init__(self, data: dict) -> None:
        super().__init__(data)
        self.transient_data = {"node": FakeNode("nodegraphMainInstance")}

    def data_to_store(self) -> dict:
        """Return the persistent instance payload."""
        return dict(self)


class FakeKatanaCreator:
    """Minimal creator that exposes only the inherited create behavior."""

    def create(self, _product_name, instance_data, _pre_create_data):
        """Return a fake created instance from prepared data."""
        instance = FakeCreatedInstance(instance_data)
        instance["instance_node"] = instance.transient_data["node"].getName()
        return instance


class FakeCreatorError(RuntimeError):
    """Creator error counterpart for isolated tests."""


class FakeOptionalPyblishPluginMixin:
    """Minimal optional-plugin activation mixin."""

    def is_active(self, data: dict) -> bool:
        """Return the stored active state, defaulting to enabled."""
        attributes = (data.get("publish_attributes") or {}).get(
            self.__class__.__name__, {}
        )
        return bool(attributes.get("active", True))


class FakePublishValidationError(RuntimeError):
    """Validation error counterpart preserving the optional title."""

    def __init__(self, message: str, *, title: str | None = None) -> None:
        super().__init__(message)
        self.title = title


class FakePublishError(RuntimeError):
    """Generic publishing error counterpart."""


class FakeInstancePlugin:
    """Minimal instance plug-in base."""

    log = logging.getLogger("test_nodegraph_publish")


class FakeExtractor:
    """Minimal extractor base with the logger used by the production plugin."""

    log = logging.getLogger("test_nodegraph_publish")


def _load_module(monkeypatch, module_name: str, path: Path):
    """Load one source module under a controlled package name."""
    module_spec = importlib.util.spec_from_file_location(module_name, path)
    assert module_spec is not None
    assert module_spec.loader is not None
    module = importlib.util.module_from_spec(module_spec)
    monkeypatch.setitem(sys.modules, module_name, module)
    module_spec.loader.exec_module(module)
    return module


def _install_ayon_katana_api(monkeypatch, api_modules: dict[str, object]) -> None:
    """Install the compact module tree required by the tested plug-ins."""
    package_module = types.ModuleType("ayon_katana")
    package_module.__path__ = []
    api_module = types.ModuleType("ayon_katana.api")
    api_module.__path__ = []
    plugins_module = types.ModuleType("ayon_katana.plugins")
    plugins_module.__path__ = []
    create_module = types.ModuleType("ayon_katana.plugins.create")
    create_module.__path__ = []
    publish_module = types.ModuleType("ayon_katana.plugins.publish")
    publish_module.__path__ = []
    monkeypatch.setitem(sys.modules, "ayon_katana", package_module)
    monkeypatch.setitem(sys.modules, "ayon_katana.api", api_module)
    monkeypatch.setitem(sys.modules, "ayon_katana.plugins", plugins_module)
    monkeypatch.setitem(sys.modules, "ayon_katana.plugins.create", create_module)
    monkeypatch.setitem(sys.modules, "ayon_katana.plugins.publish", publish_module)
    for name, module in api_modules.items():
        setattr(api_module, name, module)
        monkeypatch.setitem(sys.modules, f"ayon_katana.api.{name}", module)


def _install_publish_runtime(monkeypatch, api_modules: dict[str, object]) -> None:
    """Install small AYON Core and Pyblish surfaces for publish plug-ins."""
    pyblish_api = types.ModuleType("pyblish.api")
    pyblish_api.CollectorOrder = 1.0
    pyblish_api.ValidatorOrder = 2.0
    pyblish_api.ExtractorOrder = 3.0
    pyblish_module = types.ModuleType("pyblish")
    pyblish_module.api = pyblish_api
    monkeypatch.setitem(sys.modules, "pyblish", pyblish_module)
    monkeypatch.setitem(sys.modules, "pyblish.api", pyblish_api)

    ayon_core = types.ModuleType("ayon_core")
    pipeline_module = types.ModuleType("ayon_core.pipeline")
    pipeline_module.OptionalPyblishPluginMixin = FakeOptionalPyblishPluginMixin
    pipeline_module.publish = types.SimpleNamespace(Extractor=FakeExtractor)
    publish_module = types.ModuleType("ayon_core.pipeline.publish")
    publish_module.PublishError = FakePublishError
    publish_module.PublishValidationError = FakePublishValidationError
    ayon_core.pipeline = pipeline_module
    monkeypatch.setitem(sys.modules, "ayon_core", ayon_core)
    monkeypatch.setitem(sys.modules, "ayon_core.pipeline", pipeline_module)
    monkeypatch.setitem(sys.modules, "ayon_core.pipeline.publish", publish_module)
    _install_ayon_katana_api(monkeypatch, api_modules)


def _load_creator(monkeypatch, selected_nodes, outer_container=None):
    """Load the nodegraph creator with selection and container fakes."""
    ayon_core = types.ModuleType("ayon_core")
    pipeline_module = types.ModuleType("ayon_core.pipeline")
    pipeline_module.CreatorError = FakeCreatorError
    ayon_core.pipeline = pipeline_module
    monkeypatch.setitem(sys.modules, "ayon_core", ayon_core)
    monkeypatch.setitem(sys.modules, "ayon_core.pipeline", pipeline_module)

    compat = types.SimpleNamespace(get_selected_nodes=lambda: list(selected_nodes))
    containers = types.SimpleNamespace(
        parse_container=lambda node: {"node": node} if node is outer_container else None
    )
    imprinted = []
    instances = types.SimpleNamespace(
        imprint=lambda node, data: imprinted.append((node, dict(data)))
    )
    plugin = types.SimpleNamespace(KatanaCreator=FakeKatanaCreator)
    _install_ayon_katana_api(
        monkeypatch,
        {
            "compat": compat,
            "containers": containers,
            "instances": instances,
            "plugin": plugin,
        },
    )
    module = _load_module(
        monkeypatch,
        "ayon_katana.plugins.create.create_nodegraph",
        ROOT / "client" / "ayon_katana" / "plugins" / "create" / "create_nodegraph.py",
    )
    return module, imprinted


def test_creator_requires_one_selected_non_container_group(monkeypatch) -> None:
    """Creation rejects no selection, wrong types, and outer AYON containers."""
    module, _imprinted = _load_creator(monkeypatch, [])
    creator = object.__new__(module.CreateNodegraph)
    with pytest.raises(FakeCreatorError, match="exactly one"):
        creator.create("nodegraphMain", {}, {})

    wrong_type = FakeNode("UsdIn", "UsdIn")
    module, _imprinted = _load_creator(monkeypatch, [wrong_type])
    creator = object.__new__(module.CreateNodegraph)
    with pytest.raises(FakeCreatorError, match="Group"):
        creator.create("nodegraphMain", {}, {})

    outer_container = FakeNode("assetMain_CON")
    module, _imprinted = _load_creator(
        monkeypatch,
        [outer_container],
        outer_container=outer_container,
    )
    creator = object.__new__(module.CreateNodegraph)
    with pytest.raises(FakeCreatorError, match="outer AYON container"):
        creator.create("nodegraphMain", {}, {})


def test_creator_persists_selected_group_name_and_separate_instance(
    monkeypatch,
) -> None:
    """The nodegraph instance persists its source name and creator node name."""
    source_group = FakeNode("PublishedGroup")
    module, _imprinted = _load_creator(monkeypatch, [source_group])
    creator = object.__new__(module.CreateNodegraph)

    created = creator.create("nodegraphMain", {"families": []}, {})

    assert created["nodegraph_node"] == "PublishedGroup"
    assert created["instance_node"] == "nodegraphMainInstance"
    assert "nodegraph" in created["families"]


def test_render_setup_creator_reuses_nodegraph_contract(monkeypatch) -> None:
    """Render setups stay semantic products over the proven graph exporter."""
    module, _imprinted = _load_creator(monkeypatch, [])

    assert issubclass(module.CreateRenderSetup, module.CreateNodegraph)
    assert module.CreateRenderSetup.product_base_type == "rendersetup"
    assert module.CreateRenderSetup.product_type == "rendersetup"
    assert module.CreateRenderSetup.label == "Render Setup"
    assert module.CreateRenderSetup.identifier == "io.ayon.creators.katana.render_setup"


def _load_validator(monkeypatch, node_map, outer_container=None):
    """Load the nodegraph validator with graph and container fakes."""

    def is_descendant(node, parent_node) -> bool:
        current_node = node.getParent()
        while current_node is not None:
            if current_node is parent_node:
                return True
            current_node = current_node.getParent()
        return False

    _install_publish_runtime(
        monkeypatch,
        {
            "compat": types.SimpleNamespace(
                get_node=node_map.get,
                get_output_ports=lambda node: node.getOutputPorts(),
                is_descendant=is_descendant,
            ),
            "containers": types.SimpleNamespace(
                parse_container=lambda node: (
                    {"node": node} if node is outer_container else None
                )
            ),
            "plugin": types.SimpleNamespace(KatanaInstancePlugin=FakeInstancePlugin),
        },
    )
    return _load_module(
        monkeypatch,
        "ayon_katana.plugins.publish.validate_nodegraph",
        ROOT
        / "client"
        / "ayon_katana"
        / "plugins"
        / "publish"
        / "validate_nodegraph.py",
    )


@pytest.mark.parametrize(
    ("source", "instance_name", "match"),
    [
        (None, None, "no longer exists"),
        (FakeNode("Wrong", "UsdIn"), None, "remain a Group"),
        (FakeNode("NoOutput", output=False), None, "at least one output port"),
    ],
)
def test_validator_rejects_missing_wrong_and_outputless_sources(
    monkeypatch,
    source,
    instance_name,
    match,
) -> None:
    """Deleted, non-Group, and outputless nodegraph sources cannot publish."""
    node_map = {} if source is None else {source.getName(): source}
    validator = _load_validator(monkeypatch, node_map)
    instance = types.SimpleNamespace(
        data={"nodegraph_node": "Deleted" if source is None else source.getName()}
    )
    if instance_name:
        instance.data["instance_node"] = instance_name

    with pytest.raises(FakePublishValidationError, match=match):
        validator.ValidateNodegraph().process(instance)


def test_validator_does_not_coerce_node_identifiers(monkeypatch) -> None:
    """Malformed persisted identifiers cannot impersonate valid node names."""
    source = FakeNode("PublishedGroup")
    validator = _load_validator(monkeypatch, {source.getName(): source})

    class StringLikeIdentifier:
        def __str__(self) -> str:
            return source.getName()

    instance = types.SimpleNamespace(data={"nodegraph_node": StringLikeIdentifier()})
    with pytest.raises(FakePublishValidationError, match="no longer exists"):
        validator.ValidateNodegraph().process(instance)


def test_validator_rejects_outer_container_and_recursive_instance(monkeypatch) -> None:
    """A source cannot be a container or contain its own publish instance."""
    outer_container = FakeNode("assetMain_CON")
    validator = _load_validator(
        monkeypatch,
        {outer_container.getName(): outer_container},
        outer_container=outer_container,
    )
    with pytest.raises(FakePublishValidationError, match="outer AYON container"):
        validator.ValidateNodegraph().process(
            types.SimpleNamespace(data={"nodegraph_node": outer_container.getName()})
        )

    source_group = FakeNode("PublishedGroup")
    instance_node = FakeNode("nodegraphMain", parent=source_group)
    validator = _load_validator(
        monkeypatch,
        {source_group.getName(): source_group, instance_node.getName(): instance_node},
    )
    with pytest.raises(FakePublishValidationError, match="contains its publishing"):
        validator.ValidateNodegraph().process(
            types.SimpleNamespace(
                data={
                    "nodegraph_node": source_group.getName(),
                    "instance_node": instance_node.getName(),
                }
            )
        )


def test_dependency_collector_records_only_containers_inside_source(
    monkeypatch,
) -> None:
    """Discoverable nested AYON container representations become dependencies."""

    class LeafNode:
        def __init__(self, name: str, parent=None) -> None:
            self.name = name
            self.parent = parent

        def getName(self) -> str:
            return self.name

        def getParent(self):
            return self.parent

    def is_descendant(node, parent_node) -> bool:
        current_node = node.getParent()
        while current_node is not None:
            if current_node is parent_node:
                return True
            current_node = current_node.getParent()
        return False

    source_group = FakeNode("PublishedGroup")
    inside_container = LeafNode("inside_CON", parent=source_group)
    outside_container = LeafNode("outside_CON")
    _install_publish_runtime(
        monkeypatch,
        {
            "compat": types.SimpleNamespace(
                get_node={source_group.getName(): source_group}.get,
                is_descendant=is_descendant,
            ),
            "containers": types.SimpleNamespace(
                ls=lambda: iter(
                    [
                        {"node": inside_container, "representation": "inside-rep"},
                        {"node": outside_container, "representation": "outside-rep"},
                        {"node": inside_container, "representation": "inside-rep"},
                    ]
                )
            ),
            "plugin": types.SimpleNamespace(KatanaInstancePlugin=FakeInstancePlugin),
        },
    )
    collector = _load_module(
        monkeypatch,
        "ayon_katana.plugins.publish.collect_nodegraph",
        ROOT
        / "client"
        / "ayon_katana"
        / "plugins"
        / "publish"
        / "collect_nodegraph.py",
    )
    instance = types.SimpleNamespace(data={"nodegraph_node": source_group.getName()})

    collector.CollectNodegraphDependencies().process(instance)

    assert instance.data["inputRepresentations"] == ["inside-rep"]


def test_extractor_uses_selected_group_export_and_one_katana_representation(
    monkeypatch,
    tmp_path: Path,
) -> None:
    """Extractor calls KatanaFile.Export only for the selected source Group."""
    source_group = FakeNode("PublishedGroup")
    export_calls = []

    def export(destination_path: str, nodes: list):
        export_calls.append((destination_path, nodes))
        Path(destination_path).write_text("selected group only", encoding="utf-8")
        return destination_path

    katana_module = types.ModuleType("Katana")
    katana_module.KatanaFile = types.SimpleNamespace(Export=export)
    monkeypatch.setitem(sys.modules, "Katana", katana_module)
    _install_publish_runtime(
        monkeypatch,
        {
            "compat": types.SimpleNamespace(
                get_node={source_group.getName(): source_group}.get
            ),
            "plugin": types.SimpleNamespace(KatanaExtractorPlugin=FakeExtractor),
        },
    )
    extractor_module = _load_module(
        monkeypatch,
        "ayon_katana.plugins.publish.extract_nodegraph",
        ROOT
        / "client"
        / "ayon_katana"
        / "plugins"
        / "publish"
        / "extract_nodegraph.py",
    )
    instance = types.SimpleNamespace(
        data={"nodegraph_node": source_group.getName(), "productName": "nodegraphMain"}
    )
    extractor = extractor_module.ExtractNodegraph()
    extractor.staging_dir = lambda _instance: str(tmp_path)

    extractor.process(instance)

    assert export_calls == [
        ((tmp_path / "nodegraphMain.katana").as_posix(), [source_group])
    ]
    assert instance.data["representations"] == [
        {
            "name": "katana",
            "ext": "katana",
            "files": "nodegraphMain.katana",
            "stagingDir": str(tmp_path),
        }
    ]
    assert instance.data["setMembers"] == [
        (tmp_path / "nodegraphMain.katana").as_posix()
    ]


def test_server_settings_register_nodegraph_creator_and_publish_plugins() -> None:
    """Nodegraph plug-ins are enabled by the server's default settings."""
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

    assert defaults["create"]["CreateNodegraph"] == {"enabled": True}
    assert defaults["create"]["CreateRenderSetup"] == {"enabled": True}
    assert defaults["publish"]["CollectNodegraph"] == {"enabled": True}
    assert defaults["publish"]["CollectNodegraphDependencies"] == {"enabled": True}
    assert defaults["publish"]["ExtractNodegraph"] == {"enabled": True}
    assert defaults["publish"]["ValidateNodegraph"] == {
        "enabled": True,
        "optional": False,
        "active": True,
    }
