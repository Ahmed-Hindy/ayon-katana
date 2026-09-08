"""Tests for shared Katana loader path behavior."""

from __future__ import annotations

import importlib.util
import sys
import types
from pathlib import Path

ROOT = Path(__file__).parents[1]


def _load_plugin_module(monkeypatch):
    """Load the Katana plugin bases with compact Core and host substitutes."""
    pyblish_api = types.ModuleType("pyblish.api")
    pyblish_api.InstancePlugin = type("InstancePlugin", (), {})
    pyblish_api.ContextPlugin = type("ContextPlugin", (), {})
    pyblish_module = types.ModuleType("pyblish")
    pyblish_module.api = pyblish_api
    monkeypatch.setitem(sys.modules, "pyblish", pyblish_module)
    monkeypatch.setitem(sys.modules, "pyblish.api", pyblish_api)

    class LoaderPlugin(list):
        """Return the path supplied by the test representation context."""

        @classmethod
        def filepath_from_context(cls, context):
            return context["test_filepath"]

    pipeline = types.ModuleType("ayon_core.pipeline")
    pipeline.CreatedInstance = type("CreatedInstance", (), {})
    pipeline.Creator = type("Creator", (), {})
    pipeline.CreatorError = RuntimeError
    pipeline.load = types.SimpleNamespace(LoaderPlugin=LoaderPlugin)
    pipeline.publish = types.SimpleNamespace(Extractor=type("Extractor", (), {}))
    monkeypatch.setitem(sys.modules, "ayon_core", types.ModuleType("ayon_core"))
    monkeypatch.setitem(sys.modules, "ayon_core.pipeline", pipeline)

    katana = types.ModuleType("Katana")
    katana.NodegraphAPI = types.SimpleNamespace()
    monkeypatch.setitem(sys.modules, "Katana", katana)

    package = types.ModuleType("ayon_katana")
    package.__path__ = []
    api_package = types.ModuleType("ayon_katana.api")
    api_package.__path__ = []
    instances = types.ModuleType("ayon_katana.api.instances")
    usd = types.ModuleType("ayon_katana.api.usd")
    usd.get_ayon_entity_uri_from_representation_context = lambda context: context[
        "test_entity_uri"
    ]
    monkeypatch.setitem(sys.modules, "ayon_katana", package)
    monkeypatch.setitem(sys.modules, "ayon_katana.api", api_package)
    monkeypatch.setitem(sys.modules, "ayon_katana.api.instances", instances)
    monkeypatch.setitem(sys.modules, "ayon_katana.api.usd", usd)

    path = ROOT / "client" / "ayon_katana" / "api" / "plugin.py"
    spec = importlib.util.spec_from_file_location("ayon_katana.api.plugin", path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    monkeypatch.setitem(sys.modules, spec.name, module)
    spec.loader.exec_module(module)
    return module


def test_loader_paths_remain_filesystem_paths_by_default(monkeypatch) -> None:
    """Non-USD loaders preserve normalized filesystem behavior."""
    module = _load_plugin_module(monkeypatch)

    result = module.KatanaLoader.filepath_from_context(
        {"test_filepath": r"C:\project\asset.usd"}
    )

    assert result == "C:/project/asset.usd"


def test_loader_can_preserve_canonical_ayon_entity_uri(monkeypatch) -> None:
    """Settings-enabled USD loaders bypass filesystem normalization."""
    module = _load_plugin_module(monkeypatch)

    class EntityUriLoader(module.KatanaLoader):
        use_ayon_entity_uri = True

    uri = "ayon://Project/assets/hero?product=model&version=1&representation=usd"
    result = EntityUriLoader.filepath_from_context(
        {
            "test_filepath": r"C:\project\asset.usd",
            "test_entity_uri": uri,
        }
    )

    assert result == uri
