"""Deterministic Pyblish actions for Katana render validation failures."""

from __future__ import annotations

from collections.abc import Iterable

import pyblish.api
from ayon_core.pipeline.publish import get_errored_instances_from_context

from ayon_katana.api import compat, render

_RENDER_CREATOR_IDENTIFIER = "io.ayon.creators.katana.render"


def _node_from_instance(instance):
    """Return the outer Katana node stored on a publish instance."""
    node_reference = instance.data.get("instance_node")
    if node_reference is None:
        return None
    if hasattr(node_reference, "getName"):
        return node_reference
    return compat.get_node(str(node_reference))


def _unique_nodes(nodes: Iterable) -> list:
    """Return live nodes once, preserving their incoming order."""
    unique_nodes = []
    seen = set()
    for node in nodes:
        if node is None:
            continue
        try:
            key = node.getName()
        except Exception:
            key = id(node)
        if key in seen:
            continue
        seen.add(key)
        unique_nodes.append(node)
    return unique_nodes


def _invalid_nodes_for_context_plugin(context, plugin, method_name: str) -> list:
    """Get invalid nodes from a context validator when it exposes them."""
    if not issubclass(plugin, pyblish.api.ContextPlugin):
        return []
    getter = getattr(plugin, method_name, None)
    if not callable(getter):
        return []
    return _unique_nodes(getter(context) or [])


def _invalid_output_nodes(context, plugin) -> list:
    """Return invalid output nodes exposed by a failed validator."""
    if issubclass(plugin, pyblish.api.ContextPlugin):
        return _invalid_nodes_for_context_plugin(
            context,
            plugin,
            "get_invalid_output_nodes",
        )

    getter = getattr(plugin, "get_invalid", None)
    if not callable(getter):
        return []

    nodes = []
    for instance in get_errored_instances_from_context(context, plugin=plugin):
        nodes.extend(getter(instance) or [])
    return _unique_nodes(nodes)


def _invalid_instances(context, plugin) -> list:
    """Return failed instances, including context-validator invalid instances."""
    if not issubclass(plugin, pyblish.api.ContextPlugin):
        return list(get_errored_instances_from_context(context, plugin=plugin))

    invalid_nodes = _invalid_nodes_for_context_plugin(
        context,
        plugin,
        "get_invalid",
    )
    invalid_keys = {
        _node_key(node) for node in invalid_nodes if _node_key(node) is not None
    }
    if not invalid_keys:
        return []
    return [
        instance
        for instance in context
        if _node_key(_node_from_instance(instance)) in invalid_keys
    ]


def _node_key(node):
    """Return a stable node identity suitable for a local selection operation."""
    if node is None:
        return None
    try:
        return node.getName()
    except Exception:
        return id(node)


class SelectInvalidInstanceNodes(pyblish.api.Action):
    """Select outer AYON instance nodes from a failed validator."""

    label = "Select invalid instance nodes"
    icon = "search"
    on = "failed"

    def process(self, context, plugin) -> None:
        """Replace the Katana selection with invalid outer instance nodes."""
        nodes = _invalid_nodes_for_context_plugin(context, plugin, "get_invalid")
        if not nodes:
            nodes = [
                _node_from_instance(instance)
                for instance in _invalid_instances(context, plugin)
            ]
            nodes = _unique_nodes(nodes)
        if nodes:
            compat.set_selected_nodes(nodes)


class SelectInvalidOutputNodes(pyblish.api.Action):
    """Select concrete Katana output nodes from a failed context validator."""

    label = "Select invalid render outputs"
    icon = "search"
    on = "failed"

    def process(self, context, plugin) -> None:
        """Replace the Katana selection with invalid output nodes."""
        nodes = _invalid_output_nodes(context, plugin)
        if nodes:
            compat.set_selected_nodes(nodes)


class ReconnectAYONRenderGraphAction(pyblish.api.Action):
    """Reconnect failed render graphs created by the AYON Katana creator."""

    label = "Reconnect AYON render graph"
    icon = "refresh"
    on = "failed"

    def process(self, context, plugin) -> None:
        """Reconnect only failed instances explicitly created by AYON."""
        reconnected_nodes = []
        for instance in _invalid_instances(context, plugin):
            if instance.data.get("creator_identifier") != _RENDER_CREATOR_IDENTIFIER:
                continue
            instance_node = _node_from_instance(instance)
            if instance_node is None:
                continue
            render.reconnect_render_graph(instance_node)
            reconnected_nodes.append(instance_node)

        if reconnected_nodes:
            compat.set_selected_nodes(_unique_nodes(reconnected_nodes))
