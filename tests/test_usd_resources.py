"""Focused tests for pure Katana USD look resource planning."""

from __future__ import annotations

import importlib.util
import os
import sys
import types
from pathlib import Path

import pytest

ROOT = Path(__file__).parents[1]


class FakePropertyPath:
    """Minimal Sdf property path."""

    def __init__(self, value: str) -> None:
        self.pathString = value

    def IsPropertyPath(self) -> bool:
        return True

    def __str__(self) -> str:
        return self.pathString


class FakeAsset:
    """Sdf.AssetPath-like value with optional resolved hint."""

    def __init__(self, path: str, resolved_path: str = "") -> None:
        self.path = path
        self.resolvedPath = resolved_path


class FakeSpec:
    """Authored asset attribute specification."""

    def __init__(
        self,
        path: FakePropertyPath,
        layer,
        *,
        type_name: str = "asset",
        default=None,
        colorspace: str = "",
    ) -> None:
        self.path = path
        self.layer = layer
        self.typeName = type_name
        self.default = default
        self.colorspace = colorspace

    def HasInfo(self, name: str) -> bool:
        return name == "colorSpace" and bool(self.colorspace)

    def GetInfo(self, name: str):
        assert name == "colorSpace"
        return self.colorspace


class FakeLayer:
    """Sdf layer exposing attributes and optional time samples."""

    def __init__(self, identifier: Path) -> None:
        self.identifier = str(identifier)
        self.realPath = str(identifier)
        self.specs = {}
        self.samples = {}

    def add_asset(
        self,
        path: str,
        default=None,
        *,
        type_name: str = "asset",
        colorspace: str = "",
        samples: dict[float, object] | None = None,
    ) -> FakeSpec:
        property_path = FakePropertyPath(path)
        spec = FakeSpec(
            property_path,
            self,
            type_name=type_name,
            default=default,
            colorspace=colorspace,
        )
        self.specs[path] = (property_path, spec)
        self.samples[path] = dict(samples or {})
        return spec

    def Traverse(self, _root, callback) -> None:
        for property_path, _spec in self.specs.values():
            callback(property_path)

    def GetAttributeAtPath(self, path):
        entry = self.specs.get(str(path))
        return entry[1] if entry else None

    def ListTimeSamplesForPath(self, path):
        return sorted(self.samples.get(str(path), {}))

    def QueryTimeSample(self, path, time_code):
        return self.samples[str(path)][time_code]


class FakeStage:
    """Source stage exposing its contributing layer stack."""

    def __init__(self, layers) -> None:
        self.layers = list(layers)

    def GetLayerStack(self):
        return list(self.layers)


def _load_resources(monkeypatch):
    """Load resource planner with Sdf relative-path resolution stubbed."""
    sdf = types.ModuleType("pxr.Sdf")

    def resolve(layer, authored: str) -> str:
        return os.path.normpath(str(Path(layer.identifier).parent / authored))

    sdf.ComputeAssetPathRelativeToLayer = resolve
    pxr = types.ModuleType("pxr")
    pxr.Sdf = sdf
    monkeypatch.setitem(sys.modules, "pxr", pxr)
    monkeypatch.setitem(sys.modules, "pxr.Sdf", sdf)

    path = ROOT / "client" / "ayon_katana" / "api" / "usd_resources.py"
    spec = importlib.util.spec_from_file_location(
        "ayon_katana_usd_resources_test", path
    )
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_static_resource_preserves_colorspace_and_plans_transfer(
    monkeypatch,
    tmp_path: Path,
) -> None:
    """A local texture produces AYON Core-compatible resource plan fields."""
    module = _load_resources(monkeypatch)
    texture = tmp_path / "textures" / "hero diffuse.exr"
    texture.parent.mkdir()
    texture.write_bytes(b"texture")
    layer = FakeLayer(tmp_path / "staging" / "look.usda")
    layer.add_asset(
        "/Looks/Mat.inputs:file",
        FakeAsset(str(texture)),
        colorspace="ACEScg",
    )
    before = texture.read_bytes()

    plan = module.plan_look_resources(layer, tmp_path / "publish" / "resources", None)

    assert plan["resources"] == [
        {
            "attribute": "/Looks/Mat.inputs:file",
            "source": str(texture).replace("\\", "/"),
            "files": [os.path.normpath(str(texture))],
            "color_space": "ACEScg",
        }
    ]
    assert plan["assetRemap"][os.path.normpath(str(texture).replace("\\", "/"))] == (
        "./resources/hero diffuse.exr"
    )
    assert plan["transfers"] == [
        (
            os.path.normpath(str(texture)),
            str(tmp_path / "publish" / "resources" / "hero diffuse.exr"),
        )
    ]
    assert texture.read_bytes() == before
    assert not (tmp_path / "publish").exists()


def test_relative_udim_uses_original_source_stage_anchor(
    monkeypatch,
    tmp_path: Path,
) -> None:
    """Staging cannot re-anchor a relative UDIM away from its source layer."""
    module = _load_resources(monkeypatch)
    source_dir = tmp_path / "source"
    source_dir.mkdir()
    texture_dir = source_dir / "textures"
    texture_dir.mkdir()
    tile_1001 = texture_dir / "body.1001.exr"
    tile_1002 = texture_dir / "body.1002.exr"
    tile_1001.write_bytes(b"1001")
    tile_1002.write_bytes(b"1002")
    authored = "textures/body.<UDIM>.exr"

    source_layer = FakeLayer(source_dir / "look_source.usda")
    source_layer.add_asset("/Looks/Body.inputs:file", FakeAsset(authored))
    exported_layer = FakeLayer(tmp_path / "staging" / "look.usda")
    exported_layer.add_asset("/Looks/Body.inputs:file", FakeAsset(authored))

    plan = module.plan_look_resources(
        exported_layer,
        tmp_path / "publish" / "resources",
        FakeStage([source_layer]),
    )

    resource = plan["resources"][0]
    assert resource["source"] == authored
    assert resource["files"] == [
        os.path.normpath(str(tile_1001)),
        os.path.normpath(str(tile_1002)),
    ]
    assert plan["assetRemap"][os.path.normpath(authored)] == (
        "./resources/body.<UDIM>.exr"
    )
    assert len(plan["transfers"]) == 2


def test_asset_arrays_and_time_samples_are_all_planned(
    monkeypatch,
    tmp_path: Path,
) -> None:
    """Asset arrays plus authored time samples contribute every local texture."""
    module = _load_resources(monkeypatch)
    textures = []
    for name in ("a.exr", "b.exr", "c.exr"):
        path = tmp_path / name
        path.write_bytes(name.encode("utf-8"))
        textures.append(path)
    layer = FakeLayer(tmp_path / "look.usda")
    layer.add_asset(
        "/Looks/Array.inputs:files",
        [FakeAsset(str(textures[0])), FakeAsset(str(textures[1]))],
        type_name="asset[]",
        samples={1.0: [FakeAsset(str(textures[2]))]},
    )

    plan = module.plan_look_resources(layer, tmp_path / "resources", None)

    assert {item["source"] for item in plan["resources"]} == {
        str(path).replace("\\", "/") for path in textures
    }
    assert len(plan["transfers"]) == 3


def test_duplicate_resolved_files_transfer_once(monkeypatch, tmp_path: Path) -> None:
    """Multiple authored attributes using one file do not duplicate transfers."""
    module = _load_resources(monkeypatch)
    texture = tmp_path / "shared.exr"
    texture.write_bytes(b"shared")
    layer = FakeLayer(tmp_path / "look.usda")
    layer.add_asset("/Looks/A.inputs:file", FakeAsset(str(texture)))
    layer.add_asset("/Looks/B.inputs:file", FakeAsset(str(texture)))

    plan = module.plan_look_resources(layer, tmp_path / "resources", None)

    assert len(plan["resources"]) == 2
    assert len(plan["transfers"]) == 1


def test_ambiguous_relative_source_anchor_is_rejected(
    monkeypatch,
    tmp_path: Path,
) -> None:
    """The same authored relative value from two source layers is never guessed."""
    module = _load_resources(monkeypatch)
    authored = "textures/diffuse.exr"
    source_layers = []
    for folder_name, payload in (("a", b"a"), ("b", b"b")):
        folder = tmp_path / folder_name
        (folder / "textures").mkdir(parents=True)
        (folder / "textures" / "diffuse.exr").write_bytes(payload)
        layer = FakeLayer(folder / "look.usda")
        layer.add_asset("/Looks/Mat.inputs:file", FakeAsset(authored))
        source_layers.append(layer)
    exported = FakeLayer(tmp_path / "staging" / "look.usda")
    exported.add_asset("/Looks/Mat.inputs:file", FakeAsset(authored))

    with pytest.raises(ValueError, match="ambiguous"):
        module.plan_look_resources(
            exported,
            tmp_path / "resources",
            FakeStage(source_layers),
        )


def test_destination_basename_collision_is_rejected(
    monkeypatch,
    tmp_path: Path,
) -> None:
    """Different files cannot silently overwrite the same resources basename."""
    module = _load_resources(monkeypatch)
    first = tmp_path / "a" / "diffuse.exr"
    second = tmp_path / "b" / "diffuse.exr"
    first.parent.mkdir()
    second.parent.mkdir()
    first.write_bytes(b"a")
    second.write_bytes(b"b")
    layer = FakeLayer(tmp_path / "look.usda")
    layer.add_asset("/Looks/A.inputs:file", FakeAsset(str(first)))
    layer.add_asset("/Looks/B.inputs:file", FakeAsset(str(second)))

    with pytest.raises(ValueError, match="basename collision"):
        module.plan_look_resources(layer, tmp_path / "resources", None)


def test_missing_and_remote_resources_fail_but_composition_assets_are_excluded(
    monkeypatch,
    tmp_path: Path,
) -> None:
    """Missing/remote textures fail while USD/Alembic composition paths are ignored."""
    module = _load_resources(monkeypatch)
    missing_layer = FakeLayer(tmp_path / "missing.usda")
    missing_layer.add_asset(
        "/Looks/Mat.inputs:file",
        FakeAsset(str(tmp_path / "missing.exr")),
    )
    with pytest.raises(ValueError, match="does not resolve to local files"):
        module.plan_look_resources(missing_layer, tmp_path / "resources", None)

    remote_layer = FakeLayer(tmp_path / "remote.usda")
    remote_layer.add_asset(
        "/Looks/Mat.inputs:file",
        FakeAsset("https://example.invalid/texture.exr"),
    )
    with pytest.raises(ValueError, match="unsupported remote URI"):
        module.plan_look_resources(remote_layer, tmp_path / "resources", None)

    composition_layer = FakeLayer(tmp_path / "composition.usda")
    composition_layer.add_asset("/Asset.references", FakeAsset("model.usd"))
    composition_layer.add_asset("/Asset.cache", FakeAsset("cache.abc"))
    assert module.plan_look_resources(
        composition_layer,
        tmp_path / "resources",
        None,
    ) == {"resources": [], "assetRemap": {}, "transfers": []}
