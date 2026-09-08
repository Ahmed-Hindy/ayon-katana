"""Tests for the Katana client addon launch environment."""

from __future__ import annotations

import importlib.util
import os
import sys
import types
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).parents[1]


class FakeAYONAddon:
    """Minimal AYON addon base class."""


class FakeHostAddon:
    """Minimal AYON host-addon interface."""


def _load_addon_module(monkeypatch):
    """Load the Katana addon with a minimal AYON Core runtime."""
    addon_core = types.ModuleType("ayon_core.addon")
    addon_core.AYONAddon = FakeAYONAddon
    addon_core.IHostAddon = FakeHostAddon
    ayon_core = types.ModuleType("ayon_core")
    ayon_core.addon = addon_core

    package_module = types.ModuleType("ayon_katana")
    package_module.__path__ = []
    version_module = types.ModuleType("ayon_katana.version")
    version_module.__version__ = "0.1.34+dev"

    monkeypatch.setitem(sys.modules, "ayon_core", ayon_core)
    monkeypatch.setitem(sys.modules, "ayon_core.addon", addon_core)
    monkeypatch.setitem(sys.modules, "ayon_katana", package_module)
    monkeypatch.setitem(sys.modules, "ayon_katana.version", version_module)

    module_path = PROJECT_ROOT / "client" / "ayon_katana" / "addon.py"
    module_spec = importlib.util.spec_from_file_location(
        "ayon_katana.addon",
        module_path,
    )
    assert module_spec is not None
    assert module_spec.loader is not None
    module = importlib.util.module_from_spec(module_spec)
    monkeypatch.setitem(sys.modules, "ayon_katana.addon", module)
    module_spec.loader.exec_module(module)
    return module


def test_addon_paths_are_prepended_once(monkeypatch) -> None:
    """Exact existing launch paths are not duplicated on any platform."""
    addon_module = _load_addon_module(monkeypatch)
    resources_path = os.path.normpath(
        os.path.join(addon_module.KATANA_HOST_DIR, "resources")
    )
    package_parent = os.path.normpath(os.path.dirname(addon_module.KATANA_HOST_DIR))
    other_resource = os.path.normpath(os.path.join(resources_path, "..", "other"))
    other_python_path = os.path.normpath(os.path.join(package_parent, "other_python"))
    environment = {
        "KATANA_RESOURCES": os.pathsep.join([resources_path, other_resource]),
        "PYTHONPATH": os.pathsep.join([package_parent, other_python_path]),
    }

    addon_module.KatanaAddon().add_implementation_envs(environment, None)

    resource_paths = environment["KATANA_RESOURCES"].split(os.pathsep)
    python_paths = environment["PYTHONPATH"].split(os.pathsep)
    assert resource_paths == [resources_path, other_resource]
    assert python_paths == [package_parent, other_python_path]


@pytest.mark.skipif(os.name != "nt", reason="Windows-specific path semantics")
def test_addon_paths_are_prepended_once_case_insensitively(monkeypatch) -> None:
    """Katana launch paths remain unique under Windows path semantics."""
    addon_module = _load_addon_module(monkeypatch)
    resources_path = os.path.normpath(
        os.path.join(addon_module.KATANA_HOST_DIR, "resources")
    )
    package_parent = os.path.normpath(os.path.dirname(addon_module.KATANA_HOST_DIR))
    other_resource = os.path.normpath("C:/Katana/Resources")
    other_python_path = os.path.normpath("C:/Pipeline/Python")
    environment = {
        "KATANA_RESOURCES": os.pathsep.join(
            [resources_path.swapcase(), other_resource]
        ),
        "PYTHONPATH": os.pathsep.join([package_parent.swapcase(), other_python_path]),
    }

    addon_module.KatanaAddon().add_implementation_envs(environment, None)

    resource_paths = environment["KATANA_RESOURCES"].split(os.pathsep)
    python_paths = environment["PYTHONPATH"].split(os.pathsep)
    assert resource_paths[0] == resources_path
    assert python_paths[0] == package_parent
    assert (
        sum(
            os.path.normcase(path) == os.path.normcase(resources_path)
            for path in resource_paths
        )
        == 1
    )
    assert (
        sum(
            os.path.normcase(path) == os.path.normcase(package_parent)
            for path in python_paths
        )
        == 1
    )
    assert other_resource in resource_paths
    assert other_python_path in python_paths
