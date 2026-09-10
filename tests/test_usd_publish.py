"""Focused contracts for native Katana USD layer publishing."""

from __future__ import annotations

import ast
import importlib.util
import logging
import sys
import types
from pathlib import Path

import pytest

ROOT = Path(__file__).parents[1]


class FakeParameter:
    """Small Katana parameter storing one time-independent value."""

    def __init__(self, value) -> None:
        self.value = value

    def getValue(self, _time: float):
        """Return the current value."""
        return self.value

    def setValue(self, value, _time: float) -> None:
        """Replace the current value."""
        self.value = value


class FakePort:
    """Katana port stand-in with connection tracking."""

    def __init__(self, node=None) -> None:
        self.node = node
        self.connected = []

    def connect(self, other) -> None:
        """Connect this output to one input port."""
        self.connected.append(other)
        other.connected.append(self)

    def getConnectedPorts(self) -> list:
        """Return all connected ports."""
        return list(self.connected)

    def getNode(self):
        """Return the node owning this port."""
        return self.node


class FakeSourceNode:
    """Katana source node with a configurable node flavor."""

    def __init__(
        self,
        name: str = "NativeUsdSource",
        node_type: str = "UsdLayerWrite",
    ) -> None:
        self.name = name
        self.node_type = node_type
        self.output_port = FakePort(self)

    def getName(self) -> str:
        """Return the node name."""
        return self.name

    def getType(self) -> str:
        """Return the node type."""
        return self.node_type

    def getOutputPort(self, name: str):
        """Return the native output port."""
        return self.output_port if name == "out" else None


class FakeUsdExportNode:
    """Native ``UsdLayerExport`` stand-in used across unit tests."""

    def __init__(self, name: str = "usdLayerMain") -> None:
        self.name = name
        self.deleted = False
        self.input_port = FakePort(self)
        self.define_port = FakePort(self)
        self.parameters = {
            "saveTo": FakeParameter("artist/original.usd"),
            "_savedTo": FakeParameter("artist/original.usd"),
            "usdFileFormat": FakeParameter("usd"),
            "time.timeSamples": FakeParameter("Current Frame"),
            "time.frameRange.i0": FakeParameter(1001.0),
            "time.frameRange.i1": FakeParameter(1010.0),
            "time.samplesPerFrame": FakeParameter(1.0),
            "exportOptions.exportMethod": FakeParameter("Keep Composition Arcs"),
        }
        self.write_result = True

    def getName(self) -> str:
        """Return the node name."""
        return self.name

    def getType(self) -> str:
        """Return the native node type."""
        return "UsdLayerExport"

    def getParameter(self, name: str):
        """Return a named fake parameter."""
        return self.parameters.get(name)

    def getInputPort(self, name: str):
        """Return the native input port."""
        if name == "in":
            return self.input_port
        if name == "define":
            return self.define_port
        return None

    def write(self):
        """Write a small valid-looking USDA layer to the configured path."""
        if not hasattr(self, "_layerDefineNode"):
            raise AttributeError("_layerDefineNode")
        if not self.write_result:
            return None
        path = Path(self.parameters["saveTo"].value)
        path.write_text('#usda 1.0\ndef Xform "Published" {}\n', encoding="utf-8")
        self.parameters["_savedTo"].value = path.as_posix()
        return path.as_posix(), path.as_posix()

    def delete(self) -> None:
        """Record node deletion."""
        self.deleted = True


class FakeCreatedInstance(dict):
    """CreatedInstance-compatible mapping for creator tests."""

    def __init__(self, data: dict, node: FakeUsdExportNode) -> None:
        super().__init__(data)
        self.transient_data = {"node": node}

    def data_to_store(self) -> dict:
        """Return serializable creator data."""
        return dict(self)


class FakeCreatorBase:
    """Minimal inherited Katana creator behavior."""

    def create(self, _product_name, instance_data, _pre_create_data):
        """Return the prepared instance around the configured fake node."""
        return FakeCreatedInstance(instance_data, self.export_node)

    def _remove_instance_from_context(self, instance) -> None:
        """Record creator-context cleanup."""
        self.removed_instance = instance


class FakeCreatorError(RuntimeError):
    """Creator error counterpart for isolated tests."""


class FakeOptionalMixin:
    """Minimal optional publish plug-in activation mixin."""

    def is_active(self, _data: dict) -> bool:
        """Keep the plug-in active in focused tests."""
        return True


class FakeInstancePlugin:
    """Minimal Pyblish instance plug-in base."""

    log = logging.getLogger("test_usd_publish")


class FakeExtractor:
    """Minimal AYON extractor base."""

    log = logging.getLogger("test_usd_publish")


class FakeValidationError(RuntimeError):
    """Validation error preserving the optional title argument."""

    def __init__(self, message: str, *, title: str | None = None) -> None:
        super().__init__(message)
        self.title = title


class FakePublishError(RuntimeError):
    """Publish error counterpart for isolated tests."""


class FakeSdfLayer:
    """Small extracted USD layer used by contribution validation tests."""

    def __init__(self, default_prim: str, prim_paths=()) -> None:
        self.defaultPrim = default_prim
        self.prim_paths = set(prim_paths)

    def GetPrimAtPath(self, path: str):
        """Return a stand-in prim spec when the path exists."""
        return object() if path in self.prim_paths else None


def _load_module(monkeypatch, name: str, path: Path):
    """Load one source file under a controlled module name."""
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    monkeypatch.setitem(sys.modules, name, module)
    spec.loader.exec_module(module)
    return module


def _load_usd_api(monkeypatch):
    """Load USD helpers without importing a real AYON connection."""
    ayon_api = types.ModuleType("ayon_api")
    ayon_api.post = lambda *_args, **_kwargs: None
    monkeypatch.setitem(sys.modules, "ayon_api", ayon_api)
    katana = types.ModuleType("Katana")
    katana.NodegraphAPI = types.SimpleNamespace(
        GetNodeFlavors=lambda node_type: (
            ["nativeusd"] if node_type.startswith("Usd") else ["3d"]
        )
    )
    monkeypatch.setitem(sys.modules, "Katana", katana)
    return _load_module(
        monkeypatch,
        "ayon_katana.api.usd",
        ROOT / "client" / "ayon_katana" / "api" / "usd.py",
    )


def _install_api_package(monkeypatch, **modules) -> None:
    """Install a compact ``ayon_katana.api`` module tree."""
    package = types.ModuleType("ayon_katana")
    package.__path__ = []
    api = types.ModuleType("ayon_katana.api")
    api.__path__ = []
    plugins = types.ModuleType("ayon_katana.plugins")
    plugins.__path__ = []
    create = types.ModuleType("ayon_katana.plugins.create")
    create.__path__ = []
    publish = types.ModuleType("ayon_katana.plugins.publish")
    publish.__path__ = []
    monkeypatch.setitem(sys.modules, "ayon_katana", package)
    monkeypatch.setitem(sys.modules, "ayon_katana.api", api)
    monkeypatch.setitem(sys.modules, "ayon_katana.plugins", plugins)
    monkeypatch.setitem(sys.modules, "ayon_katana.plugins.create", create)
    monkeypatch.setitem(sys.modules, "ayon_katana.plugins.publish", publish)
    for name, module in modules.items():
        setattr(api, name, module)
        monkeypatch.setitem(sys.modules, f"ayon_katana.api.{name}", module)


def _install_publish_runtime(monkeypatch, node_map, usd_module) -> None:
    """Install the compact Core, Pyblish, and Katana publish runtime."""
    pyblish_api = types.ModuleType("pyblish.api")
    pyblish_api.CollectorOrder = 1.0
    pyblish_api.ValidatorOrder = 2.0
    pyblish_api.ExtractorOrder = 3.0
    pyblish = types.ModuleType("pyblish")
    pyblish.api = pyblish_api
    monkeypatch.setitem(sys.modules, "pyblish", pyblish)
    monkeypatch.setitem(sys.modules, "pyblish.api", pyblish_api)

    ayon_core = types.ModuleType("ayon_core")
    pipeline = types.ModuleType("ayon_core.pipeline")
    pipeline.OptionalPyblishPluginMixin = FakeOptionalMixin
    publish = types.ModuleType("ayon_core.pipeline.publish")
    publish.PublishValidationError = FakeValidationError
    publish.PublishError = FakePublishError
    usdlib = types.ModuleType("ayon_core.pipeline.usdlib")
    usdlib.get_standard_default_prim_name = lambda path: path.rstrip("/").rsplit(
        "/", 1
    )[-1]
    pipeline.publish = types.SimpleNamespace(Extractor=FakeExtractor)
    ayon_core.pipeline = pipeline
    monkeypatch.setitem(sys.modules, "ayon_core", ayon_core)
    monkeypatch.setitem(sys.modules, "ayon_core.pipeline", pipeline)
    monkeypatch.setitem(sys.modules, "ayon_core.pipeline.publish", publish)
    monkeypatch.setitem(sys.modules, "ayon_core.pipeline.usdlib", usdlib)

    _install_api_package(
        monkeypatch,
        compat=types.SimpleNamespace(get_node=node_map.get),
        plugin=types.SimpleNamespace(
            KatanaInstancePlugin=FakeInstancePlugin,
            KatanaExtractorPlugin=FakeExtractor,
        ),
        usd=usd_module,
    )


def _load_contribution_validator(monkeypatch, layer: FakeSdfLayer | None):
    """Load the contribution validator with a controlled Sdf layer result."""
    sdf = types.ModuleType("pxr.Sdf")
    sdf.Layer = types.SimpleNamespace(FindOrOpen=lambda _path: layer)
    pxr = types.ModuleType("pxr")
    pxr.Sdf = sdf
    monkeypatch.setitem(sys.modules, "pxr", pxr)
    monkeypatch.setitem(sys.modules, "pxr.Sdf", sdf)
    return _load_module(
        monkeypatch,
        "ayon_katana.plugins.publish.validate_usd_asset_contribution_default_prim",
        ROOT
        / "client"
        / "ayon_katana"
        / "plugins"
        / "publish"
        / "validate_usd_asset_contribution_default_prim.py",
    )


def _contribution_instance(tmp_path: Path, *, enabled: bool = True):
    """Return an extracted Katana USD instance with contribution attributes."""
    return types.SimpleNamespace(
        data={
            "folderPath": "/sequences/sq01/sh01",
            "stagingDir": str(tmp_path),
            "representations": [
                {
                    "name": "usd",
                    "ext": "usd",
                    "files": "cameraMain.usd",
                    "stagingDir": str(tmp_path),
                }
            ],
            "publish_attributes": {
                "CollectUSDLayerContributions": {
                    "contribution_enabled": enabled,
                    "contribution_target_product_init": "asset",
                }
            },
        }
    )


def test_usd_api_configures_and_transactionally_exports(
    monkeypatch,
    tmp_path: Path,
) -> None:
    """Native settings are validated and transient output paths are restored."""
    usd = _load_usd_api(monkeypatch)
    node = FakeUsdExportNode()
    define_source = FakeSourceNode(
        name="NativeUsdLayerDefine",
        node_type="UsdLayerDefine",
    )
    define_source.output_port.connect(node.define_port)
    usd.configure_usd_layer_export(
        node,
        file_format="usda",
        time_samples="Frame Range",
        frame_start=1001,
        frame_end=1010,
        samples_per_frame=2,
        export_method="Flatten All",
    )

    destination = tmp_path / "usdLayerMain.usda"
    result = usd.export_usd_layer(node, destination)

    assert result == destination
    assert destination.read_text(encoding="utf-8").startswith("#usda 1.0")
    assert node.getParameter("saveTo").value == "artist/original.usd"
    assert node.getParameter("_savedTo").value == "artist/original.usd"
    assert node.getParameter("usdFileFormat").value == "usda"
    assert node.getParameter("time.timeSamples").value == "Frame Range"
    assert node.getParameter("exportOptions.exportMethod").value == "Flatten All"
    assert node._layerDefineNode is define_source


def test_usd_api_rejects_failed_native_write_and_removes_stale_file(
    monkeypatch,
    tmp_path: Path,
) -> None:
    """A silent native write failure cannot publish a stale staged layer."""
    usd = _load_usd_api(monkeypatch)
    node = FakeUsdExportNode()
    node.write_result = False
    destination = tmp_path / "usdLayerMain.usd"
    destination.write_text("stale", encoding="utf-8")

    with pytest.raises(RuntimeError, match="no success result"):
        usd.export_usd_layer(node, destination)

    assert not destination.exists()
    assert node.getParameter("saveTo").value == "artist/original.usd"


def _load_creator(monkeypatch, selected_nodes):
    """Load ``CreateUsdLayer`` with controlled Core and Katana APIs."""
    usd = _load_usd_api(monkeypatch)
    ayon_core = types.ModuleType("ayon_core")
    lib = types.ModuleType("ayon_core.lib")

    class AttrDef:
        def __init__(self, *_args, **_kwargs) -> None:
            pass

    lib.BoolDef = AttrDef
    lib.EnumDef = AttrDef
    lib.NumberDef = AttrDef
    pipeline = types.ModuleType("ayon_core.pipeline")
    pipeline.CreatorError = FakeCreatorError
    ayon_core.lib = lib
    ayon_core.pipeline = pipeline
    monkeypatch.setitem(sys.modules, "ayon_core", ayon_core)
    monkeypatch.setitem(sys.modules, "ayon_core.lib", lib)
    monkeypatch.setitem(sys.modules, "ayon_core.pipeline", pipeline)

    imprinted = []
    compat = types.SimpleNamespace(
        get_selected_nodes=lambda: list(selected_nodes),
        get_output_ports=lambda node: [node.output_port],
    )
    instances = types.SimpleNamespace(
        imprint=lambda node, data: imprinted.append((node, dict(data)))
    )
    plugin = types.SimpleNamespace(KatanaCreator=FakeCreatorBase)
    _install_api_package(
        monkeypatch,
        compat=compat,
        instances=instances,
        plugin=plugin,
        usd=usd,
    )
    module = _load_module(
        monkeypatch,
        "ayon_katana.plugins.create.create_usd_layer",
        ROOT / "client" / "ayon_katana" / "plugins" / "create" / "create_usd_layer.py",
    )
    return module, imprinted


def test_creator_connects_selected_output_and_persists_native_node(monkeypatch) -> None:
    """Creator wires one selected source directly into ``UsdLayerExport``."""

    source = FakeSourceNode()
    module, imprinted = _load_creator(monkeypatch, [source])
    creator = object.__new__(module.CreateUsdLayer)
    creator.export_node = FakeUsdExportNode()
    creator.create_context = types.SimpleNamespace(
        get_current_folder_entity=lambda: {
            "attrib": {"frameStart": 1001, "frameEnd": 1010}
        }
    )

    created = creator.create(
        "usdLayerMain",
        {"families": []},
        {
            "use_selection": True,
            "usd_format": "usda",
            "time_samples": "Frame Range",
            "frame_start": 1001,
            "frame_end": 1010,
        },
    )

    assert creator.export_node.input_port in source.output_port.connected
    assert created["instance_node"] == "usdLayerMain"
    assert "usd_export_node" not in created
    assert created["families"] == ["usd", "katana.usd"]
    assert creator.export_node.getParameter("usdFileFormat").value == "usda"
    assert imprinted[-1][1]["instance_node"] == "usdLayerMain"


def test_creator_requires_exactly_one_selected_source(monkeypatch) -> None:
    """Selection-based creation rejects missing native USD sources."""
    module, _imprinted = _load_creator(monkeypatch, [])
    creator = object.__new__(module.CreateUsdLayer)

    with pytest.raises(FakeCreatorError, match="exactly one"):
        creator.create("usdLayerMain", {}, {"use_selection": True})


def test_creator_rejects_non_native_usd_source(monkeypatch) -> None:
    """Selection-based creation rejects connectable Geolib outputs."""
    source = FakeSourceNode(name="OpResolve", node_type="OpResolve")
    module, _imprinted = _load_creator(monkeypatch, [source])
    creator = object.__new__(module.CreateUsdLayer)

    with pytest.raises(FakeCreatorError, match="not a native USD node"):
        creator.create("usdLayerMain", {}, {"use_selection": True})


@pytest.mark.parametrize(
    ("class_name", "product_base_type", "label", "time_samples"),
    [
        ("CreateUsdLook", "look", "USD Look", "Current Frame"),
        ("CreateUsdCamera", "camera", "USD Camera", "Frame Range"),
        ("CreateUsdLayout", "layout", "USD Layout", "Current Frame"),
        ("CreateUsdAssembly", "assembly", "USD Assembly", "Current Frame"),
    ],
)
def test_semantic_usd_creators_reuse_native_layer_contract(
    monkeypatch,
    class_name: str,
    product_base_type: str,
    label: str,
    time_samples: str,
) -> None:
    """Semantic products retain one native USD creation implementation."""
    module, _imprinted = _load_creator(monkeypatch, [])
    creator_class = getattr(module, class_name)

    assert issubclass(creator_class, module.CreateUsdLayer)
    assert creator_class.product_base_type == product_base_type
    assert creator_class.product_type == product_base_type
    assert creator_class.label == label
    assert creator_class.identifier.startswith("io.ayon.creators.katana.usd_")
    assert creator_class.default_time_samples == time_samples


@pytest.mark.parametrize("legacy_alias", [None, "ObsoleteAlias"])
def test_collect_validate_extract_produces_one_usd_representation(
    monkeypatch,
    tmp_path: Path,
    legacy_alias,
) -> None:
    """Publish plug-ins read live settings and emit one verified USD layer."""
    usd = _load_usd_api(monkeypatch)
    node = FakeUsdExportNode()
    FakeSourceNode().output_port.connect(node.input_port)
    _install_publish_runtime(monkeypatch, {node.getName(): node}, usd)
    collector_module = _load_module(
        monkeypatch,
        "ayon_katana.plugins.publish.collect_usd_layer",
        ROOT
        / "client"
        / "ayon_katana"
        / "plugins"
        / "publish"
        / "collect_usd_layer.py",
    )
    validator_module = _load_module(
        monkeypatch,
        "ayon_katana.plugins.publish.validate_usd_layer",
        ROOT
        / "client"
        / "ayon_katana"
        / "plugins"
        / "publish"
        / "validate_usd_layer.py",
    )
    extractor_module = _load_module(
        monkeypatch,
        "ayon_katana.plugins.publish.extract_usd_layer",
        ROOT
        / "client"
        / "ayon_katana"
        / "plugins"
        / "publish"
        / "extract_usd_layer.py",
    )
    assert collector_module.CollectUsdLayer.families == ["katana.usd"]
    assert validator_module.ValidateUsdLayer.families == ["katana.usd"]
    assert extractor_module.ExtractUsdLayer.families == ["katana.usd"]
    assert extractor_module.ExtractUsdLayer.order == 2.5

    instance = types.SimpleNamespace(
        data={"instance_node": node.getName(), "productName": "usdLayerMain"}
    )
    if legacy_alias is not None:
        instance.data["usd_export_node"] = legacy_alias

    collector_module.CollectUsdLayer().process(instance)
    validator_module.ValidateUsdLayer().process(instance)
    extractor = extractor_module.ExtractUsdLayer()
    extractor.staging_dir = lambda _instance: str(tmp_path)
    extractor.process(instance)

    assert instance.data["usdFileFormat"] == "usd"
    assert instance.data["representations"] == [
        {
            "name": "usd",
            "ext": "usd",
            "files": "usdLayerMain.usd",
            "stagingDir": str(tmp_path),
        }
    ]
    assert (tmp_path / "usdLayerMain.usd").is_file()
    assert node.getParameter("saveTo").value == "artist/original.usd"


def test_missing_export_node_is_reported_during_validation(monkeypatch) -> None:
    """An artist-deleted node yields the dedicated validator error after collection."""
    usd = _load_usd_api(monkeypatch)
    _install_publish_runtime(monkeypatch, {}, usd)
    publish_path = ROOT / "client/ayon_katana/plugins/publish"
    collector = _load_module(
        monkeypatch, "missing_usd_collector", publish_path / "collect_usd_layer.py"
    )
    validator = _load_module(
        monkeypatch, "missing_usd_validator", publish_path / "validate_usd_layer.py"
    )
    instance = types.SimpleNamespace(data={"instance_node": "DeletedExport"})

    collector.CollectUsdLayer().process(instance)
    with pytest.raises(FakeValidationError, match="does not exist") as caught:
        validator.ValidateUsdLayer().process(instance)
    assert caught.value.title == "USD export node missing"


def test_validator_rejects_disconnected_native_export(monkeypatch) -> None:
    """A USD publish instance cannot pass without one native source."""
    usd = _load_usd_api(monkeypatch)
    node = FakeUsdExportNode()
    _install_publish_runtime(monkeypatch, {node.getName(): node}, usd)
    validator_module = _load_module(
        monkeypatch,
        "ayon_katana.plugins.publish.validate_usd_layer",
        ROOT
        / "client"
        / "ayon_katana"
        / "plugins"
        / "publish"
        / "validate_usd_layer.py",
    )

    with pytest.raises(FakeValidationError, match="exactly one"):
        validator_module.ValidateUsdLayer().process(
            types.SimpleNamespace(data={"instance_node": node.getName()})
        )


def test_validator_rejects_connected_geolib_source(monkeypatch) -> None:
    """A connectable Geolib output is not accepted as native USD data."""
    usd = _load_usd_api(monkeypatch)
    node = FakeUsdExportNode()
    FakeSourceNode(name="OpResolve", node_type="OpResolve").output_port.connect(
        node.input_port
    )
    _install_publish_runtime(monkeypatch, {node.getName(): node}, usd)
    validator_module = _load_module(
        monkeypatch,
        "ayon_katana.plugins.publish.validate_usd_layer",
        ROOT
        / "client"
        / "ayon_katana"
        / "plugins"
        / "publish"
        / "validate_usd_layer.py",
    )

    with pytest.raises(FakeValidationError, match="not a native USD node"):
        validator_module.ValidateUsdLayer().process(
            types.SimpleNamespace(data={"instance_node": node.getName()})
        )


def test_asset_contribution_validation_skips_when_disabled(
    monkeypatch,
    tmp_path: Path,
) -> None:
    """A plain USD publish does not require an asset-style default prim."""
    usd = _load_usd_api(monkeypatch)
    _install_publish_runtime(monkeypatch, {}, usd)
    module = _load_contribution_validator(monkeypatch, None)
    instance = _contribution_instance(tmp_path, enabled=False)

    module.ValidateUsdAssetContributionDefaultPrim().process(instance)


@pytest.mark.parametrize("default_prim", ["", "cameras"])
def test_asset_contribution_validation_requires_folder_default_prim(
    monkeypatch,
    tmp_path: Path,
    default_prim: str,
) -> None:
    """An asset contribution must default to the current folder root."""
    usd = _load_usd_api(monkeypatch)
    _install_publish_runtime(monkeypatch, {}, usd)
    module = _load_contribution_validator(
        monkeypatch,
        FakeSdfLayer(default_prim, {f"/{default_prim}"}),
    )

    with pytest.raises(FakeValidationError, match="root prim named '/sh01'"):
        module.ValidateUsdAssetContributionDefaultPrim().process(
            _contribution_instance(tmp_path)
        )


def test_asset_contribution_validation_requires_authored_root_prim(
    monkeypatch,
    tmp_path: Path,
) -> None:
    """A defaultPrim token cannot point at an absent root prim spec."""
    usd = _load_usd_api(monkeypatch)
    _install_publish_runtime(monkeypatch, {}, usd)
    module = _load_contribution_validator(
        monkeypatch,
        FakeSdfLayer("sh01"),
    )

    with pytest.raises(FakeValidationError, match="root prim does not exist"):
        module.ValidateUsdAssetContributionDefaultPrim().process(
            _contribution_instance(tmp_path)
        )


def test_asset_contribution_validation_accepts_expected_root(
    monkeypatch,
    tmp_path: Path,
) -> None:
    """A matching authored root and default prim are contribution-safe."""
    usd = _load_usd_api(monkeypatch)
    _install_publish_runtime(monkeypatch, {}, usd)
    module = _load_contribution_validator(
        monkeypatch,
        FakeSdfLayer("sh01", {"/sh01"}),
    )

    validator = module.ValidateUsdAssetContributionDefaultPrim()
    assert validator.order == 2.52
    assert validator.families == ["katana.usd"]
    assert validator.optional is True
    validator.process(_contribution_instance(tmp_path))


def test_server_settings_register_usd_creator_and_publish_plugins() -> None:
    """USD creator, collector, validator, and extractor default to enabled."""
    tree = ast.parse(
        (ROOT / "server" / "settings" / "main.py").read_text(encoding="utf-8")
    )
    assignment = next(
        node
        for node in tree.body
        if isinstance(node, ast.Assign)
        and any(
            isinstance(target, ast.Name) and target.id == "DEFAULT_VALUES"
            for target in node.targets
        )
    )
    defaults = ast.literal_eval(assignment.value)

    assert defaults["create"]["CreateUsdLayer"] == {
        "enabled": True,
        "default_usd_format": "usd",
        "default_time_samples": "Current Frame",
        "default_export_method": "Keep Composition Arcs",
        "default_samples_per_frame": 1.0,
    }
    for creator_name in ("CreateUsdLook", "CreateUsdLayout", "CreateUsdAssembly"):
        assert defaults["create"][creator_name] == defaults["create"]["CreateUsdLayer"]
    assert defaults["create"]["CreateUsdCamera"] == {
        **defaults["create"]["CreateUsdLayer"],
        "default_time_samples": "Frame Range",
    }
    assert defaults["publish"]["CollectUsdLayer"] == {"enabled": True}
    assert defaults["publish"]["ValidateUsdLayer"] == {
        "enabled": True,
        "optional": False,
        "active": True,
    }
    assert defaults["publish"]["ValidateUsdAssetContributionDefaultPrim"] == {
        "enabled": True,
        "optional": True,
        "active": True,
    }
    assert defaults["publish"]["ExtractUsdLayer"] == {"enabled": True}
