"""Tests for the administrator-authored Workfile Builder script placeholder."""

from __future__ import annotations

import functools
import importlib.util
import sys
import types
from pathlib import Path

ROOT = Path(__file__).parents[1]


class FakeDefinition:
    """Capture a Core creator attribute definition."""

    def __init__(self, key, **kwargs) -> None:
        self.key = key
        self.kwargs = kwargs


class FakePlaceholderItem:
    """Small Core placeholder item substitute."""

    def __init__(self, scene_identifier, data, plugin) -> None:
        self.scene_identifier = scene_identifier
        self.data = data
        self.plugin = plugin
        self.order = data.get("order", 0)


class FakeNode:
    """Node carrying Workfile Builder metadata."""

    def __init__(self, name: str, data: dict) -> None:
        self._name = name
        self.data = data

    def getName(self) -> str:
        """Return the stable Katana node name."""
        return self._name


class FakeBuilder:
    """Record Core depth and finish callbacks."""

    def __init__(self) -> None:
        self.depth_callbacks = []
        self.finished_callbacks = []

    def add_on_depth_processed_callback(self, callback, order=0) -> None:
        """Record a depth callback and order."""
        self.depth_callbacks.append((order, callback))

    def add_on_finished_callback(self, callback, order=0) -> None:
        """Record a finished callback and order."""
        self.finished_callbacks.append((order, callback))


def _load_script_placeholder(monkeypatch):
    """Load the plugin with compact AYON and Katana substitutes."""
    core_lib = types.ModuleType("ayon_core.lib")
    core_lib.NumberDef = FakeDefinition
    core_lib.TextDef = FakeDefinition
    events_module = types.ModuleType("ayon_core.lib.events")
    events_module.weakref_partial = functools.partial
    builder_module = types.ModuleType(
        "ayon_core.pipeline.workfile.workfile_template_builder"
    )
    builder_module.PlaceholderItem = FakePlaceholderItem
    monkeypatch.setitem(sys.modules, "ayon_core", types.ModuleType("ayon_core"))
    monkeypatch.setitem(sys.modules, "ayon_core.lib", core_lib)
    monkeypatch.setitem(sys.modules, "ayon_core.lib.events", events_module)
    monkeypatch.setitem(sys.modules, "ayon_core.pipeline", types.ModuleType("pipeline"))
    monkeypatch.setitem(
        sys.modules,
        "ayon_core.pipeline.workfile",
        types.ModuleType("ayon_core.pipeline.workfile"),
    )
    monkeypatch.setitem(
        sys.modules,
        "ayon_core.pipeline.workfile.workfile_template_builder",
        builder_module,
    )

    nodegraph = types.SimpleNamespace(GetNode=lambda name: f"node:{name}")
    katana_module = types.ModuleType("Katana")
    katana_module.NodegraphAPI = nodegraph
    monkeypatch.setitem(sys.modules, "Katana", katana_module)

    class PlaceholderBase:
        """Provide the Katana placeholder methods used by the script plugin."""

        nodes = []
        log = types.SimpleNamespace(debug=lambda *_args: None)

        def __init__(self) -> None:
            self.builder = FakeBuilder()
            self.deleted = []
            self.prepared = []

        def collect_scene_placeholders(self):
            """Return configured fake nodes."""
            return self.nodes

        @staticmethod
        def _read(node):
            """Return copied node metadata."""
            return dict(node.data)

        def prepare_placeholders(self, placeholders) -> None:
            """Record Core base preparation."""
            self.prepared.extend(placeholders)

        def delete_placeholder(self, placeholder) -> None:
            """Record placeholder deletion."""
            self.deleted.append(placeholder)

    package_module = types.ModuleType("ayon_katana")
    package_module.__path__ = []
    api_package = types.ModuleType("ayon_katana.api")
    api_package.__path__ = []
    katana_builder = types.ModuleType("ayon_katana.api.workfile_template_builder")
    katana_builder.KatanaPlaceholderPlugin = PlaceholderBase
    monkeypatch.setitem(sys.modules, "ayon_katana", package_module)
    monkeypatch.setitem(sys.modules, "ayon_katana.api", api_package)
    monkeypatch.setitem(
        sys.modules,
        "ayon_katana.api.workfile_template_builder",
        katana_builder,
    )

    path = (
        ROOT
        / "client"
        / "ayon_katana"
        / "plugins"
        / "workfile_build"
        / "script_placeholder.py"
    )
    spec = importlib.util.spec_from_file_location(
        "ayon_katana.plugins.workfile_build.script_placeholder",
        path,
    )
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_script_placeholder_options_warn_and_collection_is_filtered(monkeypatch):
    """The UI labels unsandboxed code and ignores other placeholder types."""
    module = _load_script_placeholder(monkeypatch)
    plugin = module.KatanaPlaceholderScriptPlugin()
    plugin.nodes = [
        FakeNode("script", {"plugin_identifier": plugin.identifier}),
        FakeNode("load", {"plugin_identifier": "ayon.load.placeholder"}),
    ]

    options = plugin.get_placeholder_options()
    placeholders = plugin.collect_placeholders()

    assert [option.key for option in options] == [
        "order",
        "prepare_script",
        "populate_script",
        "depth_processed_script",
        "finished_script",
    ]
    assert "Unsandboxed" in plugin.label
    assert all(
        "unsandboxed" in option.kwargs.get("tooltip", "").lower()
        for option in options[1:]
    )
    assert [item.scene_identifier for item in placeholders] == ["script"]


def test_script_placeholder_executes_all_phases_and_defers_deletion(monkeypatch):
    """Prepare, populate, depth, and finish scripts receive the Core context."""
    module = _load_script_placeholder(monkeypatch)
    plugin = module.KatanaPlaceholderScriptPlugin()
    plugin.trace = []
    placeholder = FakePlaceholderItem(
        "script",
        {
            "order": 7,
            "keep_placeholder": False,
            "prepare_script": "plugin.trace.append(('prepare', event))",
            "populate_script": "plugin.trace.append(('populate', event))",
            "depth_processed_script": "plugin.trace.append(('depth', event.topic))",
            "finished_script": "plugin.trace.append(('finish', event.topic))",
        },
        plugin,
    )

    plugin.prepare_placeholders([placeholder])
    plugin.populate_placeholder(placeholder)
    depth_event = types.SimpleNamespace(topic="template.depth_processed")
    finish_event = types.SimpleNamespace(topic="template.finished")
    plugin.builder.depth_callbacks[0][1](depth_event)
    plugin.builder.finished_callbacks[0][1](finish_event)
    plugin.builder.finished_callbacks[1][1](finish_event)

    assert plugin.trace == [
        ("prepare", None),
        ("populate", None),
        ("depth", "template.depth_processed"),
        ("finish", "template.finished"),
    ]
    assert [order for order, _callback in plugin.builder.depth_callbacks] == [7]
    assert [order for order, _callback in plugin.builder.finished_callbacks] == [7, 8]
    assert plugin.deleted == [placeholder]
