"""Tests for Katana's host-owned USD binding compatibility."""

from __future__ import annotations

import importlib.util
import sys
import types
from pathlib import Path

import pytest

ROOT = Path(__file__).parents[1]
BINDINGS_PATH = ROOT / "client" / "ayon_katana" / "usd_bindings.py"


def _load_bindings_module():
    """Load the compatibility module without importing the Katana package."""
    module_spec = importlib.util.spec_from_file_location(
        "ayon_katana_usd_bindings_test",
        BINDINGS_PATH,
    )
    assert module_spec is not None
    assert module_spec.loader is not None
    module = importlib.util.module_from_spec(module_spec)
    module_spec.loader.exec_module(module)
    return module


def test_external_pxr_binding_is_rejected(monkeypatch) -> None:
    """Katana must not mix its bundled USD with an external USD build."""
    module = _load_bindings_module()
    standard_pxr = types.ModuleType("pxr")
    root_module = types.ModuleType("fnpxr")
    submodules = {
        name: types.ModuleType(f"fnpxr.{name}") for name in module.USD_SUBMODULES
    }

    def fake_import(name: str):
        if name == "fnpxr":
            return root_module
        return submodules[name.removeprefix("fnpxr.")]

    monkeypatch.setattr(module, "import_module", fake_import)
    monkeypatch.setitem(sys.modules, "pxr", standard_pxr)

    with pytest.raises(module.UsdBindingConflictError, match="different USD build"):
        module.install_usd_bindings()

    assert sys.modules["pxr"] is standard_pxr


def test_fnpxr_is_exposed_as_atomic_pxr_aliases(monkeypatch) -> None:
    """Katana's binding satisfies standard root and submodule imports."""
    module = _load_bindings_module()
    root_module = types.ModuleType("fnpxr")
    submodules = {
        name: types.ModuleType(f"fnpxr.{name}") for name in module.USD_SUBMODULES
    }

    def fake_import(name: str):
        if name == "fnpxr":
            return root_module
        return submodules[name.removeprefix("fnpxr.")]

    monkeypatch.setattr(module, "import_module", fake_import)
    monkeypatch.delitem(sys.modules, "pxr", raising=False)
    for name in module.USD_SUBMODULES:
        monkeypatch.delitem(sys.modules, f"pxr.{name}", raising=False)

    assert module.install_usd_bindings() == "fnpxr"
    assert module.install_usd_bindings() == "fnpxr"
    assert sys.modules["pxr"] is root_module
    for name, submodule in submodules.items():
        assert getattr(root_module, name) is submodule
        assert sys.modules[f"pxr.{name}"] is submodule


def test_incomplete_fnpxr_does_not_publish_partial_aliases(monkeypatch) -> None:
    """A failed binding initialization leaves the import namespace untouched."""
    module = _load_bindings_module()

    def fake_import(name: str):
        if name == "fnpxr":
            return types.ModuleType("fnpxr")
        raise ModuleNotFoundError(name=name)

    monkeypatch.setattr(module, "import_module", fake_import)
    monkeypatch.delitem(sys.modules, "pxr", raising=False)

    assert module.install_usd_bindings() is None
    assert "pxr" not in sys.modules
