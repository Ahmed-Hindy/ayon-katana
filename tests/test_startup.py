"""Tests for Katana startup workfile coordination."""

from __future__ import annotations

import importlib.util
import os
import sys
import types
from pathlib import Path
from typing import Optional

ROOT = Path(__file__).parents[1]
REQUESTED_WORKFILE_ENV = "AYON_KATANA_WORKFILE_PATH"


def _load_startup_module():
    """Load the startup coordinator without importing the Katana package."""
    module_path = ROOT / "client" / "ayon_katana" / "api" / "startup.py"
    module_spec = importlib.util.spec_from_file_location(
        "ayon_katana_startup_test", module_path
    )
    assert module_spec is not None
    assert module_spec.loader is not None
    module = importlib.util.module_from_spec(module_spec)
    module_spec.loader.exec_module(module)
    return module


class FakeWorkio:
    """Small workfile API test double with observable load calls."""

    def __init__(
        self, current_path: str = "", open_error: Optional[Exception] = None
    ) -> None:
        self.current_path = current_path
        self.open_error = open_error
        self.opened_paths = []

    @staticmethod
    def validate_workfile_path(path: str, *, require_exists: bool = False) -> str:
        """Validate the test path using the production-facing contract."""
        invalid_extension = not path.endswith(".katana")
        missing_file = require_exists and path == "missing.katana"
        if invalid_extension or missing_file:
            raise ValueError(path)
        return os.path.abspath(path)

    def get_current_workfile(self) -> str:
        """Return the configured current project path."""
        return self.current_path

    @staticmethod
    def workfile_paths_match(first_path: str, second_path: str) -> bool:
        """Compare normalized test paths."""
        return os.path.normcase(os.path.abspath(first_path)) == os.path.normcase(
            os.path.abspath(second_path)
        )

    def open_workfile(self, path: str) -> str:
        """Record or fail the requested open operation."""
        self.opened_paths.append(path)
        if self.open_error is not None:
            raise self.open_error
        self.current_path = path
        return path


def test_requested_workfile_is_consumed_and_opened_once() -> None:
    """The coordinator consumes the request and cannot reopen it accidentally."""
    module = _load_startup_module()
    environment = {REQUESTED_WORKFILE_ENV: "selected.katana"}
    workio = FakeWorkio()

    assert module.has_requested_workfile(environment) is True
    first_result = module.open_requested_workfile(environment, workio)
    assert module.has_requested_workfile(environment) is False
    second_result = module.open_requested_workfile(environment, workio)

    expected_path = os.path.abspath("selected.katana")
    assert first_result == expected_path
    assert second_result is None
    assert workio.opened_paths == [expected_path]
    assert REQUESTED_WORKFILE_ENV not in environment


def test_already_open_workfile_is_not_loaded_again() -> None:
    """Native startup loading of the same path is detected and preserved."""
    module = _load_startup_module()
    current_path = os.path.abspath("selected.katana")
    environment = {REQUESTED_WORKFILE_ENV: current_path}
    workio = FakeWorkio(current_path=current_path)

    result = module.open_requested_workfile(environment, workio)

    assert result == current_path
    assert workio.opened_paths == []


def test_invalid_or_failed_workfile_leaves_opening_to_katana() -> None:
    """Validation and load failures do not trigger replacement or save calls."""
    module = _load_startup_module()
    missing_environment = {REQUESTED_WORKFILE_ENV: "missing.katana"}
    failing_environment = {REQUESTED_WORKFILE_ENV: "broken.katana"}
    missing_workio = FakeWorkio(current_path="current.katana")
    failing_workio = FakeWorkio(
        current_path="current.katana",
        open_error=RuntimeError("load failed"),
    )

    missing_result = module.open_requested_workfile(
        missing_environment,
        missing_workio,
    )
    failing_result = module.open_requested_workfile(
        failing_environment,
        failing_workio,
    )

    assert missing_result is None
    assert missing_workio.current_path == "current.katana"
    assert missing_workio.opened_paths == []
    assert failing_result is None
    assert failing_workio.current_path == "current.katana"
    assert failing_workio.opened_paths == [os.path.abspath("broken.katana")]


def test_startup_resource_installs_the_host(monkeypatch) -> None:
    """Katana startup installs AYON before native startup completion."""
    events = []
    bindings_module = types.ModuleType("ayon_katana.usd_bindings")
    bindings_module.install_usd_bindings = lambda: events.append(("bindings", None))
    pipeline_module = types.ModuleType("ayon_core.pipeline")
    pipeline_module.install_host = lambda host: events.append(("install", host))
    core_module = types.ModuleType("ayon_core")
    core_module.pipeline = pipeline_module

    api_module = types.ModuleType("ayon_katana.api")

    class KatanaHost:
        """Host marker used by the startup resource test."""

        def __init__(self) -> None:
            events.append(("host", self))

    api_module.KatanaHost = KatanaHost
    katana_module = types.ModuleType("ayon_katana")
    katana_module.__path__ = []
    katana_module.api = api_module
    katana_module.usd_bindings = bindings_module

    monkeypatch.setitem(sys.modules, "ayon_core", core_module)
    monkeypatch.setitem(sys.modules, "ayon_core.pipeline", pipeline_module)
    monkeypatch.setitem(sys.modules, "ayon_katana", katana_module)
    monkeypatch.setitem(sys.modules, "ayon_katana.api", api_module)
    monkeypatch.setitem(
        sys.modules,
        "ayon_katana.usd_bindings",
        bindings_module,
    )

    init_path = ROOT / "client" / "ayon_katana" / "resources" / "Startup" / "init.py"
    module_spec = importlib.util.spec_from_file_location(
        "ayon_katana_startup_resource_test", init_path
    )
    assert module_spec is not None
    assert module_spec.loader is not None
    module = importlib.util.module_from_spec(module_spec)
    module_spec.loader.exec_module(module)

    assert [event[0] for event in events] == ["bindings", "host", "install"]
    assert events[2][1] is events[1][1]
