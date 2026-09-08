"""Focused tests for AYON Katana menu actions."""

from __future__ import annotations

import importlib.util
import sys
import types
from pathlib import Path

ROOT = Path(__file__).parents[1]


def _load_menu_module(monkeypatch):
    """Load the menu module with compact Core, Katana, and Qt stubs."""
    host_tools = types.SimpleNamespace()
    utils_module = types.ModuleType("ayon_core.tools.utils")
    utils_module.host_tools = host_tools
    tools_module = types.ModuleType("ayon_core.tools")
    tools_module.__path__ = []
    core_module = types.ModuleType("ayon_core")
    core_module.__path__ = []
    monkeypatch.setitem(sys.modules, "ayon_core", core_module)
    monkeypatch.setitem(sys.modules, "ayon_core.tools", tools_module)
    monkeypatch.setitem(sys.modules, "ayon_core.tools.utils", utils_module)

    katana_module = types.ModuleType("Katana")
    katana_module.UI4 = types.SimpleNamespace(
        App=types.SimpleNamespace(
            MainWindow=types.SimpleNamespace(GetMainWindow=lambda: None)
        )
    )
    monkeypatch.setitem(sys.modules, "Katana", katana_module)
    qtpy_module = types.ModuleType("qtpy")
    qtpy_module.QtWidgets = types.SimpleNamespace(QMenuBar=object, QMenu=object)
    monkeypatch.setitem(sys.modules, "qtpy", qtpy_module)

    package_module = types.ModuleType("ayon_katana")
    package_module.__path__ = []
    api_package = types.ModuleType("ayon_katana.api")
    api_package.__path__ = []
    monkeypatch.setitem(sys.modules, "ayon_katana", package_module)
    monkeypatch.setitem(sys.modules, "ayon_katana.api", api_package)

    module_path = ROOT / "client" / "ayon_katana" / "api" / "menu.py"
    module_spec = importlib.util.spec_from_file_location(
        "ayon_katana.api.menu",
        module_path,
    )
    assert module_spec is not None
    assert module_spec.loader is not None
    module = importlib.util.module_from_spec(module_spec)
    monkeypatch.setitem(sys.modules, module_spec.name, module)
    module_spec.loader.exec_module(module)
    return module


def test_menu_actions_delegate_to_core_and_katana_helpers(monkeypatch) -> None:
    """Version, range, and resolver actions use their maintained APIs."""
    module = _load_menu_module(monkeypatch)
    calls = []

    workfile_module = types.ModuleType("ayon_core.pipeline.workfile")
    workfile_module.save_next_version = lambda: calls.append("version")
    pipeline_module = types.ModuleType("ayon_core.pipeline")
    pipeline_module.__path__ = []
    monkeypatch.setitem(sys.modules, "ayon_core.pipeline", pipeline_module)
    monkeypatch.setitem(
        sys.modules,
        "ayon_core.pipeline.workfile",
        workfile_module,
    )

    context_module = types.ModuleType("ayon_katana.api.context")
    context_module.apply_current_frame_range = lambda: calls.append("range")
    usd_module = types.ModuleType("ayon_katana.api.usd")
    usd_module.clear_resolver_cache = lambda: calls.append("resolver")
    monkeypatch.setitem(sys.modules, "ayon_katana.api.context", context_module)
    monkeypatch.setitem(sys.modules, "ayon_katana.api.usd", usd_module)

    module._version_up_workfile()
    module._set_frame_range()
    module._clear_usd_resolver_cache()

    assert calls == ["version", "range", "resolver"]


def test_version_up_action_respects_core_menu_setting(monkeypatch) -> None:
    """Version Up availability follows the shared AYON menu setting."""
    module = _load_menu_module(monkeypatch)
    context_tools_module = types.ModuleType("ayon_core.pipeline.context_tools")
    context_tools_module.get_current_project_settings = lambda: {
        "core": {
            "tools": {
                "ayon_menu": {"version_up_current_workfile": True},
            }
        }
    }
    pipeline_module = types.ModuleType("ayon_core.pipeline")
    pipeline_module.__path__ = []
    monkeypatch.setitem(sys.modules, "ayon_core.pipeline", pipeline_module)
    monkeypatch.setitem(
        sys.modules,
        "ayon_core.pipeline.context_tools",
        context_tools_module,
    )

    assert module._version_up_enabled() is True

    context_tools_module.get_current_project_settings = lambda: {}
    assert module._version_up_enabled() is False

    def _settings_unavailable():
        raise ConnectionError("AYON Server is unavailable")

    context_tools_module.get_current_project_settings = _settings_unavailable
    assert module._version_up_enabled() is False
