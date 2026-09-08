"""Tests for Workfile Builder compatibility behavior."""

from __future__ import annotations

import ast
import importlib.util
import sys
import types
from pathlib import Path

ROOT = Path(__file__).parents[1]


class FakeLoadPlaceholderItem:
    """Minimal load placeholder item."""

    def __init__(self, scene_identifier, data, plugin) -> None:
        self.scene_identifier = scene_identifier
        self.data = data
        self.plugin = plugin


class FakeKatanaPlaceholderPlugin:
    """Minimal Katana placeholder base class."""

    nodes = []

    def collect_scene_placeholders(self):
        """Return configured fake placeholder nodes."""
        return self.nodes

    @staticmethod
    def _read(node):
        """Return copied placeholder metadata."""
        return dict(node.data)


class FakeNode:
    """Minimal Katana placeholder node."""

    def __init__(self, name: str, data: dict) -> None:
        self.name = name
        self.data = data

    def getName(self) -> str:
        """Return the node name."""
        return self.name


def _load_placeholder_module(monkeypatch):
    """Load the placeholder plugin with compact AYON and Katana stubs."""
    builder_module = types.ModuleType(
        "ayon_core.pipeline.workfile.workfile_template_builder"
    )
    builder_module.LoadPlaceholderItem = FakeLoadPlaceholderItem
    builder_module.PlaceholderLoadMixin = type("PlaceholderLoadMixin", (), {})

    pipeline_module = types.ModuleType("ayon_core.pipeline")
    pipeline_module.__path__ = []
    core_module = types.ModuleType("ayon_core")
    core_module.__path__ = []
    monkeypatch.setitem(sys.modules, "ayon_core", core_module)
    monkeypatch.setitem(sys.modules, "ayon_core.pipeline", pipeline_module)
    monkeypatch.setitem(
        sys.modules,
        "ayon_core.pipeline.workfile.workfile_template_builder",
        builder_module,
    )

    compat_module = types.SimpleNamespace()
    api_module = types.ModuleType("ayon_katana.api")
    api_module.__path__ = []
    api_module.compat = compat_module

    katana_builder_module = types.ModuleType(
        "ayon_katana.api.workfile_template_builder"
    )
    katana_builder_module.KatanaPlaceholderPlugin = FakeKatanaPlaceholderPlugin

    katana_module = types.ModuleType("ayon_katana")
    katana_module.__path__ = []
    plugins_module = types.ModuleType("ayon_katana.plugins")
    plugins_module.__path__ = []
    workfile_build_module = types.ModuleType("ayon_katana.plugins.workfile_build")
    workfile_build_module.__path__ = []

    monkeypatch.setitem(sys.modules, "ayon_katana", katana_module)
    monkeypatch.setitem(sys.modules, "ayon_katana.api", api_module)
    monkeypatch.setitem(
        sys.modules,
        "ayon_katana.api.workfile_template_builder",
        katana_builder_module,
    )
    monkeypatch.setitem(sys.modules, "ayon_katana.plugins", plugins_module)
    monkeypatch.setitem(
        sys.modules,
        "ayon_katana.plugins.workfile_build",
        workfile_build_module,
    )

    module_path = (
        ROOT
        / "client"
        / "ayon_katana"
        / "plugins"
        / "workfile_build"
        / "load_placeholder.py"
    )
    module_spec = importlib.util.spec_from_file_location(
        "ayon_katana.plugins.workfile_build.load_placeholder",
        module_path,
    )
    assert module_spec is not None
    assert module_spec.loader is not None
    module = importlib.util.module_from_spec(module_spec)
    monkeypatch.setitem(sys.modules, module_spec.name, module)
    module_spec.loader.exec_module(module)
    return module


def test_collected_placeholder_preserves_loader_name(monkeypatch) -> None:
    """Persisted placeholders should use the exact configured loader name."""
    module = _load_placeholder_module(monkeypatch)
    plugin = module.KatanaPlaceholderLoadPlugin()
    plugin.nodes = [
        FakeNode(
            "AYON_PLACEHOLDER_model",
            {
                "plugin_identifier": plugin.identifier,
                "loader": "UsdLoader",
            },
        )
    ]

    placeholders = plugin.collect_placeholders()

    assert len(placeholders) == 1
    assert placeholders[0].data["loader"] == "UsdLoader"


def test_workfile_builder_profiles_expose_independent_core_triggers() -> None:
    """Katana defaults match the AYON Core 1.9.9 trigger contract."""
    settings_path = ROOT / "server" / "settings" / "templated_workfile_build.py"
    tree = ast.parse(settings_path.read_text(encoding="utf-8"))
    profile_model = next(
        node
        for node in tree.body
        if isinstance(node, ast.ClassDef)
        and node.name == "TemplatedWorkfileProfileModel"
    )
    defaults = {}
    for node in profile_model.body:
        if not isinstance(node, ast.AnnAssign):
            continue
        if not isinstance(node.target, ast.Name) or not isinstance(
            node.value, ast.Call
        ):
            continue
        if not node.value.args:
            continue
        defaults[node.target.id] = ast.literal_eval(node.value.args[0])

    assert defaults["execute_on_app_launch"] is True
    assert defaults["execute_on_new_file"] is False
    assert defaults["create_first_version"] is True
