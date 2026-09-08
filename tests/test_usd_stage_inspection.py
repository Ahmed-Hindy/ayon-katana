"""Focused contracts for Katana native USD stage and layer inspection."""

from __future__ import annotations

import importlib.util
import sys
import types
from pathlib import Path

import pytest

ROOT = Path(__file__).parents[1]


class FakeNode:
    """Small Katana node stand-in with a configurable native USD flavor."""

    def __init__(self, name: str = "UsdSource", node_type: str = "UsdIn") -> None:
        self._name = name
        self._type = node_type

    def getName(self) -> str:
        """Return the node name."""
        return self._name

    def getType(self) -> str:
        """Return the node type."""
        return self._type


class FakeStageHandle:
    """Katana NodesUsdAPI stage handle stand-in."""

    def __init__(self, stage) -> None:
        self._stage = stage

    def getUsdStage(self):
        """Return the configured host-owned stage object."""
        return self._stage


def _load_usd_api(monkeypatch, *, stage_handle=None):
    """Load Katana USD helpers with a controlled host API."""
    ayon_api = types.ModuleType("ayon_api")
    ayon_api.post = lambda *_args, **_kwargs: None
    monkeypatch.setitem(sys.modules, "ayon_api", ayon_api)

    katana = types.ModuleType("Katana")
    katana.NodegraphAPI = types.SimpleNamespace(
        GetNodeFlavors=lambda node_type: (
            ["nativeusd"] if node_type.startswith("Usd") else ["3d"]
        )
    )
    katana.NodesUsdAPI = types.SimpleNamespace(
        GetStage=lambda _node: stage_handle,
    )
    monkeypatch.setitem(sys.modules, "Katana", katana)

    name = "ayon_katana.api.usd_stage_inspection_test"
    path = ROOT / "client" / "ayon_katana" / "api" / "usd.py"
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    monkeypatch.setitem(sys.modules, name, module)
    spec.loader.exec_module(module)
    return module


def test_get_composed_usd_stage_returns_host_owned_stage(monkeypatch) -> None:
    """Native USD inspection returns the exact stage owned by Katana."""
    stage = object()
    usd = _load_usd_api(monkeypatch, stage_handle=FakeStageHandle(stage))

    assert usd.get_composed_usd_stage(FakeNode()) is stage


def test_get_composed_usd_stage_rejects_missing_or_non_native_node(monkeypatch) -> None:
    """Invalid sources fail before attempting host stage composition."""
    usd = _load_usd_api(monkeypatch, stage_handle=FakeStageHandle(object()))

    with pytest.raises(ValueError, match="source node is required"):
        usd.get_composed_usd_stage(None)

    with pytest.raises(ValueError, match="not a native USD node"):
        usd.get_composed_usd_stage(FakeNode(node_type="Group"))


@pytest.mark.parametrize(
    ("stage_handle", "message"),
    [
        (None, "no USD stage handle"),
        (FakeStageHandle(None), "no composed USD stage"),
    ],
)
def test_get_composed_usd_stage_rejects_invalid_host_stage(
    monkeypatch,
    stage_handle,
    message: str,
) -> None:
    """Missing Katana stage handles and composed stages are actionable errors."""
    usd = _load_usd_api(monkeypatch, stage_handle=stage_handle)

    with pytest.raises(RuntimeError, match=message):
        usd.get_composed_usd_stage(FakeNode())


@pytest.mark.parametrize("files", ["look.usd", ["look.usd"]])
def test_get_extracted_usd_layer_path_accepts_single_file_forms(
    monkeypatch,
    tmp_path: Path,
    files,
) -> None:
    """String and one-item file lists resolve to the same staged layer."""
    usd = _load_usd_api(monkeypatch)
    data = {
        "representations": [
            {
                "ext": "usd",
                "files": files,
                "stagingDir": str(tmp_path),
            }
        ]
    }

    assert usd.get_extracted_usd_layer_path(data) == tmp_path / "look.usd"


def test_get_extracted_usd_layer_path_uses_instance_staging_dir(
    monkeypatch,
    tmp_path: Path,
) -> None:
    """Instance staging remains the fallback for existing extractor metadata."""
    usd = _load_usd_api(monkeypatch)
    data = {
        "stagingDir": str(tmp_path),
        "representations": [{"ext": ".usda", "files": "look.usda"}],
    }

    assert usd.get_extracted_usd_layer_path(data) == tmp_path / "look.usda"


@pytest.mark.parametrize(
    ("data", "message"),
    [
        ({}, "No extracted USD representation"),
        (
            {
                "representations": [
                    {"ext": "usd", "files": "a.usd", "stagingDir": "stage"},
                    {"ext": "usdc", "files": "b.usdc", "stagingDir": "stage"},
                ]
            },
            "exactly one extracted USD representation",
        ),
        (
            {
                "representations": [
                    {"ext": "usd", "files": ["a.usd", "b.usd"], "stagingDir": "stage"}
                ]
            },
            "exactly one extracted USD layer file",
        ),
        (
            {"representations": [{"ext": "usd", "files": "look.usd"}]},
            "no staging directory",
        ),
    ],
)
def test_get_extracted_usd_layer_path_rejects_ambiguous_metadata(
    monkeypatch,
    data: dict,
    message: str,
) -> None:
    """Missing or ambiguous representation metadata cannot pick a layer silently."""
    usd = _load_usd_api(monkeypatch)

    with pytest.raises(ValueError, match=message):
        usd.get_extracted_usd_layer_path(data)
