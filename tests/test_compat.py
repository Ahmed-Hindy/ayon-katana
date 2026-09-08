"""Tests for shared Katana API helpers."""

from __future__ import annotations

import importlib.util
import sys
import types
from pathlib import Path


def _load_compat_module(root_node, monkeypatch, katana_file=None, nodes=None):
    """Load the Katana API helpers with a minimal fake host."""
    node_map = nodes or {}
    katana_module = types.ModuleType("Katana")
    katana_module.KatanaFile = katana_file or types.SimpleNamespace()
    katana_module.NodegraphAPI = types.SimpleNamespace(
        GetRootNode=lambda: root_node,
        GetNode=node_map.get,
        GetAllSelectedNodes=lambda: [],
        SetAllSelectedNodes=lambda _nodes: None,
    )
    monkeypatch.setitem(sys.modules, "Katana", katana_module)

    module_path = (
        Path(__file__).parents[1] / "client" / "ayon_katana" / "api" / "compat.py"
    )
    module_spec = importlib.util.spec_from_file_location(
        "ayon_katana_compat_test",
        module_path,
    )
    assert module_spec is not None
    assert module_spec.loader is not None
    module = importlib.util.module_from_spec(module_spec)
    module_spec.loader.exec_module(module)
    return module


def test_iter_nodes_traverses_nested_groups(monkeypatch) -> None:
    """Recursive traversal should preserve Katana child order."""

    class Node:
        def __init__(self, children=None):
            self.children = children or []

        def getChildren(self):
            return self.children

    first_leaf = Node()
    second_leaf = Node()
    nested_group = Node([second_leaf])
    root_node = Node([first_leaf, nested_group])
    compat = _load_compat_module(root_node, monkeypatch)

    assert list(compat.iter_nodes()) == [first_leaf, nested_group, second_leaf]


def test_iter_nodes_stops_at_leaf_without_children_api(monkeypatch) -> None:
    """Leaf Katana nodes without ``getChildren`` terminate traversal."""

    class Group:
        def __init__(self, children=None):
            self.children = children or []

        def getChildren(self):
            return self.children

    leaf = object()
    root_node = Group([leaf])
    compat = _load_compat_module(root_node, monkeypatch)

    assert list(compat.iter_nodes()) == [leaf]


def test_is_descendant_walks_parent_chain(monkeypatch) -> None:
    """Hierarchy checks should not require child traversal APIs."""

    class Node:
        def __init__(self, parent=None):
            self.parent = parent

        def getParent(self):
            return self.parent

    root_node = Node()
    parent_node = Node(root_node)
    leaf_node = Node(parent_node)
    outside_node = Node(root_node)
    compat = _load_compat_module(root_node, monkeypatch)

    assert compat.is_descendant(leaf_node, parent_node)
    assert compat.is_descendant(leaf_node, root_node)
    assert not compat.is_descendant(leaf_node, outside_node)
    assert not compat.is_descendant(object(), root_node)


def test_get_output_ports_supports_arbitrary_port_names(monkeypatch) -> None:
    """Output discovery should not assume Katana names every port ``out``."""

    custom_port = object()

    class Node:
        def getOutputPorts(self):
            return [custom_port]

    compat = _load_compat_module(Node(), monkeypatch)

    assert compat.get_output_ports(Node()) == [custom_port]
    assert compat.get_output_ports(object()) == []


def test_import_returns_nodes_when_katana_returns_none(monkeypatch) -> None:
    """Imported nodes should be detected when Katana returns no node list."""

    class Node:
        def __init__(self, children=None):
            self.children = children or []

        def getChildren(self):
            return self.children

    imported_node = Node()
    root_node = Node()

    def import_file(filepath, floatNodes=False, parentNode=None):
        assert filepath == "template.katana"
        assert not floatNodes
        assert parentNode is root_node
        root_node.children.append(imported_node)
        return None

    katana_file = types.SimpleNamespace(Import=import_file)
    compat = _load_compat_module(root_node, monkeypatch, katana_file=katana_file)

    assert compat.import_katana_file(
        "template.katana",
        parent_node=root_node,
    ) == [imported_node]
