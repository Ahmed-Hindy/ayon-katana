"""Tests for Katana's narrow Scene Inventory selection actions."""

from __future__ import annotations

import importlib.util
import sys
import types
from pathlib import Path

ROOT = Path(__file__).parents[1]


class _Node:
    """Minimal node double identified by a readable label."""

    def __init__(self, label: str) -> None:
        self.label = label


def _load_module(monkeypatch, module_name: str, module_path: Path):
    """Load a module under a controlled package-qualified name."""
    module_spec = importlib.util.spec_from_file_location(module_name, module_path)
    assert module_spec is not None
    assert module_spec.loader is not None
    module = importlib.util.module_from_spec(module_spec)
    monkeypatch.setitem(sys.modules, module_name, module)
    module_spec.loader.exec_module(module)
    return module


def _load_action_module(monkeypatch, filename, node_map, managed_nodes, selections):
    """Load one inventory action with its Core and Katana dependencies stubbed."""

    class InventoryAction:
        """Minimal Core action base class."""

    pipeline_core = types.ModuleType("ayon_core.pipeline")
    pipeline_core.InventoryAction = InventoryAction
    monkeypatch.setitem(sys.modules, "ayon_core", types.ModuleType("ayon_core"))
    monkeypatch.setitem(sys.modules, "ayon_core.pipeline", pipeline_core)

    package_module = types.ModuleType("ayon_katana")
    package_module.__path__ = []
    api_package = types.ModuleType("ayon_katana.api")
    api_package.__path__ = []
    compat_module = types.ModuleType("ayon_katana.api.compat")
    compat_module.get_node = node_map.get
    compat_module.set_selected_nodes = lambda nodes: selections.append(list(nodes))
    containers_module = types.ModuleType("ayon_katana.api.containers")
    containers_module.SOURCE_ROLE = "source"
    containers_module.find_managed_node = lambda node, role: managed_nodes.get(
        (node, role)
    )
    for module_name, module in (
        ("ayon_katana", package_module),
        ("ayon_katana.api", api_package),
        ("ayon_katana.api.compat", compat_module),
        ("ayon_katana.api.containers", containers_module),
    ):
        monkeypatch.setitem(sys.modules, module_name, module)

    return _load_module(
        monkeypatch,
        f"ayon_katana.plugins.inventory.{filename.stem}",
        filename,
    )


def test_select_in_node_graph_resolves_node_names_and_ignores_missing(monkeypatch):
    """Container selection should target only live Katana container nodes."""
    first_node = _Node("first")
    second_node = _Node("second")
    selections = []
    module = _load_action_module(
        monkeypatch,
        ROOT
        / "client"
        / "ayon_katana"
        / "plugins"
        / "inventory"
        / "select_containers.py",
        {"second": second_node},
        {},
        selections,
    )

    action = module.SelectInScene()
    action.process(
        [
            {"node": first_node},
            {"objectName": "second"},
            {"objectName": "missing"},
        ]
    )

    assert action.is_compatible({"objectName": "second"}) is True
    assert action.is_compatible({"objectName": "missing"}) is False
    assert selections == [[first_node, second_node]]


def test_select_managed_sources_uses_loader_owned_nodes_only(monkeypatch):
    """Managed-source selection must not infer arbitrary artist-owned nodes."""
    container_node = _Node("container")
    source_node = _Node("source")
    selections = []
    module = _load_action_module(
        monkeypatch,
        ROOT
        / "client"
        / "ayon_katana"
        / "plugins"
        / "inventory"
        / "select_managed_sources.py",
        {"container": container_node},
        {(container_node, "source"): source_node},
        selections,
    )

    action = module.SelectManagedSources()
    action.process([{"objectName": "container"}, {"objectName": "missing"}])

    assert action.is_compatible({"objectName": "container"}) is True
    assert action.is_compatible({"objectName": "missing"}) is False
    assert selections == [[source_node]]
