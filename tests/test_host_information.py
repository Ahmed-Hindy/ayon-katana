"""Tests for Katana host information and selection preservation."""

from __future__ import annotations

import importlib.util
import sys
import types
from dataclasses import dataclass
from pathlib import Path

import pytest

ROOT = Path(__file__).parents[1]


def _load_module(monkeypatch, module_name: str, module_path: Path):
    """Load a module under a controlled package-qualified name."""
    module_spec = importlib.util.spec_from_file_location(module_name, module_path)
    assert module_spec is not None
    assert module_spec.loader is not None
    module = importlib.util.module_from_spec(module_spec)
    monkeypatch.setitem(sys.modules, module_name, module)
    module_spec.loader.exec_module(module)
    return module


@dataclass
class _ApplicationInformation:
    """Small stand-in for AYON Core's application-information contract."""

    app_name: str | None = None
    app_version: str | None = None


class _Node:
    """Minimal Katana node with a globally unique name."""

    def __init__(self, name: str) -> None:
        self.name = name

    def getName(self) -> str:
        """Return the current node name."""
        return self.name


def _load_pipeline_module(monkeypatch, node_map, selected_nodes, restored):
    """Load ``pipeline`` with the small host APIs exercised by these tests."""

    class HostBase:
        """Minimal HostBase implementation."""

        def __init__(self) -> None:
            pass

    class IWorkfileHost:
        """Distinct marker interface."""

    class ILoadHost:
        """Distinct marker interface."""

    class IPublishHost:
        """Distinct marker interface."""

    host_module = types.ModuleType("ayon_core.host")
    host_module.ApplicationInformation = _ApplicationInformation
    host_module.HostBase = HostBase
    host_module.ILoadHost = ILoadHost
    host_module.IPublishHost = IPublishHost
    host_module.IWorkfileHost = IWorkfileHost

    core_lib = types.ModuleType("ayon_core.lib")
    core_lib.register_event_callback = lambda *_args: None
    pipeline_core = types.ModuleType("ayon_core.pipeline")
    for name in (
        "deregister_creator_plugin_path",
        "deregister_inventory_action_path",
        "deregister_loader_plugin_path",
        "deregister_workfile_build_plugin_path",
        "register_creator_plugin_path",
        "register_inventory_action_path",
        "register_loader_plugin_path",
        "register_workfile_build_plugin_path",
    ):
        setattr(pipeline_core, name, lambda *_args: None)

    monkeypatch.setitem(sys.modules, "ayon_core", types.ModuleType("ayon_core"))
    monkeypatch.setitem(sys.modules, "ayon_core.host", host_module)
    monkeypatch.setitem(sys.modules, "ayon_core.lib", core_lib)
    monkeypatch.setitem(sys.modules, "ayon_core.pipeline", pipeline_core)

    pyblish_api = types.ModuleType("pyblish.api")
    pyblish_api.deregister_host = lambda *_args: None
    pyblish_api.deregister_plugin_path = lambda *_args: None
    pyblish_api.register_host = lambda *_args: None
    pyblish_api.register_plugin_path = lambda *_args: None
    pyblish_module = types.ModuleType("pyblish")
    pyblish_module.api = pyblish_api
    monkeypatch.setitem(sys.modules, "pyblish", pyblish_module)
    monkeypatch.setitem(sys.modules, "pyblish.api", pyblish_api)

    katana_module = types.ModuleType("Katana")
    katana_module.__version__ = "9.0.1"
    monkeypatch.setitem(sys.modules, "Katana", katana_module)

    package_module = types.ModuleType("ayon_katana")
    package_module.__path__ = []
    package_module.KATANA_HOST_DIR = str(ROOT / "client" / "ayon_katana")
    api_package = types.ModuleType("ayon_katana.api")
    api_package.__path__ = []
    compat_module = types.ModuleType("ayon_katana.api.compat")
    compat_module.get_node = node_map.get
    compat_module.get_selected_nodes = lambda: list(selected_nodes)
    compat_module.set_selected_nodes = lambda nodes: restored.append(list(nodes))
    callbacks_module = types.ModuleType("ayon_katana.api.callbacks")
    callbacks_module.CallbackManager = lambda lifecycle: object()
    context_module = types.ModuleType("ayon_katana.api.context")
    containers_module = types.ModuleType("ayon_katana.api.containers")
    lifecycle_module = types.ModuleType("ayon_katana.api.lifecycle")
    lifecycle_module.LifecycleController = lambda host: object()
    workio_module = types.ModuleType("ayon_katana.api.workio")
    for module_name, module in (
        ("ayon_katana", package_module),
        ("ayon_katana.api", api_package),
        ("ayon_katana.api.callbacks", callbacks_module),
        ("ayon_katana.api.compat", compat_module),
        ("ayon_katana.api.context", context_module),
        ("ayon_katana.api.containers", containers_module),
        ("ayon_katana.api.lifecycle", lifecycle_module),
        ("ayon_katana.api.workio", workio_module),
    ):
        monkeypatch.setitem(sys.modules, module_name, module)

    lib_module = _load_module(
        monkeypatch,
        "ayon_katana.api.lib",
        ROOT / "client" / "ayon_katana" / "api" / "lib.py",
    )
    api_package.lib = lib_module

    return _load_module(
        monkeypatch,
        "ayon_katana.api.pipeline",
        ROOT / "client" / "ayon_katana" / "api" / "pipeline.py",
    )


def test_host_reports_native_katana_application_information(monkeypatch) -> None:
    """Katana's native Python version must populate Core's host metadata."""
    module = _load_pipeline_module(monkeypatch, {}, [], [])

    application_information = module.KatanaHost().get_app_information()

    assert isinstance(application_information, _ApplicationInformation)
    assert application_information.app_name == "Katana"
    assert application_information.app_version == "9.0.1"


def test_host_uses_katana_root_version_when_native_version_is_missing(
    monkeypatch,
) -> None:
    """Katana 8 falls back to the configured application root version."""
    module = _load_pipeline_module(monkeypatch, {}, [], [])
    monkeypatch.delattr(sys.modules["Katana"], "__version__")
    monkeypatch.setenv("KATANA_ROOT", r"C:\Program Files\Katana8.0v1")

    application_information = module.KatanaHost().get_app_information()

    assert application_information.app_version == "8.0v1"


def test_maintained_selection_restores_only_live_original_nodes(monkeypatch) -> None:
    """Deleted nodes and same-name replacements must not be selected again."""
    retained_node = _Node("retained")
    deleted_node = _Node("deleted")
    replaced_node = _Node("replaced")
    replacement_node = _Node("replaced")
    selected_nodes = [retained_node, deleted_node, replaced_node]
    restored = []
    module = _load_pipeline_module(
        monkeypatch,
        {
            retained_node.name: retained_node,
            replacement_node.name: replacement_node,
        },
        selected_nodes,
        restored,
    )

    with module.KatanaHost().maintained_selection():
        selected_nodes[:] = [_Node("temporary")]

    assert restored == [[retained_node]]


def test_maintained_selection_restores_selection_after_an_error(monkeypatch) -> None:
    """Selection restoration must run when the enclosed Core operation fails."""
    selected_node = _Node("selected")
    restored = []
    module = _load_pipeline_module(
        monkeypatch,
        {selected_node.name: selected_node},
        [selected_node],
        restored,
    )

    with (
        pytest.raises(RuntimeError, match="operation failed"),
        module.KatanaHost().maintained_selection(),
    ):
        raise RuntimeError("operation failed")

    assert restored == [[selected_node]]
