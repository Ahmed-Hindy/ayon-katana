"""Tests for Katana renderer discovery and default selection."""

from __future__ import annotations

import importlib.util
import sys
import types
from pathlib import Path

import pytest


def _load_render_module(monkeypatch, renderer_names):
    """Load the render helpers with a minimal fake Katana registry."""
    render_plugins = types.SimpleNamespace(
        GetRendererPluginNames=lambda: list(renderer_names),
    )
    katana_module = types.ModuleType("Katana")
    katana_module.NodegraphAPI = types.SimpleNamespace()
    katana_module.RenderingAPI = types.SimpleNamespace(RenderPlugins=render_plugins)
    monkeypatch.setitem(sys.modules, "Katana", katana_module)

    package_module = types.ModuleType("ayon_katana")
    package_module.__path__ = []
    api_module = types.ModuleType("ayon_katana.api")
    api_module.__path__ = []
    lib_module = types.ModuleType("ayon_katana.api.lib")
    monkeypatch.setitem(sys.modules, "ayon_katana", package_module)
    monkeypatch.setitem(sys.modules, "ayon_katana.api", api_module)
    monkeypatch.setitem(sys.modules, "ayon_katana.api.lib", lib_module)

    module_path = (
        Path(__file__).parents[1] / "client" / "ayon_katana" / "api" / "render.py"
    )
    module_spec = importlib.util.spec_from_file_location(
        "ayon_katana.api.render",
        module_path,
    )
    assert module_spec is not None
    assert module_spec.loader is not None
    module = importlib.util.module_from_spec(module_spec)
    monkeypatch.setitem(sys.modules, "ayon_katana.api.render", module)
    module_spec.loader.exec_module(module)
    return module


def test_katana_executable_prefers_katana_root(monkeypatch, tmp_path) -> None:
    """Batch and farm rendering share the current Windows Katana installation."""
    render = _load_render_module(monkeypatch, ["prman"])
    monkeypatch.setattr(render.sys, "platform", "win32")
    executable = tmp_path / "Katana9.0v1" / "bin" / "katanaBin.exe"
    executable.parent.mkdir(parents=True)
    executable.write_text("", encoding="utf-8")
    monkeypatch.setenv("KATANA_ROOT", str(executable.parents[1]))
    monkeypatch.delenv("AYON_APP_EXECUTABLE", raising=False)
    monkeypatch.setattr(render.sys, "executable", "C:/Python/python.exe")

    assert render.get_katana_executable() == executable


def test_katana_executable_supports_linux_katana_root(monkeypatch, tmp_path) -> None:
    """Linux launches resolve Katana's extensionless batch executable."""
    render = _load_render_module(monkeypatch, ["prman"])
    monkeypatch.setattr(render.sys, "platform", "linux")
    executable = tmp_path / "Katana9.0v1" / "bin" / "katanaBin"
    executable.parent.mkdir(parents=True)
    executable.write_text("", encoding="utf-8")
    monkeypatch.setenv("KATANA_ROOT", str(executable.parents[1]))
    monkeypatch.delenv("AYON_APP_EXECUTABLE", raising=False)
    monkeypatch.setattr(render.sys, "executable", "/usr/bin/python3")

    assert render.get_katana_executable() == executable


def test_katana_executable_requires_a_real_candidate(monkeypatch) -> None:
    """Missing launch metadata must fail instead of guessing an executable."""
    render = _load_render_module(monkeypatch, ["prman"])
    monkeypatch.delenv("KATANA_ROOT", raising=False)
    monkeypatch.delenv("AYON_APP_EXECUTABLE", raising=False)
    monkeypatch.setattr(render.sys, "executable", "C:/Python/python.exe")

    with pytest.raises(RuntimeError, match="Could not resolve"):
        render.get_katana_executable()


def test_registered_renderers_exclude_internal_plugins(monkeypatch) -> None:
    """Artist selectors should contain only actual pixel renderers."""
    render = _load_render_module(
        monkeypatch,
        ["usd", "dl", "profilingMockRenderer", "prman", "prman"],
    )

    assert render.get_registered_renderers() == ["dl", "prman"]
    assert render.get_registered_renderers(include_internal=True) == [
        "dl",
        "prman",
        "profilingMockRenderer",
        "usd",
    ]


def test_default_renderer_uses_settings_then_environment(monkeypatch) -> None:
    """Project settings should override DEFAULT_RENDERER when both are valid."""
    render = _load_render_module(monkeypatch, ["prman", "dl"])
    monkeypatch.setenv("DEFAULT_RENDERER", "dl")

    assert render.get_default_renderer("prman") == "prman"
    assert render.get_default_renderer("missing") == "dl"
    assert render.is_renderer_registered("prman")
    assert not render.is_renderer_registered("missing")


def test_default_renderer_requires_configuration(monkeypatch) -> None:
    """Renderer selection should stay empty without an explicit default."""
    render = _load_render_module(monkeypatch, ["dl", "prman"])
    monkeypatch.delenv("DEFAULT_RENDERER", raising=False)

    assert render.get_default_renderer() == ""


def test_render_output_aov_identifiers(monkeypatch) -> None:
    """Beauty stays the main product while named channels become AOVs."""
    render = _load_render_module(monkeypatch, ["prman"])
    beauty = render.RenderOutputDefinition(
        node_name="beautyNode",
        name="primary",
        path="beauty.####.exr",
        extension="exr",
        channel="rgba",
        enabled=True,
    )
    depth = render.RenderOutputDefinition(
        node_name="depthNode",
        name="depth",
        path="depth.####.exr",
        extension="exr",
        channel="Z",
        enabled=True,
    )

    assert beauty.aov_identifier == ""
    assert depth.aov_identifier == "Z"
