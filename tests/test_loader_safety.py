"""Tests for Katana loader options and managed graph replacement safety."""

from __future__ import annotations

import ast
import importlib.util
import sys
import types
from pathlib import Path

import pytest


class FakeParameter:
    """Minimal Katana parameter storing a single value."""

    def __init__(self, value="") -> None:
        self.value = value

    def getValue(self, _time):
        """Return the stored value."""
        return self.value

    def setValue(self, value, _time) -> None:
        """Store a value."""
        self.value = value


class FakePort:
    """Minimal bidirectional Katana port connection model."""

    def __init__(self, node, name: str) -> None:
        self.node = node
        self.name = name
        self.connections = []

    def connect(self, other_port) -> None:
        """Create a connection to another port."""
        if other_port not in self.connections:
            self.connections.append(other_port)
            other_port.connections.append(self)

    def disconnect(self, other_port) -> None:
        """Remove a connection to another port."""
        if other_port in self.connections:
            self.connections.remove(other_port)
            other_port.connections.remove(self)

    def getConnectedPorts(self):
        """Return ports connected to this one."""
        return list(self.connections)

    def getNode(self):
        """Return the owning node."""
        return self.node


class FakeNode:
    """Small Group/source node implementation used by loader tests."""

    def __init__(self, node_type: str, parent_node=None) -> None:
        self.node_type = node_type
        self.parent_node = parent_node
        self.children = []
        self.name = node_type
        self.deleted = False
        self.ports = {}
        self.parameters = {}
        self.container_data = None
        self.roles = {}
        if node_type == "UsdIn":
            self.parameters["location"] = FakeParameter("/root/default_usd")
            self.addOutputPort("out")
        elif node_type == "UsdSubLayerAdd":
            self.parameters["asset"] = FakeParameter()
            self.addOutputPort("out")
        elif node_type == "Alembic_In":
            self.parameters["name"] = FakeParameter("/root/default_alembic")
            self.addOutputPort("out")
        elif node_type == "ImageRead":
            self.parameters["file"] = FakeParameter()
            self.parameters["image.colorspace"] = FakeParameter()
            self.addOutputPort("out")
        if parent_node is not None:
            parent_node.children.append(self)

    def _get_port(self, kind: str, name: str, create: bool = False):
        key = (kind, name)
        if create and key not in self.ports:
            self.ports[key] = FakePort(self, name)
        return self.ports.get(key)

    def addInputPort(self, name: str):
        """Add an input port."""
        return self._get_port("input", name, create=True)

    def addOutputPort(self, name: str):
        """Add an output port."""
        return self._get_port("output", name, create=True)

    def getInputPort(self, name: str):
        """Return an input port, if present."""
        return self._get_port("input", name)

    def getOutputPort(self, name: str):
        """Return an output port, if present."""
        return self._get_port("output", name)

    def getOutputPorts(self):
        """Return all output ports."""
        return [port for (kind, _name), port in self.ports.items() if kind == "output"]

    def getSendPort(self, name: str):
        """Return a Group send port."""
        return self._get_port("send", name, create=True)

    def getReturnPort(self, name: str):
        """Return a Group return port."""
        return self._get_port("return", name, create=True)

    def getParameter(self, name: str):
        """Return a native parameter, creating generic ones as needed."""
        if name not in self.parameters:
            self.parameters[name] = FakeParameter()
        return self.parameters[name]

    def getChildren(self):
        """Return direct children."""
        return list(self.children)

    def getChild(self, name: str):
        """Return a direct child by name."""
        return next((child for child in self.children if child.name == name), None)

    def getName(self) -> str:
        """Return the node name."""
        return self.name

    def setName(self, name: str) -> None:
        """Set the node name."""
        self.name = name

    def delete(self) -> None:
        """Delete the node, its child nodes, and its port connections."""
        for child in list(self.children):
            child.delete()
        for port in self.ports.values():
            for connected_port in list(port.connections):
                port.disconnect(connected_port)
        if self.parent_node is not None:
            self.parent_node.children.remove(self)
        self.deleted = True


class FakeGraph:
    """Katana NodegraphAPI replacement for isolated unit tests."""

    def __init__(self) -> None:
        self.root = FakeNode("Root")

    def CreateNode(self, node_type: str, parent_node):
        """Create a node below a parent."""
        return FakeNode(node_type, parent_node)

    def GetRootNode(self):
        """Return the test graph root."""
        return self.root

    def GetAllNodesByType(self, node_type: str):
        """Return every matching node in the graph."""
        matches = []
        pending = list(self.root.getChildren())
        while pending:
            node = pending.pop(0)
            if node.node_type == node_type:
                matches.append(node)
            pending.extend(node.getChildren())
        return matches


class FakeTextDef:
    """Simplified AYON Core text attribute definition."""

    def __init__(self, key: str, **kwargs) -> None:
        self.key = key
        for name, value in kwargs.items():
            setattr(self, name, value)


class FakeKatanaLoader(list):
    """Loader base providing representation paths for the test context."""

    use_ayon_entity_uri = False

    @classmethod
    def filepath_from_context(cls, context):
        """Return the test representation path."""
        if cls.use_ayon_entity_uri:
            return context["test_entity_uri"]
        return str(context["test_filepath"])


def _load_module(monkeypatch, module_name: str, module_path: Path):
    """Load a module from the repository under a controlled module name."""
    module_spec = importlib.util.spec_from_file_location(module_name, module_path)
    assert module_spec is not None
    assert module_spec.loader is not None
    module = importlib.util.module_from_spec(module_spec)
    monkeypatch.setitem(sys.modules, module_name, module)
    module_spec.loader.exec_module(module)
    return module


def _load_loader_modules(monkeypatch, import_graph):
    """Load loader modules with a small fake Katana and AYON Core runtime."""
    repository_root = Path(__file__).parents[1]
    graph = FakeGraph()

    katana_module = types.ModuleType("Katana")
    katana_module.NodegraphAPI = graph
    monkeypatch.setitem(sys.modules, "Katana", katana_module)

    ayon_core_module = types.ModuleType("ayon_core")
    ayon_core_module.__path__ = []
    pipeline_module = types.ModuleType("ayon_core.pipeline")
    pipeline_module.AYON_CONTAINER_ID = "ayon-container-id"
    lib_module = types.ModuleType("ayon_core.lib")
    lib_module.TextDef = FakeTextDef
    monkeypatch.setitem(sys.modules, "ayon_core", ayon_core_module)
    monkeypatch.setitem(sys.modules, "ayon_core.pipeline", pipeline_module)
    monkeypatch.setitem(sys.modules, "ayon_core.lib", lib_module)

    package_module = types.ModuleType("ayon_katana")
    package_module.__path__ = []
    api_module = types.ModuleType("ayon_katana.api")
    api_module.__path__ = []
    plugins_module = types.ModuleType("ayon_katana.plugins")
    plugins_module.__path__ = []
    load_module = types.ModuleType("ayon_katana.plugins.load")
    load_module.__path__ = []
    monkeypatch.setitem(sys.modules, "ayon_katana", package_module)
    monkeypatch.setitem(sys.modules, "ayon_katana.api", api_module)
    monkeypatch.setitem(sys.modules, "ayon_katana.plugins", plugins_module)
    monkeypatch.setitem(sys.modules, "ayon_katana.plugins.load", load_module)

    container_lib_module = types.ModuleType("ayon_katana.api.lib")
    container_lib_module.sanitize_node_name = lambda value, _fallback: value
    container_lib_module.write_json_parameter = lambda node, _path, data: setattr(
        node, "container_data", dict(data)
    )
    container_lib_module.read_json_parameter = lambda node, _path: (
        dict(node.container_data) if node.container_data is not None else None
    )
    container_lib_module.set_string_parameter = lambda node, path, value: (
        node.roles.__setitem__(path, value)
    )
    container_lib_module.get_string_parameter = lambda node, path: node.roles.get(path)

    monkeypatch.setitem(sys.modules, "ayon_katana.api.lib", container_lib_module)

    containers = _load_module(
        monkeypatch,
        "ayon_katana.api.containers",
        repository_root / "client" / "ayon_katana" / "api" / "containers.py",
    )
    api_module.containers = containers

    plugin_module = types.ModuleType("ayon_katana.api.plugin")
    plugin_module.KatanaLoader = FakeKatanaLoader
    compat_module = types.ModuleType("ayon_katana.api.compat")
    compat_module.get_output_ports = lambda node: list(node.getOutputPorts())
    compat_module.import_katana_file = lambda filepath, parent_node, float_nodes: (
        import_graph(
            filepath,
            parent_node,
            float_nodes,
        )
    )
    monkeypatch.setitem(sys.modules, "ayon_katana.api.plugin", plugin_module)
    monkeypatch.setitem(sys.modules, "ayon_katana.api.compat", compat_module)
    api_module.plugin = plugin_module
    api_module.compat = compat_module

    colorspace_api_module = types.ModuleType("ayon_katana.api.colorspace")
    colorspace_api_module.get_imageio_file_rule_colorspace = (
        lambda _filepath, _context: ""
    )
    monkeypatch.setitem(
        sys.modules,
        "ayon_katana.api.colorspace",
        colorspace_api_module,
    )
    api_module.colorspace = colorspace_api_module

    usd_api_module = types.ModuleType("ayon_katana.api.usd")
    usd_api_module.USD_PRODUCT_BASE_TYPES = {
        "assembly",
        "camera",
        "layout",
        "look",
        "usd",
        "usdCamera",
    }
    usd_api_module.clear_resolver_cache = lambda: None
    monkeypatch.setitem(sys.modules, "ayon_katana.api.usd", usd_api_module)
    api_module.usd = usd_api_module

    usd = _load_module(
        monkeypatch,
        "ayon_katana.plugins.load.load_usd",
        repository_root / "client" / "ayon_katana" / "plugins" / "load" / "load_usd.py",
    )
    clear_usd_cache = _load_module(
        monkeypatch,
        "ayon_katana.plugins.load.clear_usd_resolver_cache",
        repository_root
        / "client"
        / "ayon_katana"
        / "plugins"
        / "load"
        / "clear_usd_resolver_cache.py",
    )
    alembic = _load_module(
        monkeypatch,
        "ayon_katana.plugins.load.load_alembic",
        repository_root
        / "client"
        / "ayon_katana"
        / "plugins"
        / "load"
        / "load_alembic.py",
    )
    katana = _load_module(
        monkeypatch,
        "ayon_katana.plugins.load.load_katana",
        repository_root
        / "client"
        / "ayon_katana"
        / "plugins"
        / "load"
        / "load_katana.py",
    )
    image = _load_module(
        monkeypatch,
        "ayon_katana.plugins.load.load_image",
        repository_root
        / "client"
        / "ayon_katana"
        / "plugins"
        / "load"
        / "load_image.py",
    )
    return types.SimpleNamespace(
        graph=graph,
        containers=containers,
        usd=usd,
        clear_usd_cache=clear_usd_cache,
        alembic=alembic,
        katana=katana,
        image=image,
    )


def _context(filepath: Path, representation_id: str) -> dict:
    """Return a minimal AYON loader context."""
    return {
        "project": {"name": "LoaderSafety"},
        "folder": {"name": "asset"},
        "product": {"name": "assetMain"},
        "representation": {"id": representation_id},
        "test_filepath": filepath,
    }


@pytest.mark.parametrize(
    ("loader_attribute", "loader_name", "native_parameter", "native_default"),
    [
        ("usd", "UsdLoader", "location", "/root/default_usd"),
        ("alembic", "AbcLoader", "name", "/root/default_alembic"),
    ],
)
def test_scenegraph_location_option_applies_without_overriding_defaults(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    loader_attribute: str,
    loader_name: str,
    native_parameter: str,
    native_default: str,
) -> None:
    """Loaders expose location options and preserve native defaults when empty."""
    environment = _load_loader_modules(
        monkeypatch,
        import_graph=lambda *_args: [],
    )
    loader_class = getattr(getattr(environment, loader_attribute), loader_name)
    option = loader_class.get_options([])[0]
    assert option.key == "location"
    assert option.label == "Scenegraph location"
    assert option.default == ""
    assert "/root/world/geo" in option.tooltip

    filepath = tmp_path / "asset.usd"
    loader = loader_class()
    loaded_with_location = loader.load(
        _context(filepath, "representation-with-location"),
        options={"location": "/root/world/geo"},
    )
    source_with_location = environment.containers.find_managed_node(
        loaded_with_location,
        environment.containers.SOURCE_ROLE,
    )
    assert source_with_location is not None
    assert (
        source_with_location.getParameter(native_parameter).getValue(0.0)
        == "/root/world/geo"
    )

    loaded_with_default = loader.load(
        _context(filepath, "representation-with-default"),
        options={"location": ""},
    )
    source_with_default = environment.containers.find_managed_node(
        loaded_with_default,
        environment.containers.SOURCE_ROLE,
    )
    assert source_with_default is not None
    assert (
        source_with_default.getParameter(native_parameter).getValue(0.0)
        == native_default
    )


@pytest.mark.parametrize(
    ("loader_attribute", "loader_name", "source_node_type"),
    [
        ("usd", "UsdLoader", "UsdIn"),
        ("usd", "UsdSublayerLoader", "UsdSubLayerAdd"),
        ("alembic", "AbcLoader", "Alembic_In"),
        ("image", "ImageLoader", "ImageRead"),
    ],
)
def test_native_loader_failure_removes_incomplete_container(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    loader_attribute: str,
    loader_name: str,
    source_node_type: str,
) -> None:
    """Failed source-node setup must not leave a malformed AYON container."""
    environment = _load_loader_modules(
        monkeypatch,
        import_graph=lambda *_args: [],
    )
    original_create_node = environment.graph.CreateNode

    def create_node(node_type, parent_node):
        if node_type == source_node_type:
            raise ValueError("source creation failed")
        return original_create_node(node_type, parent_node)

    monkeypatch.setattr(environment.graph, "CreateNode", create_node)
    loader = getattr(getattr(environment, loader_attribute), loader_name)()

    with pytest.raises(ValueError, match="source creation failed"):
        loader.load(_context(tmp_path / "asset.usd", "representation-v001"))

    assert environment.graph.root.getChildren() == []


@pytest.mark.parametrize(
    ("loader_attribute", "loader_name"),
    [
        ("usd", "UsdLoader"),
        ("usd", "UsdSublayerLoader"),
        ("alembic", "AbcLoader"),
        ("image", "ImageLoader"),
    ],
)
def test_container_metadata_failure_leaves_no_loader_container(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    loader_attribute: str,
    loader_name: str,
) -> None:
    """A container metadata failure must delete the outer Group it created."""
    environment = _load_loader_modules(
        monkeypatch,
        import_graph=lambda *_args: [],
    )
    monkeypatch.setattr(
        environment.containers.lib,
        "write_json_parameter",
        lambda *_args: (_ for _ in ()).throw(RuntimeError("metadata failure")),
    )
    loader = getattr(getattr(environment, loader_attribute), loader_name)()

    with pytest.raises(RuntimeError, match="metadata failure"):
        loader.load(_context(tmp_path / "asset.usd", "representation-v001"))

    assert environment.graph.root.getChildren() == []


@pytest.mark.parametrize(
    ("loader_attribute", "loader_name", "extension"),
    [
        ("usd", "UsdLoader", "usd"),
        ("usd", "UsdSublayerLoader", "usd"),
        ("alembic", "AbcLoader", "abc"),
    ],
)
def test_loader_names_round_trip_without_compatibility_remapping(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    loader_attribute: str,
    loader_name: str,
    extension: str,
) -> None:
    """Containers persist the exact public loader class name."""
    environment = _load_loader_modules(
        monkeypatch,
        import_graph=lambda *_args: [],
    )
    loader = getattr(getattr(environment, loader_attribute), loader_name)()
    container_node = loader.load(
        _context(
            tmp_path / f"asset_v001.{extension}",
            "representation-v001",
        )
    )
    parsed_container = environment.containers.parse_container(container_node)
    assert parsed_container is not None
    assert parsed_container["loader"] == loader_name

    loader.update(
        parsed_container,
        _context(
            tmp_path / f"asset_v002.{extension}",
            "representation-v002",
        ),
    )

    assert container_node.container_data["loader"] == loader_name
    updated_container = environment.containers.parse_container(container_node)
    assert updated_container is not None
    assert updated_container["loader"] == loader_name


@pytest.mark.parametrize(
    ("loader_attribute", "loader_name", "parameter_name"),
    [
        ("usd", "UsdLoader", "fileName"),
        ("usd", "UsdSublayerLoader", "asset"),
        ("alembic", "AbcLoader", "abcAsset"),
        ("image", "ImageLoader", "file"),
    ],
)
def test_native_loader_update_rolls_back_path_and_metadata(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    loader_attribute: str,
    loader_name: str,
    parameter_name: str,
) -> None:
    """Metadata failure cannot leave the source node on a different version."""
    environment = _load_loader_modules(
        monkeypatch,
        import_graph=lambda *_args: [],
    )
    loader = getattr(getattr(environment, loader_attribute), loader_name)()
    initial_context = _context(tmp_path / "asset_v001.usd", "representation-v001")
    container_node = loader.load(initial_context)
    source_node = environment.containers.find_managed_node(
        container_node,
        environment.containers.SOURCE_ROLE,
    )
    assert source_node is not None
    original_path = source_node.getParameter(parameter_name).getValue(0.0)
    original_metadata = environment.containers.parse_container(container_node)
    assert original_metadata is not None
    original_writer = environment.containers.lib.write_json_parameter
    failed_once = False

    def fail_metadata_once(node, parameter_path, data):
        nonlocal failed_once
        if node is container_node and not failed_once:
            failed_once = True
            raise ValueError("metadata write failed")
        original_writer(node, parameter_path, data)

    monkeypatch.setattr(
        environment.containers.lib,
        "write_json_parameter",
        fail_metadata_once,
    )
    update_context = _context(tmp_path / "asset_v002.usd", "representation-v002")

    with pytest.raises(ValueError, match="metadata write failed"):
        loader.update(
            environment.containers.parse_container(container_node),
            update_context,
        )

    assert source_node.getParameter(parameter_name).getValue(0.0) == original_path
    restored_metadata = environment.containers.parse_container(container_node)
    assert restored_metadata is not None
    assert restored_metadata["representation"] == original_metadata["representation"]


@pytest.mark.parametrize(
    ("filepath", "frame", "expected"),
    [
        ("C:/renders/beauty.1001.exr", 1001, "C:/renders/beauty.####.exr"),
        ("C:/renders/beauty.%04d.exr", 1001, "C:/renders/beauty.####.exr"),
        ("C:/renders/beauty.$F4.exr", 1001, "C:/renders/beauty.####.exr"),
        ("C:/renders/beauty.1002.exr", 1001, "C:/renders/beauty.1002.exr"),
        ("C:/stills/beauty.exr", None, "C:/stills/beauty.exr"),
    ],
)
def test_image_sequence_paths_use_katana_hash_tokens(
    monkeypatch: pytest.MonkeyPatch,
    filepath: str,
    frame: int | None,
    expected: str,
) -> None:
    """Published sequence paths normalize without rewriting unrelated digits."""
    environment = _load_loader_modules(monkeypatch, import_graph=lambda *_args: [])
    representation = {"context": {"frame": frame}}

    result = environment.image.normalize_image_sequence_path(
        filepath,
        representation,
    )

    assert result == expected


def test_image_loader_applies_sequence_and_colorspace_metadata(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """ImageRead receives a hash sequence and published OCIO colorspace."""
    environment = _load_loader_modules(monkeypatch, import_graph=lambda *_args: [])
    context = _context(
        tmp_path / "plateMain.1001.exr",
        "image-representation-v001",
    )
    context["representation"].update(
        {
            "context": {"frame": 1001},
            "data": {"colorspaceData": {"colorspace": "ACEScg"}},
        }
    )

    container_node = environment.image.ImageLoader().load(context)
    source_node = environment.containers.find_managed_node(
        container_node,
        environment.containers.SOURCE_ROLE,
    )

    assert source_node is not None
    assert source_node.getParameter("file").getValue(0.0).endswith("plateMain.####.exr")
    assert source_node.getParameter("image.colorspace").getValue(0.0) == "ACEScg"
    managed_group = environment.containers.get_managed_group(container_node)
    assert managed_group is not None
    assert source_node.getOutputPort("out").getConnectedPorts() == [
        managed_group.getReturnPort("out")
    ]


def test_image_loader_metadata_precedes_host_file_rules(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Published representation colorspace wins over host/global file rules."""
    environment = _load_loader_modules(monkeypatch, import_graph=lambda *_args: [])
    monkeypatch.setattr(
        environment.image.colorspace_api,
        "get_imageio_file_rule_colorspace",
        lambda _filepath, _context: "RuleSpace",
    )
    context = _context(tmp_path / "plate.exr", "image-v001")
    context["representation"]["data"] = {"colorspaceData": {"colorspace": "ACEScg"}}

    container_node = environment.image.ImageLoader().load(context)
    source_node = environment.containers.find_managed_node(
        container_node,
        environment.containers.SOURCE_ROLE,
    )

    assert source_node is not None
    assert source_node.getParameter("image.colorspace").getValue(0.0) == "ACEScg"


def test_image_loader_uses_host_file_rule_when_metadata_is_absent(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """AYON host/global file rules are the fallback before native defaults."""
    environment = _load_loader_modules(monkeypatch, import_graph=lambda *_args: [])
    monkeypatch.setattr(
        environment.image.colorspace_api,
        "get_imageio_file_rule_colorspace",
        lambda _filepath, _context: "Utility - sRGB - Texture",
    )
    context = _context(tmp_path / "plate.exr", "image-v001")

    container_node = environment.image.ImageLoader().load(context)
    source_node = environment.containers.find_managed_node(
        container_node,
        environment.containers.SOURCE_ROLE,
    )

    assert source_node is not None
    assert source_node.getParameter("image.colorspace").getValue(0.0) == (
        "Utility - sRGB - Texture"
    )


def test_image_loader_update_rolls_back_colorspace_and_path(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Metadata failure restores both native ImageRead parameters."""
    environment = _load_loader_modules(monkeypatch, import_graph=lambda *_args: [])
    loader = environment.image.ImageLoader()
    initial = _context(tmp_path / "plate.1001.exr", "image-v001")
    initial["representation"].update(
        {
            "context": {"frame": 1001},
            "data": {"colorspaceData": {"colorspace": "sRGB"}},
        }
    )
    container_node = loader.load(initial)
    container = environment.containers.parse_container(container_node)
    source_node = environment.containers.find_managed_node(
        container_node,
        environment.containers.SOURCE_ROLE,
    )
    assert container is not None
    assert source_node is not None
    original_writer = environment.containers.lib.write_json_parameter
    failed_once = False

    def fail_metadata_once(node, parameter_path, data):
        nonlocal failed_once
        if node is container_node and not failed_once:
            failed_once = True
            raise ValueError("metadata write failed")
        original_writer(node, parameter_path, data)

    monkeypatch.setattr(
        environment.containers.lib,
        "write_json_parameter",
        fail_metadata_once,
    )
    update = _context(tmp_path / "plate.1002.exr", "image-v002")
    update["representation"].update(
        {
            "context": {"frame": 1002},
            "data": {"colorspaceData": {"colorspace": "ACEScg"}},
        }
    )

    with pytest.raises(ValueError, match="metadata write failed"):
        loader.update(container, update)

    assert source_node.getParameter("file").getValue(0.0).endswith("plate.####.exr")
    assert source_node.getParameter("image.colorspace").getValue(0.0) == "sRGB"
    assert (
        environment.containers.parse_container(container_node)["representation"]
        == "image-v001"
    )


def test_usd_loader_supports_usdz_and_optional_entity_uri(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The server setting can preserve a resolver URI in native UsdIn."""
    environment = _load_loader_modules(monkeypatch, import_graph=lambda *_args: [])
    loader_class = environment.usd.UsdLoader
    assert "usdz" in loader_class.extensions
    assert {
        "assembly",
        "camera",
        "layout",
        "look",
        "usd",
        "usdCamera",
    } <= loader_class.product_base_types
    assert (
        environment.clear_usd_cache.ClearUsdResolverCache.product_base_types
        == loader_class.product_base_types
    )
    assert "rendersetup" in environment.katana.KatanaImportLoader.product_base_types
    loader_class.use_ayon_entity_uri = True
    context = _context(tmp_path / "asset.usdz", "usd-representation")
    context["test_entity_uri"] = (
        "ayon://LoaderSafety/asset?product=assetMain&version=1&representation=usd"
    )

    container_node = loader_class().load(context)
    source_node = environment.containers.find_managed_node(
        container_node,
        environment.containers.SOURCE_ROLE,
    )

    assert source_node is not None
    assert (
        source_node.getParameter("fileName").getValue(0.0) == context["test_entity_uri"]
    )


def test_usd_sublayer_loader_composes_into_native_graph(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The native loader authors a managed UsdSubLayerAdd source node."""
    environment = _load_loader_modules(monkeypatch, import_graph=lambda *_args: [])
    loader_class = environment.usd.UsdSublayerLoader
    assert loader_class.label == "Sublayer USD (Native Graph)"
    assert "usdz" not in loader_class.extensions
    assert loader_class.get_options([]) == []
    assert (
        loader_class.product_base_types == environment.usd.UsdLoader.product_base_types
    )

    loader_class.use_ayon_entity_uri = True
    context = _context(tmp_path / "camera.usd", "camera-representation")
    context["test_entity_uri"] = (
        "ayon://LoaderSafety/asset?product=cameraMain&version=1&representation=usd"
    )

    container_node = loader_class().load(context)
    source_node = environment.containers.find_managed_node(
        container_node,
        environment.containers.SOURCE_ROLE,
    )

    assert source_node is not None
    assert source_node.node_type == "UsdSubLayerAdd"
    assert source_node.getParameter("asset").getValue(0.0) == context["test_entity_uri"]
    assert source_node.getOutputPort("out").getConnectedPorts() == [
        environment.containers.get_managed_group(container_node).getReturnPort("out")
    ]


def test_server_settings_enable_native_image_and_optional_usd_uri() -> None:
    """Loader discovery and server defaults expose both new controls."""
    settings_path = Path(__file__).parents[1] / "server" / "settings" / "main.py"
    tree = ast.parse(settings_path.read_text(encoding="utf-8"))
    defaults = next(
        ast.literal_eval(node.value)
        for node in tree.body
        if isinstance(node, ast.Assign)
        and any(
            isinstance(target, ast.Name) and target.id == "DEFAULT_VALUES"
            for target in node.targets
        )
    )

    expected_usd_settings = {
        "enabled": True,
        "use_ayon_entity_uri": False,
    }
    assert defaults["load"]["UsdLoader"] == expected_usd_settings
    assert defaults["load"]["UsdSublayerLoader"] == expected_usd_settings
    assert defaults["load"]["ImageLoader"] == {"enabled": True}


def _graph_importer(graph):
    """Return a controllable importer that creates one usable source node."""

    def import_graph(filepath, parent_node, _float_nodes):
        name = Path(filepath).stem
        if name == "raises":
            raise ValueError("broken Katana file")
        source_node = graph.CreateNode("Group", parent_node)
        source_node.setName(f"Imported_{name}")
        if name != "invalid":
            output_name = "o0" if name == "custom" else "out"
            source_node.addOutputPort(output_name)
        return [source_node]

    return import_graph


def _make_import_loader(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """Create a loaded Katana container and paths for update tests."""
    graph_holder = {}

    def import_graph(filepath, parent_node, float_nodes):
        return _graph_importer(graph_holder["graph"])(
            filepath,
            parent_node,
            float_nodes,
        )

    environment = _load_loader_modules(monkeypatch, import_graph)
    graph_holder["graph"] = environment.graph
    paths = {
        name: tmp_path / f"{name}.katana"
        for name in ("initial", "updated", "custom", "raises", "invalid")
    }
    for path in paths.values():
        path.write_text("test Katana graph", encoding="utf-8")
    loader = environment.katana.KatanaImportLoader()
    container_node = loader.load(_context(paths["initial"], "representation-initial"))
    return environment, loader, container_node, paths


def test_katana_load_failure_removes_incomplete_container(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A failed initial graph import rolls back and preserves its exception."""
    graph_holder = {}

    def import_graph(filepath, parent_node, float_nodes):
        return _graph_importer(graph_holder["graph"])(
            filepath,
            parent_node,
            float_nodes,
        )

    environment = _load_loader_modules(monkeypatch, import_graph)
    graph_holder["graph"] = environment.graph
    filepath = tmp_path / "raises.katana"
    filepath.write_text("broken Katana graph", encoding="utf-8")
    loader = environment.katana.KatanaImportLoader()

    with pytest.raises(ValueError, match="broken Katana file"):
        loader.load(_context(filepath, "representation-broken"))

    assert environment.graph.root.getChildren() == []


def test_katana_update_stages_then_replaces_managed_graph(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A successful update replaces only the managed graph and metadata."""
    environment, loader, container_node, paths = _make_import_loader(
        tmp_path,
        monkeypatch,
    )
    old_managed_group = environment.containers.get_managed_group(container_node)
    user_group = environment.containers.get_user_group(container_node)
    assert old_managed_group is not None
    assert user_group is not None
    user_node = environment.graph.CreateNode("Group", user_group)
    user_node.setName("ArtistAdjustment")

    imported_nodes = loader.update(
        environment.containers.parse_container(container_node),
        _context(paths["updated"], "representation-updated"),
    )

    new_managed_group = environment.containers.get_managed_group(container_node)
    assert new_managed_group is not None
    assert new_managed_group is not old_managed_group
    assert new_managed_group.getName() == environment.containers.MANAGED_GROUP_NAME
    assert old_managed_group.deleted
    assert imported_nodes[0].getName() == "Imported_updated"
    assert user_group.getChild("ArtistAdjustment") is user_node
    assert user_group.getInputPort("in").getConnectedPorts() == [
        new_managed_group.getOutputPort("out")
    ]
    assert (
        environment.containers.parse_container(container_node)["representation"]
        == "representation-updated"
    )


def test_katana_import_loader_accepts_custom_terminal_output(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Imported graphs may expose terminal ports with arbitrary names."""
    environment, loader, container_node, paths = _make_import_loader(
        tmp_path,
        monkeypatch,
    )

    imported_nodes = loader.update(
        environment.containers.parse_container(container_node),
        _context(paths["custom"], "representation-custom"),
    )

    managed_group = environment.containers.get_managed_group(container_node)
    assert managed_group is not None
    custom_port = imported_nodes[0].getOutputPort("o0")
    assert custom_port is not None
    assert custom_port.getConnectedPorts() == [managed_group.getReturnPort("out")]


def test_katana_update_failed_import_preserves_existing_graph_and_metadata(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A failed import removes only its temporary group."""
    environment, loader, container_node, paths = _make_import_loader(
        tmp_path,
        monkeypatch,
    )
    old_managed_group = environment.containers.get_managed_group(container_node)
    user_group = environment.containers.get_user_group(container_node)
    before = environment.containers.parse_container(container_node)
    assert old_managed_group is not None
    assert user_group is not None
    user_node = environment.graph.CreateNode("Group", user_group)
    user_node.setName("ArtistAdjustment")

    with pytest.raises(ValueError, match="broken Katana file"):
        loader.update(
            before,
            _context(paths["raises"], "representation-raises"),
        )

    after = environment.containers.parse_container(container_node)
    assert environment.containers.get_managed_group(container_node) is old_managed_group
    assert not old_managed_group.deleted
    assert after["representation"] == before["representation"]
    assert user_group.getChild("ArtistAdjustment") is user_node
    assert not any(
        child.getName() == environment.katana._TEMP_MANAGED_GROUP_NAME
        for child in container_node.getChildren()
    )


def test_katana_update_invalid_graph_preserves_existing_graph_and_metadata(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """An import without a usable output cannot replace the active graph."""
    environment, loader, container_node, paths = _make_import_loader(
        tmp_path,
        monkeypatch,
    )
    old_managed_group = environment.containers.get_managed_group(container_node)
    before = environment.containers.parse_container(container_node)
    assert old_managed_group is not None

    with pytest.raises(RuntimeError, match="no usable terminal output port"):
        loader.update(
            before,
            _context(paths["invalid"], "representation-invalid"),
        )

    after = environment.containers.parse_container(container_node)
    assert environment.containers.get_managed_group(container_node) is old_managed_group
    assert not old_managed_group.deleted
    assert after["representation"] == before["representation"]


def test_managed_group_validation_preserves_error_when_cleanup_fails(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Cleanup failure must not mask an invalid container-state error."""
    environment, _loader, container_node, _paths = _make_import_loader(
        tmp_path,
        monkeypatch,
    )
    user_group = environment.containers.get_user_group(container_node)
    assert user_group is not None
    user_group.delete()

    replacement_group = environment.containers.create_managed_group(
        container_node,
        name="AYON_MANAGED_PENDING",
        role=None,
    )

    def fail_delete():
        raise RuntimeError("cleanup failed")

    monkeypatch.setattr(replacement_group, "delete", fail_delete)

    with pytest.raises(RuntimeError, match="missing its managed/user groups"):
        environment.containers.replace_managed_group(
            container_node,
            replacement_group,
            {"representation": "representation-updated"},
        )


def test_katana_update_metadata_failure_restores_existing_graph_and_metadata(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A metadata write failure restores the previous graph and container state."""
    environment, loader, container_node, paths = _make_import_loader(
        tmp_path,
        monkeypatch,
    )
    old_managed_group = environment.containers.get_managed_group(container_node)
    user_group = environment.containers.get_user_group(container_node)
    before = environment.containers.parse_container(container_node)
    assert old_managed_group is not None
    assert user_group is not None
    assert before is not None

    original_update_container = environment.containers.update_container

    def fail_after_metadata_write(node, data):
        original_update_container(node, data)
        if data.get("representation") == "representation-updated":
            raise ValueError("metadata write failed")

    monkeypatch.setattr(
        environment.katana.containers,
        "update_container",
        fail_after_metadata_write,
    )

    with pytest.raises(ValueError, match="metadata write failed"):
        loader.update(
            before,
            _context(paths["updated"], "representation-updated"),
        )

    after = environment.containers.parse_container(container_node)
    assert after is not None
    assert environment.containers.get_managed_group(container_node) is old_managed_group
    assert not old_managed_group.deleted
    assert after["representation"] == before["representation"]
    assert user_group.getInputPort("in").getConnectedPorts() == [
        old_managed_group.getOutputPort("out")
    ]
    assert old_managed_group.getName() == environment.containers.MANAGED_GROUP_NAME
    assert not any(
        child.getName() == environment.katana._TEMP_MANAGED_GROUP_NAME
        for child in container_node.getChildren()
    )


def test_katana_update_old_group_delete_failure_keeps_replacement_active(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Post-commit cleanup failure must not invalidate a successful update."""
    environment, loader, container_node, paths = _make_import_loader(
        tmp_path,
        monkeypatch,
    )
    old_managed_group = environment.containers.get_managed_group(container_node)
    user_group = environment.containers.get_user_group(container_node)
    before = environment.containers.parse_container(container_node)
    assert old_managed_group is not None
    assert user_group is not None
    assert before is not None

    def fail_delete():
        raise RuntimeError("old group delete failed")

    monkeypatch.setattr(old_managed_group, "delete", fail_delete)

    imported_nodes = loader.update(
        before,
        _context(paths["updated"], "representation-updated"),
    )

    new_managed_group = environment.containers.get_managed_group(container_node)
    after = environment.containers.parse_container(container_node)
    assert new_managed_group is not None
    assert new_managed_group is not old_managed_group
    assert old_managed_group in container_node.getChildren()
    assert user_group.getInputPort("in").getConnectedPorts() == [
        new_managed_group.getOutputPort("out")
    ]
    assert after is not None
    assert after["representation"] == "representation-updated"
    assert imported_nodes[0].getName() == "Imported_updated"
    assert "Could not delete the previous managed group" in caplog.text


def test_katana_import_loader_switch_and_remove_still_work(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Switch uses the staged update and removal deletes the outer container."""
    environment, loader, container_node, paths = _make_import_loader(
        tmp_path,
        monkeypatch,
    )

    loader.switch(
        environment.containers.parse_container(container_node),
        _context(paths["updated"], "representation-updated"),
    )

    assert (
        environment.containers.parse_container(container_node)["representation"]
        == "representation-updated"
    )
    loader.remove(environment.containers.parse_container(container_node))
    assert container_node.deleted
