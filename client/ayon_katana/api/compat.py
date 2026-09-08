"""Shared Katana host API helpers."""

from __future__ import annotations

from Katana import KatanaFile, NodegraphAPI


def iter_nodes(parent_node=None):
    """Yield all Katana nodes recursively."""
    parent_node = parent_node or NodegraphAPI.GetRootNode()
    get_children = getattr(parent_node, "getChildren", None)
    if get_children is None:
        return

    for child in get_children() or []:
        yield child
        yield from iter_nodes(child)


def is_descendant(node, parent_node):
    """Return whether a node is nested below another Katana node."""
    get_parent = getattr(node, "getParent", None)
    if get_parent is None:
        return False

    current_node = get_parent()
    while current_node is not None:
        if current_node is parent_node:
            return True
        current_node = current_node.getParent()
    return False


def get_output_ports(node):
    """Return all native output ports exposed by a Katana node."""
    get_ports = getattr(node, "getOutputPorts", None)
    return list(get_ports() or []) if get_ports is not None else []


def get_node(node_name: str):
    """Return a Katana node by its globally unique name."""
    return NodegraphAPI.GetNode(node_name)


def import_katana_file(
    filepath: str,
    parent_node=None,
    float_nodes: bool = False,
) -> list:
    """Import a Katana file and return all imported nodes."""
    existing_nodes = set(iter_nodes())
    result = KatanaFile.Import(
        filepath,
        floatNodes=float_nodes,
        parentNode=parent_node,
    )
    imported_nodes = list(result or [])
    if imported_nodes:
        return imported_nodes
    return list(set(iter_nodes()) - existing_nodes)


def set_parent(node, parent_node) -> None:
    """Move a node below a Group."""
    node.setParent(parent_node)


def get_selected_nodes() -> list:
    """Return selected Katana nodes."""
    return list(NodegraphAPI.GetAllSelectedNodes())


def set_selected_nodes(nodes: list) -> None:
    """Replace the Katana node selection."""
    NodegraphAPI.SetAllSelectedNodes(nodes)
