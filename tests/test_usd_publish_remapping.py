"""Focused tests for staged Katana USD publish-path finalization."""

from __future__ import annotations

import importlib.util
import os
import sys
import types
from pathlib import Path

import pytest

ROOT = Path(__file__).parents[1]


class FakeInstance:
    """Small publish instance with context and mutable data."""

    def __init__(self, name: str, data: dict) -> None:
        self.name = name
        self.data = data
        self.context = None


class FakeContext(list):
    """Publish context exposing shared data."""

    def __init__(self, instances=()) -> None:
        super().__init__(instances)
        self.data = {}
        for instance in self:
            instance.context = self


class FakePrimPath:
    """Minimal Sdf path used by composition traversal."""

    def IsPrimPath(self) -> bool:
        return True


class FakeLayer:
    """Mutable layer copy used by the fake Sdf/UsdUtils implementation."""

    registry = {}

    def __init__(
        self,
        identifier: str,
        *,
        assets=(),
        sublayers=(),
        format_id: str = "usda",
    ) -> None:
        self.identifier = identifier
        self.realPath = identifier if not identifier.startswith("anon:") else ""
        self.assets = list(assets)
        self.subLayerPaths = list(sublayers)
        self.format_id = format_id
        FakeLayer.registry[identifier.replace("\\", "/")] = self

    def TransferContent(self, other) -> None:
        self.assets = list(other.assets)
        self.subLayerPaths = list(other.subLayerPaths)
        self.format_id = other.format_id

    def Traverse(self, _root, _callback) -> None:
        return None

    def GetPrimAtPath(self, _path):
        return None

    def GetFileFormat(self):
        return types.SimpleNamespace(formatId=self.format_id)

    def Export(self, path: str, args=None):
        output = Path(path)
        output.write_text("\n".join(self.assets), encoding="utf-8")
        FakeLayer(
            path,
            assets=self.assets,
            sublayers=self.subLayerPaths,
            format_id=(args or {}).get("format", self.format_id),
        )
        return True


class FakeStage:
    """Source stage exposing original contributing layers."""

    def __init__(self, layers) -> None:
        self.layers = list(layers)

    def GetLayerStack(self):
        return list(self.layers)


def _install_fake_pxr(monkeypatch):
    """Install Sdf layer cloning and UsdUtils asset-path rewriting fakes."""
    FakeLayer.registry = {}
    sdf = types.ModuleType("pxr.Sdf")
    sdf.Layer = types.SimpleNamespace(
        FindOrOpen=lambda path: FakeLayer.registry.get(path.replace("\\", "/")),
        CreateAnonymous=lambda tag: FakeLayer(f"anon:{tag}"),
    )
    sdf.ComputeAssetPathRelativeToLayer = lambda layer, authored: os.path.normpath(
        str(Path(layer.identifier).parent / authored)
    )
    usd_utils = types.ModuleType("pxr.UsdUtils")

    def modify_asset_paths(layer, callback) -> None:
        layer.assets = [callback(asset) for asset in layer.assets]
        layer.subLayerPaths = [callback(asset) for asset in layer.subLayerPaths]

    usd_utils.ModifyAssetPaths = modify_asset_paths
    pxr = types.ModuleType("pxr")
    pxr.Sdf = sdf
    pxr.UsdUtils = usd_utils
    monkeypatch.setitem(sys.modules, "pxr", pxr)
    monkeypatch.setitem(sys.modules, "pxr.Sdf", sdf)
    monkeypatch.setitem(sys.modules, "pxr.UsdUtils", usd_utils)


def _load_api(monkeypatch):
    """Load the USD publish API with isolated imports."""
    _install_fake_pxr(monkeypatch)
    path = ROOT / "client" / "ayon_katana" / "api" / "usd_publish.py"
    spec = importlib.util.spec_from_file_location("ayon_katana_usd_publish_test", path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_publish_map_includes_forward_active_representations(
    monkeypatch,
    tmp_path: Path,
) -> None:
    """A complete context map includes products appearing later in publish order."""
    module = _load_api(monkeypatch)
    publish_lib = types.ModuleType("ayon_core.pipeline.publish.lib")
    publish_lib.get_instance_expected_output_path = (
        lambda instance, representation_name, ext: str(
            tmp_path / "publish" / f"{instance.data['productName']}.{ext}"
        )
    )
    core = types.ModuleType("ayon_core")
    core.__path__ = []
    pipeline = types.ModuleType("ayon_core.pipeline")
    pipeline.__path__ = []
    publish = types.ModuleType("ayon_core.pipeline.publish")
    publish.__path__ = []
    monkeypatch.setitem(sys.modules, "ayon_core", core)
    monkeypatch.setitem(sys.modules, "ayon_core.pipeline", pipeline)
    monkeypatch.setitem(sys.modules, "ayon_core.pipeline.publish", publish)
    monkeypatch.setitem(sys.modules, "ayon_core.pipeline.publish.lib", publish_lib)

    first = FakeInstance(
        "first",
        {
            "productName": "first",
            "representations": [
                {
                    "name": "usd",
                    "ext": "usd",
                    "files": "first.usd",
                    "stagingDir": str(tmp_path / "stage"),
                }
            ],
        },
    )
    second = FakeInstance(
        "second",
        {
            "productName": "second",
            "representations": [
                {
                    "name": "usd",
                    "ext": "usd",
                    "files": "second.usd",
                    "stagingDir": str(tmp_path / "stage"),
                }
            ],
        },
    )
    disabled = FakeInstance(
        "disabled",
        {
            "productName": "disabled",
            "active": False,
            "representations": [
                {
                    "name": "usd",
                    "ext": "usd",
                    "files": "disabled.usd",
                    "stagingDir": str(tmp_path / "stage"),
                }
            ],
        },
    )
    context = FakeContext([first, second, disabled])

    mapping = module.build_publish_path_map(context)

    assert mapping[module._mapping_key(tmp_path / "stage" / "first.usd")].endswith(
        "/publish/first.usd"
    )
    assert mapping[module._mapping_key(tmp_path / "stage" / "second.usd")].endswith(
        "/publish/second.usd"
    )
    assert not any("disabled.usd" in key for key in mapping)


def test_rewrite_applies_forward_publish_and_texture_remaps(
    monkeypatch,
    tmp_path: Path,
) -> None:
    """Staging references and look textures are rewritten on a copied layer."""
    module = _load_api(monkeypatch)
    staging = tmp_path / "stage"
    staging.mkdir()
    layer_path = staging / "first.usda"
    layer_path.write_text("original", encoding="utf-8")
    source_layer = FakeLayer(
        layer_path.as_posix(),
        assets=["second.usd", "textures/diffuse.exr"],
    )
    other_staged = staging / "second.usd"
    other_staged.write_bytes(b"other")
    publish_path = tmp_path / "publish" / "second.usd"

    result = module.rewrite_staged_usd_layer(
        layer_path,
        publish_mapping={module._mapping_key(other_staged): publish_path.as_posix()},
        asset_remap={
            os.path.normpath("textures/diffuse.exr"): "./resources/diffuse.exr"
        },
    )

    assert result == layer_path
    rewritten = layer_path.read_text(encoding="utf-8").splitlines()
    assert publish_path.as_posix() in rewritten
    assert "./resources/diffuse.exr" in rewritten
    assert not any(str(staging).replace("\\", "/") in value for value in rewritten)
    assert source_layer.assets == ["second.usd", "textures/diffuse.exr"]


def test_rewrite_anchors_external_relative_composition(
    monkeypatch,
    tmp_path: Path,
) -> None:
    """A relative external layer remains stable after the staged layer moves."""
    module = _load_api(monkeypatch)
    source_dir = tmp_path / "source" / "look"
    external_dir = tmp_path / "source" / "external"
    source_dir.mkdir(parents=True)
    external_dir.mkdir(parents=True)
    external = external_dir / "shared.usd"
    external.write_bytes(b"external")
    authored = "../external/shared.usd"
    source_layer = FakeLayer(
        (source_dir / "look.usda").as_posix(),
        sublayers=[authored],
    )
    staged_dir = tmp_path / "stage"
    staged_dir.mkdir()
    staged_path = staged_dir / "look.usda"
    staged_path.write_text("original", encoding="utf-8")
    FakeLayer(staged_path.as_posix(), assets=[authored])

    module.rewrite_staged_usd_layer(
        staged_path,
        publish_mapping={},
        source_stage=FakeStage([source_layer]),
    )

    assert staged_path.read_text(encoding="utf-8").strip() == external.as_posix()


def test_failed_rewrite_preserves_original_staged_layer(
    monkeypatch,
    tmp_path: Path,
) -> None:
    """Unresolved/anonymous dependencies fail before replacing staged output."""
    module = _load_api(monkeypatch)
    for authored in ("missing.usd", "anon:temporary.usd"):
        staged = tmp_path / f"{Path(authored).stem}.usda"
        staged.write_bytes(b"original-bytes")
        FakeLayer(staged.as_posix(), assets=[authored])

        with pytest.raises(ValueError):
            module.rewrite_staged_usd_layer(staged, publish_mapping={})

        assert staged.read_bytes() == b"original-bytes"
        assert not any("ayon_finalize" in path.name for path in tmp_path.iterdir())


def test_existing_absolute_composition_is_preserved(
    monkeypatch,
    tmp_path: Path,
) -> None:
    """Valid absolute external references are not rewritten unnecessarily."""
    module = _load_api(monkeypatch)
    external = tmp_path / "external.usd"
    external.write_bytes(b"external")
    staged = tmp_path / "look.usda"
    staged.write_text("original", encoding="utf-8")
    FakeLayer(staged.as_posix(), assets=[external.as_posix()])

    module.rewrite_staged_usd_layer(staged, publish_mapping={})

    assert staged.read_text(encoding="utf-8").strip() == external.as_posix()


def _load_finalizer(monkeypatch):
    """Load the finalizer with lightweight Katana/Core API packages."""
    pyblish_api = types.ModuleType("pyblish.api")
    pyblish_api.ExtractorOrder = 2.0
    pyblish = types.ModuleType("pyblish")
    pyblish.api = pyblish_api
    monkeypatch.setitem(sys.modules, "pyblish", pyblish)
    monkeypatch.setitem(sys.modules, "pyblish.api", pyblish_api)

    core = types.ModuleType("ayon_core")
    pipeline = types.ModuleType("ayon_core.pipeline")
    publish = types.ModuleType("ayon_core.pipeline.publish")

    class PublishError(RuntimeError):
        """Minimal Core publish error."""

    publish.PublishError = PublishError
    monkeypatch.setitem(sys.modules, "ayon_core", core)
    monkeypatch.setitem(sys.modules, "ayon_core.pipeline", pipeline)
    monkeypatch.setitem(sys.modules, "ayon_core.pipeline.publish", publish)

    package = types.ModuleType("ayon_katana")
    package.__path__ = []
    api = types.ModuleType("ayon_katana.api")
    api.__path__ = []
    api.plugin = types.SimpleNamespace(KatanaContextPlugin=object)
    usd = types.ModuleType("ayon_katana.api.usd")
    usd.get_extracted_usd_layer_path = lambda data: Path(data["layer_path"])
    look = types.ModuleType("ayon_katana.api.usd_look")
    look.get_composed_source_stage = lambda data: data["stage"]
    look.is_look_instance = lambda data: data.get("productType") == "look"
    publish_api = types.ModuleType("ayon_katana.api.usd_publish")
    publish_api.build_publish_path_map = lambda _context: {"mapping": "ready"}
    publish_api.rewrite_staged_usd_layer = lambda *args, **kwargs: None
    resources = types.ModuleType("ayon_katana.api.usd_resources")
    resources.plan_look_resources = lambda *_args: {
        "resources": [
            {
                "attribute": "/Looks/Mat.inputs:file",
                "source": "texture.exr",
                "files": ["C:/textures/texture.exr"],
                "color_space": "ACEScg",
            }
        ],
        "assetRemap": {"texture.exr": "./resources/texture.exr"},
        "transfers": [("C:/textures/texture.exr", "C:/publish/resources/texture.exr")],
    }
    api.usd = usd
    api.usd_look = look
    api.usd_publish = publish_api
    api.usd_resources = resources
    monkeypatch.setitem(sys.modules, "ayon_katana", package)
    monkeypatch.setitem(sys.modules, "ayon_katana.api", api)
    monkeypatch.setitem(sys.modules, "ayon_katana.api.plugin", api.plugin)
    monkeypatch.setitem(sys.modules, "ayon_katana.api.usd", usd)
    monkeypatch.setitem(sys.modules, "ayon_katana.api.usd_look", look)
    monkeypatch.setitem(sys.modules, "ayon_katana.api.usd_publish", publish_api)
    monkeypatch.setitem(sys.modules, "ayon_katana.api.usd_resources", resources)

    path = (
        ROOT
        / "client"
        / "ayon_katana"
        / "plugins"
        / "publish"
        / "finalize_usd_publish.py"
    )
    spec = importlib.util.spec_from_file_location("ayon_katana_finalize_usd_test", path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module, publish_api, resources


def test_finalizer_registers_look_resource_transfers(
    monkeypatch,
    tmp_path: Path,
) -> None:
    """Look finalization explicitly queues resource copies for Core integration."""
    module, _publish_api, _resources = _load_finalizer(monkeypatch)
    _install_fake_pxr(monkeypatch)
    staged = tmp_path / "look.usda"
    staged.write_text("usd", encoding="utf-8")
    FakeLayer(staged.as_posix())
    rewrites = []
    module.rewrite_staged_usd_layer = lambda *args, **kwargs: rewrites.append(
        (args, kwargs)
    )
    instance = FakeInstance(
        "lookMain",
        {
            "productName": "lookMain",
            "productType": "look",
            "families": ["usd", "katana.usd"],
            "layer_path": str(staged),
            "stage": object(),
            "resourcesDir": str(tmp_path / "publish" / "resources"),
            "transfers": [("existing", "existing-destination")],
        },
    )
    context = FakeContext([instance])

    module.FinalizeUsdPublish().process(context)

    assert instance.data["resources"][0]["color_space"] == "ACEScg"
    assert instance.data["assetRemap"] == {"texture.exr": "./resources/texture.exr"}
    assert instance.data["transfers"] == [
        ("existing", "existing-destination"),
        ("C:/textures/texture.exr", "C:/publish/resources/texture.exr"),
    ]
    assert len(rewrites) == 1
    assert module.FinalizeUsdPublish.order == pytest.approx(1.505)


def test_finalizer_deduplicates_existing_look_resource_transfer(monkeypatch) -> None:
    """An already queued identical resource copy is not registered twice."""
    module, _publish_api, resources = _load_finalizer(monkeypatch)
    plan = resources.plan_look_resources(None)
    transfer = plan["transfers"][0]
    instance = FakeInstance(
        "lookMain",
        {
            "resources": [],
            "assetRemap": {},
            "transfers": [transfer],
        },
    )

    module.FinalizeUsdPublish._merge_resource_plan(instance, plan)

    assert instance.data["transfers"] == [transfer]
