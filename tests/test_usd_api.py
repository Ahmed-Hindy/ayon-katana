"""Tests for AYON entity URI and optional USD resolver integration."""

from __future__ import annotations

import importlib.util
import sys
import types
from pathlib import Path

ROOT = Path(__file__).parents[1]


def _load_usd_module(monkeypatch, response=None):
    """Load USD helpers with a controlled AYON API response."""
    ayon_api = types.ModuleType("ayon_api")
    ayon_api.post = lambda *_args, **_kwargs: response
    monkeypatch.setitem(sys.modules, "ayon_api", ayon_api)
    path = ROOT / "client" / "ayon_katana" / "api" / "usd.py"
    spec = importlib.util.spec_from_file_location("ayon_katana_usd_api_test", path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_usd_product_types_share_one_host_api_contract(monkeypatch) -> None:
    """USD loaders use the semantic product vocabulary from one module."""
    module = _load_usd_module(monkeypatch)

    assert {
        "assembly",
        "camera",
        "layout",
        "look",
        "usd",
        "usdCamera",
    } == module.USD_PRODUCT_BASE_TYPES


def test_entity_uri_uses_server_canonical_representation_uri(monkeypatch) -> None:
    """The loader uses the server URI instead of rebuilding an approximation."""
    response = types.SimpleNamespace(
        status_code=200,
        text="",
        data={
            "uris": [
                {
                    "uri": (
                        "ayon://Project/assets/hero?product=modelMain"
                        "&version=3&representation=usd"
                    )
                }
            ]
        },
    )
    module = _load_usd_module(monkeypatch, response)

    result = module.get_ayon_entity_uri_from_representation_context(
        {
            "project": {"name": "Project"},
            "representation": {"id": "representation-id"},
        }
    )

    assert result == response.data["uris"][0]["uri"]


def test_missing_optional_resolver_warns_and_does_nothing(monkeypatch, caplog) -> None:
    """Cache clearing remains safe when usdAssetResolver is not installed."""
    module = _load_usd_module(monkeypatch)
    monkeypatch.setitem(sys.modules, "usdAssetResolver", None)

    result = module.clear_resolver_cache()

    assert result == {
        "resolver_available": False,
        "cache_cleared": False,
        "flushed_nodes": 0,
    }
    assert "not installed" in caplog.text


def test_resolver_clear_flushes_native_usdin_stages(monkeypatch) -> None:
    """A present resolver clears once and flushes each healthy UsdIn stage."""
    module = _load_usd_module(monkeypatch)
    clear_calls = []

    class ResolverContext:
        """Record resolver cache clears."""

        def ClearCache(self) -> None:
            clear_calls.append(True)

    resolver_module = types.ModuleType("usdAssetResolver")
    resolver_module.AyonUsdResolver = types.SimpleNamespace(
        ResolverContext=ResolverContext
    )
    monkeypatch.setitem(sys.modules, "usdAssetResolver", resolver_module)

    class Node:
        """Record native stage flush calls."""

        def __init__(self, name: str, fail: bool = False) -> None:
            self.name = name
            self.fail = fail
            self.calls = []

        def getName(self) -> str:
            return self.name

        def flushStage(self, downstream, graph_state) -> None:
            if self.fail:
                raise RuntimeError("flush failed")
            self.calls.append((downstream, graph_state))

    healthy = Node("HealthyUsdIn")
    failing = Node("FailingUsdIn", fail=True)
    graph_state = object()
    nodegraph = types.SimpleNamespace(
        GetCurrentGraphState=lambda: graph_state,
        GetAllNodesByType=lambda node_type: (
            [healthy, failing] if node_type == "UsdIn" else []
        ),
    )
    katana_module = types.ModuleType("Katana")
    katana_module.NodegraphAPI = nodegraph
    monkeypatch.setitem(sys.modules, "Katana", katana_module)

    result = module.clear_resolver_cache()

    assert clear_calls == [True]
    assert healthy.calls == [(healthy, graph_state)]
    assert result == {
        "resolver_available": True,
        "cache_cleared": True,
        "flushed_nodes": 1,
    }
