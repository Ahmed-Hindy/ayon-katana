"""Focused tests for Katana lifecycle and startup behavior."""

from __future__ import annotations

import importlib.util
import sys
import types
from pathlib import Path

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


class FakeLifecycle:
    """Record lifecycle dispatches from a callback manager."""

    def __init__(self) -> None:
        self.calls: list[str] = []

    def on_startup_complete(self) -> None:
        self.calls.append("init")

    def on_new(self) -> None:
        self.calls.append("new")

    def on_new_scene_loaded(self) -> None:
        self.calls.append("new_ready")

    def on_open(self) -> None:
        self.calls.append("open")

    def before_save(self) -> None:
        self.calls.append("before.save")

    def on_save(self) -> None:
        self.calls.append("save")


class FakeCallbacks:
    """Record Katana callback registration and deregistration."""

    class Type:
        onStartupComplete = "onStartupComplete"
        onSceneAboutToLoad = "onSceneAboutToLoad"
        onSceneLoad = "onSceneLoad"
        onSceneAboutToSave = "onSceneAboutToSave"
        onSceneSave = "onSceneSave"
        onNewScene = "onNewScene"

    def __init__(self) -> None:
        self.added: list[tuple[str, object]] = []
        self.removed: list[tuple[str, object]] = []

    def addCallback(self, callback_type, callback) -> None:
        """Record a callback registration."""
        self.added.append((callback_type, callback))

    def delCallback(self, callback_type, callback) -> None:
        """Record a callback deregistration."""
        self.removed.append((callback_type, callback))


def _load_callbacks_module(monkeypatch):
    """Load callback management with a small Katana substitute."""
    callbacks = FakeCallbacks()
    katana_module = types.ModuleType("Katana")
    katana_module.Callbacks = callbacks
    monkeypatch.setitem(sys.modules, "Katana", katana_module)
    return _load_module(
        monkeypatch,
        "ayon_katana.api.callbacks",
        ROOT / "client" / "ayon_katana" / "api" / "callbacks.py",
    ), callbacks


def test_callback_manager_installs_once_and_separates_new_from_open(monkeypatch):
    """Katana's paired ``New`` load callback must not emit an AYON open."""
    module, callbacks = _load_callbacks_module(monkeypatch)
    lifecycle = FakeLifecycle()
    manager = module.CallbackManager(lifecycle)

    manager.install()
    manager.install()
    assert len(callbacks.added) == 6

    manager._on_scene_about_to_load()
    manager._on_new_scene()
    manager._on_scene_load()
    manager._on_scene_about_to_load()
    manager._on_scene_load()
    manager._on_scene_about_to_save()
    manager._on_scene_save()

    assert lifecycle.calls == [
        "new",
        "new_ready",
        "open",
        "before.save",
        "save",
    ]

    manager.uninstall()
    assert len(callbacks.removed) == 6
    assert manager._registered_callbacks == []


def test_ui_plugin_has_no_import_time_callbacks_or_timers(monkeypatch):
    """Katana UI resource import must not own host lifecycle callbacks."""
    callback_calls = []
    timer_calls = []
    katana_module = types.ModuleType("Katana")
    katana_module.Callbacks = types.SimpleNamespace(
        Type=types.SimpleNamespace(onStartupComplete=object()),
        addCallback=lambda *args: callback_calls.append(args),
    )
    qtpy_module = types.ModuleType("qtpy")
    qtpy_module.QtCore = types.SimpleNamespace(
        QTimer=types.SimpleNamespace(
            singleShot=lambda *args: timer_calls.append(args),
        )
    )
    monkeypatch.setitem(sys.modules, "Katana", katana_module)
    monkeypatch.setitem(sys.modules, "qtpy", qtpy_module)

    _load_module(
        monkeypatch,
        "ayon_katana.resources.UIPlugins.ayon_menu",
        ROOT / "client" / "ayon_katana" / "resources" / "UIPlugins" / "ayon_menu.py",
    )

    assert callback_calls == []
    assert timer_calls == []


class FakeNodegraph:
    """Validate the native Katana timeline ordering used by context setup."""

    def __init__(self) -> None:
        self.in_time = 1.0
        self.out_time = 100.0
        self.current_time = 1.0
        self.calls: list[tuple[str, float]] = []

    def GetInTime(self) -> float:
        """Return the current timeline start."""
        return self.in_time

    def SetInTime(self, value: float) -> None:
        """Set a valid timeline start."""
        assert value < self.out_time
        self.in_time = value
        self.calls.append(("in", value))

    def SetOutTime(self, value: float) -> None:
        """Set a valid timeline end."""
        assert value > self.in_time
        self.out_time = value
        self.calls.append(("out", value))

    def SetCurrentTime(self, value: float) -> None:
        """Set the current Katana frame."""
        self.current_time = value
        self.calls.append(("current", value))

    def SetTimeIncrement(self, value: float) -> None:
        """Fail if FPS handling tries to repurpose navigation increment."""
        raise AssertionError(f"timeIncrement must not be used as FPS: {value}")


class FakeContextHost:
    """Minimal host storing embedded AYON context writes."""

    def __init__(self) -> None:
        self.context = {
            "project_name": "TestProject",
            "folder_path": "/assets/hero",
            "task_name": "layout",
        }
        self.updated_contexts: list[dict] = []

    def get_current_context(self) -> dict:
        """Return the active AYON context."""
        return dict(self.context)

    def update_context_data(self, data: dict) -> None:
        """Record a root-node context update."""
        self.updated_contexts.append(dict(data))


def _load_context_module(monkeypatch, graph: FakeNodegraph):
    """Load context helpers with only their needed Core and Katana APIs."""
    katana_module = types.ModuleType("Katana")
    katana_module.NodegraphAPI = graph
    monkeypatch.setitem(sys.modules, "Katana", katana_module)

    context_tools = types.ModuleType("ayon_core.pipeline.context_tools")
    context_tools.get_current_task_entity = lambda **_kwargs: None
    monkeypatch.setitem(sys.modules, "ayon_core", types.ModuleType("ayon_core"))
    monkeypatch.setitem(
        sys.modules,
        "ayon_core.pipeline",
        types.ModuleType("ayon_core.pipeline"),
    )
    monkeypatch.setitem(sys.modules, "ayon_core.pipeline.context_tools", context_tools)

    api_package = types.ModuleType("ayon_katana.api")
    api_package.__path__ = []
    package_module = types.ModuleType("ayon_katana")
    package_module.__path__ = []
    lib_module = types.ModuleType("ayon_katana.api.lib")
    lib_module.read_json_parameter = lambda *_args: None
    lib_module.write_json_parameter = lambda *_args: None
    instances_module = types.ModuleType("ayon_katana.api.instances")
    instances_module.iter_instances = lambda: iter(())
    instances_module.imprint = lambda *_args: None
    monkeypatch.setitem(sys.modules, "ayon_katana", package_module)
    monkeypatch.setitem(sys.modules, "ayon_katana.api", api_package)
    monkeypatch.setitem(sys.modules, "ayon_katana.api.instances", instances_module)
    monkeypatch.setitem(sys.modules, "ayon_katana.api.lib", lib_module)
    return _load_module(
        monkeypatch,
        "ayon_katana.api.context",
        ROOT / "client" / "ayon_katana" / "api" / "context.py",
    )


def test_context_settings_updates_range_without_simulating_fps(monkeypatch, caplog):
    """Only native range/current-time APIs are used for a new task context."""
    graph = FakeNodegraph()
    module = _load_context_module(monkeypatch, graph)
    task = {
        "attrib": {
            "frameStart": 1001,
            "frameEnd": 1010,
            "handleStart": 2,
            "handleEnd": 3,
            "fps": 24,
        }
    }
    monkeypatch.setattr(module, "_get_current_task_entity", lambda: task)
    host = FakeContextHost()

    result = module.apply_context_settings(host, {"task_name": "animation"})

    assert result["task_name"] == "animation"
    assert host.updated_contexts == [result]
    assert graph.in_time == 999.0
    assert graph.out_time == 1013.0
    assert graph.current_time == 999.0
    assert graph.calls == [
        ("out", 1013.0),
        ("in", 999.0),
        ("out", 1013.0),
        ("current", 999.0),
    ]
    assert "no authoritative project FPS setter" in caplog.text


def test_context_updates_node_and_workfile_instance_metadata(monkeypatch):
    """Cross-context updates persist only existing AYON instance metadata."""
    module = _load_context_module(monkeypatch, FakeNodegraph())
    first_node = object()
    second_node = object()
    stored = [
        (first_node, {"folderPath": "/old", "task": "layout", "keep": 1}),
        (second_node, {"keep": 2}),
    ]
    imprints = []
    monkeypatch.setattr(module.instances, "iter_instances", lambda: iter(stored))
    monkeypatch.setattr(
        module.instances,
        "imprint",
        lambda node, data: imprints.append((node, data)),
    )
    workfile_data = {"folderPath": "/old", "task": "layout", "keep": 3}
    workfile_updates = []
    monkeypatch.setattr(
        module,
        "get_workfile_instance_data",
        lambda: dict(workfile_data),
    )
    monkeypatch.setattr(
        module,
        "set_workfile_instance_data",
        lambda data: workfile_updates.append(data),
    )

    updated = module.update_instance_context_metadata("/new", "lighting")

    assert updated == 2
    assert imprints == [
        (
            first_node,
            {"folderPath": "/new", "task": "lighting", "keep": 1},
        )
    ]
    assert workfile_updates == [{"folderPath": "/new", "task": "lighting", "keep": 3}]


class FakeLifecycleContext:
    """Record lifecycle requests made to context helpers."""

    def __init__(self) -> None:
        self.applied: list[tuple[object, object]] = []
        self.updated: list[tuple[object, object]] = []
        self.fps_reports = 0
        self.frame_range_updates = 0
        self.instance_updates: list[tuple[str, str]] = []

    @staticmethod
    def get_current_context_data(host, data=None) -> dict:
        """Return a complete startup context."""
        output = dict(host.context)
        if data:
            output.update(data)
        return output

    @staticmethod
    def get_current_task_type() -> str:
        """Return the task type used by startup profile matching."""
        return "animation"

    def apply_context_settings(self, host, data=None) -> None:
        """Record timing/context application."""
        self.applied.append((host, data))

    def update_embedded_context(self, host, data=None) -> None:
        """Record pre-save persistence."""
        self.updated.append((host, data))

    def apply_current_frame_range(self) -> bool:
        """Record an explicit frame-range update."""
        self.frame_range_updates += 1
        return True

    def update_instance_context_metadata(
        self,
        folder_path: str,
        task_name: str,
    ) -> int:
        """Record explicit publish-instance metadata updates."""
        self.instance_updates.append((folder_path, task_name))
        return 2

    def log_fps_limitation(self) -> None:
        """Record open-scene FPS reporting."""
        self.fps_reports += 1


class FakeLifecycleBuilder:
    """Record automatic Workfile Builder starts."""

    def __init__(self) -> None:
        self.app_launch_starts = 0
        self.new_file_starts = 0

    def trigger_on_app_launch(self) -> bool:
        """Record an application-launch trigger."""
        self.app_launch_starts += 1
        return True

    def trigger_on_new_file(self) -> bool:
        """Record a new-file trigger."""
        self.new_file_starts += 1
        return True


class FakeLifecycleHost:
    """Minimal host used by lifecycle controller tests."""

    name = "katana"

    def __init__(self) -> None:
        self._has_been_setup = True
        self.context = {
            "project_name": "TestProject",
            "folder_path": "/assets/hero",
            "task_name": "layout",
        }


def _load_lifecycle_module(monkeypatch):
    """Load lifecycle logic with test doubles instead of Core UI modules."""
    emitted_events: list[str] = []
    core_lib = types.ModuleType("ayon_core.lib")
    core_lib.emit_event = lambda topic: emitted_events.append(topic)
    load_module = types.ModuleType("ayon_core.pipeline.load")
    load_module.any_outdated_containers = lambda: False
    workfile_module = types.ModuleType("ayon_core.pipeline.workfile")
    workfile_module.should_open_workfiles_tool_on_launch = lambda *_args: False
    monkeypatch.setitem(sys.modules, "ayon_core", types.ModuleType("ayon_core"))
    monkeypatch.setitem(sys.modules, "ayon_core.lib", core_lib)
    monkeypatch.setitem(
        sys.modules,
        "ayon_core.pipeline",
        types.ModuleType("ayon_core.pipeline"),
    )
    monkeypatch.setitem(sys.modules, "ayon_core.pipeline.load", load_module)
    monkeypatch.setitem(sys.modules, "ayon_core.pipeline.workfile", workfile_module)

    package_module = types.ModuleType("ayon_katana")
    package_module.__path__ = []
    api_package = types.ModuleType("ayon_katana.api")
    api_package.__path__ = []
    context_module = FakeLifecycleContext()
    builder_module = FakeLifecycleBuilder()
    startup_module = types.SimpleNamespace(
        has_requested_workfile=lambda: False,
        open_requested_workfile=lambda: None,
    )
    monkeypatch.setitem(sys.modules, "ayon_katana", package_module)
    monkeypatch.setitem(sys.modules, "ayon_katana.api", api_package)
    monkeypatch.setitem(sys.modules, "ayon_katana.api.context", context_module)
    monkeypatch.setitem(sys.modules, "ayon_katana.api.startup", startup_module)
    monkeypatch.setitem(
        sys.modules,
        "ayon_katana.api.workfile_template_builder",
        builder_module,
    )
    module = _load_module(
        monkeypatch,
        "ayon_katana.api.lifecycle",
        ROOT / "client" / "ayon_katana" / "api" / "lifecycle.py",
    )
    return module, context_module, builder_module, emitted_events


def test_lifecycle_task_changed_and_save_update_context(monkeypatch):
    """Task changes and pre-save update embedded context without saving."""
    module, context_module, _builder, emitted_events = _load_lifecycle_module(
        monkeypatch
    )
    host = FakeLifecycleHost()
    controller = module.LifecycleController(host)

    controller.on_task_changed(
        types.SimpleNamespace(
            data={"folder_path": "/shots/010", "task_name": "lighting"}
        )
    )
    controller.before_save()
    controller.on_save()

    assert context_module.applied == [
        (host, {"folder_path": "/shots/010", "task_name": "lighting"})
    ]
    assert context_module.updated == [(host, None)]
    assert emitted_events == ["before.save", "save"]


def test_cross_context_save_as_applies_selected_scene_updates(monkeypatch):
    """A graphical Save As applies only the artist-selected context updates."""
    module, context_module, _builder, _events = _load_lifecycle_module(monkeypatch)
    host = FakeLifecycleHost()
    controller = module.LifecycleController(host)
    target = {
        "project_name": "TestProject",
        "folder_path": "/shots/010",
        "task_name": "lighting",
    }
    window = object()
    prompt_calls = []
    monkeypatch.setattr(module, "_get_main_window", lambda: window)
    monkeypatch.setattr(
        module,
        "_prompt_context_change",
        lambda parent, source, destination: (
            prompt_calls.append((parent, source, destination))
            or {"frame_range": True, "instances": True}
        ),
    )

    controller.on_workfile_save_before(types.SimpleNamespace(data=target))
    host.context.update(target)
    controller.on_task_changed(types.SimpleNamespace(data=target))

    assert len(prompt_calls) == 1
    assert prompt_calls[0][0] is window
    assert prompt_calls[0][1]["folder_path"] == "/assets/hero"
    assert prompt_calls[0][2] == target
    assert context_module.updated == [(host, target)]
    assert context_module.frame_range_updates == 1
    assert context_module.instance_updates == [("/shots/010", "lighting")]
    assert context_module.applied == []
    assert controller._pending_workfile_save is None


def test_cross_context_save_as_cancel_and_headless_do_not_rewrite_instances(
    monkeypatch,
):
    """Cancel and headless Save As paths leave range and instances untouched."""
    module, context_module, _builder, _events = _load_lifecycle_module(monkeypatch)
    host = FakeLifecycleHost()
    controller = module.LifecycleController(host)
    target = {"folder_path": "/shots/020", "task_name": "comp"}

    monkeypatch.setattr(module, "_get_main_window", lambda: object())
    monkeypatch.setattr(module, "_prompt_context_change", lambda *_args: None)
    controller.on_workfile_save_before(target)
    controller.on_task_changed(target)

    monkeypatch.setattr(module, "_get_main_window", lambda: None)
    controller.on_workfile_save_before(target)
    controller.on_task_changed(target)

    assert context_module.frame_range_updates == 0
    assert context_module.instance_updates == []
    assert context_module.applied == []
    assert len(context_module.updated) == 2


def test_lifecycle_new_scene_applies_context_then_uses_new_file_trigger(monkeypatch):
    """New scenes use the separately configurable Core new-file trigger."""
    module, context_module, builder, emitted_events = _load_lifecycle_module(
        monkeypatch
    )
    host = FakeLifecycleHost()
    controller = module.LifecycleController(host)

    controller.on_new()
    controller.on_new_scene_loaded()

    assert context_module.applied == [(host, None)]
    assert builder.new_file_starts == 1
    assert builder.app_launch_starts == 0
    assert emitted_events == ["new"]


def test_startup_complete_opens_workfile_before_init_event(monkeypatch):
    """The launch-requested scene opens after host install and before AYON init."""
    module, _context_module, _builder, _events = _load_lifecycle_module(monkeypatch)
    order = []
    monkeypatch.setattr(
        module.startup,
        "open_requested_workfile",
        lambda: order.append("open"),
    )
    monkeypatch.setattr(module, "emit_event", lambda topic: order.append(topic))
    monkeypatch.setattr(module, "_get_main_window", lambda: None)
    controller = module.LifecycleController(FakeLifecycleHost())

    controller.on_startup_complete()

    assert order == ["open", "init"]


def test_startup_blank_scene_uses_app_launch_builder_trigger(monkeypatch):
    """A blank launch evaluates the Core application-launch profile once."""
    module, _context, builder, _events = _load_lifecycle_module(monkeypatch)
    monkeypatch.setattr(module, "_get_main_window", lambda: None)
    controller = module.LifecycleController(FakeLifecycleHost())

    controller.on_startup_complete()

    assert builder.app_launch_starts == 1
    assert builder.new_file_starts == 0


def test_startup_selected_workfile_suppresses_template_import(monkeypatch):
    """A launch-selected workfile must never be replaced by a template."""
    module, _context, builder, _events = _load_lifecycle_module(monkeypatch)
    monkeypatch.setattr(
        module.startup,
        "open_requested_workfile",
        lambda: "G:/projects/shot/lighting_v003.katana",
    )
    monkeypatch.setattr(module, "_get_main_window", lambda: None)
    controller = module.LifecycleController(FakeLifecycleHost())

    controller.on_startup_complete()

    assert builder.app_launch_starts == 0
    assert builder.new_file_starts == 0


def test_failed_selected_workfile_still_suppresses_template_import(monkeypatch):
    """A failed selected-workfile load must not fall through to a template."""
    module, _context, builder, _events = _load_lifecycle_module(monkeypatch)
    monkeypatch.setattr(module.startup, "has_requested_workfile", lambda: True)
    monkeypatch.setattr(module.startup, "open_requested_workfile", lambda: None)
    monkeypatch.setattr(module, "_get_main_window", lambda: None)
    controller = module.LifecycleController(FakeLifecycleHost())

    controller.on_startup_complete()

    assert builder.app_launch_starts == 0
    assert builder.new_file_starts == 0


def test_lifecycle_menu_install_is_deferred_and_host_guarded(monkeypatch):
    """Menu setup uses one deferred callback guarded by host installation."""
    module, _context_module, _builder, _events = _load_lifecycle_module(monkeypatch)
    deferred: list[tuple[int, object]] = []
    install_calls = []
    uninstall_calls = []
    host = FakeLifecycleHost()
    controller = module.LifecycleController(host)
    monkeypatch.setattr(module, "_get_main_window", object)
    monkeypatch.setattr(
        module,
        "_defer_call",
        lambda callback, delay=0: deferred.append((delay, callback)),
    )
    monkeypatch.setattr(module, "_install_menu", lambda: install_calls.append(True))
    monkeypatch.setattr(module, "_uninstall_menu", lambda: uninstall_calls.append(True))

    controller.install()

    assert len(deferred) == 1
    delay, callback = deferred.pop()
    assert delay == 2000

    host._has_been_setup = False
    callback()
    assert install_calls == []

    host._has_been_setup = True
    controller.install()
    _delay, callback = deferred.pop()
    callback()
    assert install_calls == [True]

    controller.uninstall()
    assert uninstall_calls == [True]


def test_lifecycle_deferred_ui_callbacks_respect_host_state(monkeypatch):
    """Deferred UI work cannot run after the host is uninstalled."""
    module, _context_module, _builder, _events = _load_lifecycle_module(monkeypatch)
    deferred: list[tuple[int, object]] = []
    ui_calls = []
    host = FakeLifecycleHost()
    controller = module.LifecycleController(host)
    monkeypatch.setattr(module, "_get_main_window", object)
    monkeypatch.setattr(
        module,
        "_defer_call",
        lambda callback, delay=0: deferred.append((delay, callback)),
    )

    assert controller._run_in_ui(lambda parent: ui_calls.append(parent))
    host._has_been_setup = False
    _delay, callback = deferred.pop()
    callback()

    assert ui_calls == []


def test_lifecycle_workfiles_profile_and_headless_mode(monkeypatch):
    """Profile-enabled Workfiles starts only schedule after a real main window."""
    module, context_module, _builder, emitted_events = _load_lifecycle_module(
        monkeypatch
    )
    profile_calls: list[tuple] = []
    deferred: list[tuple[int, object]] = []
    monkeypatch.setattr(
        module,
        "should_open_workfiles_tool_on_launch",
        lambda *args: profile_calls.append(args) or True,
    )
    monkeypatch.setattr(module, "_get_main_window", lambda: None)
    monkeypatch.setattr(
        module,
        "_defer_call",
        lambda callback, delay=0: deferred.append((delay, callback)),
    )
    host = FakeLifecycleHost()
    controller = module.LifecycleController(host)

    controller.on_startup_complete()

    assert emitted_events == ["init"]
    assert profile_calls == [("TestProject", "katana", "layout", "animation")]
    assert deferred == []
    assert context_module.applied == []


def test_lifecycle_profile_matching_defers_workfiles_once(monkeypatch):
    """A matching profile gets one deferred Workfiles call in graphical Katana."""
    module, _context_module, _builder, _events = _load_lifecycle_module(monkeypatch)
    monkeypatch.setattr(
        module,
        "should_open_workfiles_tool_on_launch",
        lambda *_args: True,
    )
    host = FakeLifecycleHost()
    window = object()
    deferred: list[tuple[int, object]] = []
    shown: list[object] = []
    monkeypatch.setattr(module, "_get_main_window", lambda: window)
    monkeypatch.setattr(
        module,
        "_defer_call",
        lambda callback, delay=0: deferred.append((delay, callback)),
    )
    controller = module.LifecycleController(host)
    monkeypatch.setattr(
        controller,
        "_show_workfiles",
        lambda parent: shown.append(parent),
    )

    controller.on_startup_complete()

    workfile_callbacks = [callback for delay, callback in deferred if delay == 0]
    menu_callbacks = [callback for delay, callback in deferred if delay == 2000]
    assert len(workfile_callbacks) == 1
    assert len(menu_callbacks) == 1
    workfile_callbacks[0]()
    assert shown == [window]


def test_lifecycle_reports_outdated_content_without_headless_ui(monkeypatch, caplog):
    """Headless open warnings wait for startup without importing UI tools."""
    module, _context_module, _builder, _events = _load_lifecycle_module(monkeypatch)
    deferred: list[tuple[int, object]] = []
    monkeypatch.setattr(module, "any_outdated_containers", lambda: True)
    monkeypatch.setattr(module, "_get_main_window", lambda: None)
    monkeypatch.setattr(
        module,
        "_defer_call",
        lambda callback, delay=0: deferred.append((delay, callback)),
    )
    host = FakeLifecycleHost()
    controller = module.LifecycleController(host)

    controller.on_open()

    assert deferred == []
    assert controller._outdated_content_pending is True
    assert "Katana scene has outdated content." in caplog.text


def _load_template_builder_module(monkeypatch):
    """Load Workfile Builder startup helpers with abstract Core test doubles."""
    katana_module = types.ModuleType("Katana")
    katana_module.NodegraphAPI = types.SimpleNamespace()
    monkeypatch.setitem(sys.modules, "Katana", katana_module)

    pipeline_module = types.ModuleType("ayon_core.pipeline")
    pipeline_module.registered_host = lambda: object()
    builder_core_module = types.ModuleType(
        "ayon_core.pipeline.workfile.workfile_template_builder"
    )

    class AbstractTemplateBuilder:
        """Minimal Workfile Builder base class."""

    class PlaceholderPlugin:
        """Minimal placeholder base class."""

    class TemplateProfileNotFound(Exception):
        """Signal an unmatched Workfile Builder profile."""

    builder_core_module.AbstractTemplateBuilder = AbstractTemplateBuilder
    builder_core_module.PlaceholderPlugin = PlaceholderPlugin
    builder_core_module.TemplateProfileNotFound = TemplateProfileNotFound
    monkeypatch.setitem(sys.modules, "ayon_core", types.ModuleType("ayon_core"))
    monkeypatch.setitem(sys.modules, "ayon_core.pipeline", pipeline_module)
    monkeypatch.setitem(
        sys.modules,
        "ayon_core.pipeline.workfile",
        types.ModuleType("ayon_core.pipeline.workfile"),
    )
    monkeypatch.setitem(
        sys.modules,
        "ayon_core.pipeline.workfile.workfile_template_builder",
        builder_core_module,
    )

    package_module = types.ModuleType("ayon_katana")
    package_module.__path__ = []
    api_package = types.ModuleType("ayon_katana.api")
    api_package.__path__ = []
    compat_module = types.ModuleType("ayon_katana.api.compat")
    containers_module = types.ModuleType("ayon_katana.api.containers")
    lib_module = types.ModuleType("ayon_katana.api.lib")
    monkeypatch.setitem(sys.modules, "ayon_katana", package_module)
    monkeypatch.setitem(sys.modules, "ayon_katana.api", api_package)
    monkeypatch.setitem(sys.modules, "ayon_katana.api.compat", compat_module)
    monkeypatch.setitem(sys.modules, "ayon_katana.api.containers", containers_module)
    monkeypatch.setitem(sys.modules, "ayon_katana.api.lib", lib_module)
    module = _load_module(
        monkeypatch,
        "ayon_katana.api.workfile_template_builder",
        ROOT / "client" / "ayon_katana" / "api" / "workfile_template_builder.py",
    )
    return module, TemplateProfileNotFound


def test_unmatched_workfile_builder_profile_does_nothing(monkeypatch):
    """Core template triggers ignore only an unmatched profile."""
    module, profile_not_found = _load_template_builder_module(monkeypatch)
    calls: list[str] = []

    class Builder:
        """Raise an unmatched profile from the Core trigger methods."""

        def __init__(self, _host) -> None:
            pass

        def trigger_on_app_launch(self) -> None:
            calls.append("app")
            raise profile_not_found("no match")

        def trigger_on_new_file(self) -> None:
            calls.append("new")
            raise profile_not_found("no match")

    monkeypatch.setattr(module, "KatanaTemplateBuilder", Builder)

    assert module.trigger_on_app_launch() is False
    assert module.trigger_on_new_file() is False
    assert calls == ["app", "new"]


def test_open_workfile_template_uses_core_confirmation_ui(monkeypatch):
    """The menu action delegates destructive template opening to Core UI."""
    module, _profile_not_found = _load_template_builder_module(monkeypatch)
    host = object()
    builder = object()
    main_window = object()
    calls = []
    monkeypatch.setattr(module, "registered_host", lambda: host)
    monkeypatch.setattr(module, "KatanaTemplateBuilder", lambda value: builder)

    tools_module = types.ModuleType("ayon_core.tools")
    tools_module.__path__ = []
    builder_tools_module = types.ModuleType("ayon_core.tools.workfile_template_build")
    builder_tools_module.open_template_ui = lambda value, parent: calls.append(
        (value, parent)
    )
    menu_module = types.ModuleType("ayon_katana.api.menu")
    menu_module.get_main_window = lambda: main_window
    monkeypatch.setitem(sys.modules, "ayon_core.tools", tools_module)
    monkeypatch.setitem(
        sys.modules,
        "ayon_core.tools.workfile_template_build",
        builder_tools_module,
    )
    monkeypatch.setitem(sys.modules, "ayon_katana.api.menu", menu_module)

    module.open_workfile_template()

    assert calls == [(builder, main_window)]


class FakeEventCallback:
    """Record deregistration of an AYON global event callback."""

    def __init__(self) -> None:
        self.deregistered = False

    def deregister(self) -> None:
        """Record callback cleanup."""
        self.deregistered = True


def _load_pipeline_module(monkeypatch):
    """Load the host pipeline with minimal Core registration test doubles."""
    registered_events: list[tuple[str, object, FakeEventCallback]] = []

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
    host_module.HostBase = HostBase
    host_module.IWorkfileHost = IWorkfileHost
    host_module.ILoadHost = ILoadHost
    host_module.IPublishHost = IPublishHost
    core_lib = types.ModuleType("ayon_core.lib")

    def _register_event_callback(topic, callback) -> FakeEventCallback:
        event_callback = FakeEventCallback()
        registered_events.append((topic, callback, event_callback))
        return event_callback

    core_lib.register_event_callback = _register_event_callback
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
    pyblish_api.register_host = lambda *_args: None
    pyblish_api.register_plugin_path = lambda *_args: None
    pyblish_api.deregister_host = lambda *_args: None
    pyblish_api.deregister_plugin_path = lambda *_args: None
    pyblish_module = types.ModuleType("pyblish")
    pyblish_module.api = pyblish_api
    monkeypatch.setitem(sys.modules, "pyblish", pyblish_module)
    monkeypatch.setitem(sys.modules, "pyblish.api", pyblish_api)

    package_module = types.ModuleType("ayon_katana")
    package_module.__path__ = []
    package_module.KATANA_HOST_DIR = str(ROOT / "client" / "ayon_katana")
    api_package = types.ModuleType("ayon_katana.api")
    api_package.__path__ = []
    context_module = types.ModuleType("ayon_katana.api.context")
    containers_module = types.ModuleType("ayon_katana.api.containers")
    lib_module = types.ModuleType("ayon_katana.api.lib")
    workio_module = types.ModuleType("ayon_katana.api.workio")
    callbacks_module = types.ModuleType("ayon_katana.api.callbacks")
    lifecycle_module = types.ModuleType("ayon_katana.api.lifecycle")

    class CallbackManager:
        """Record Katana callback manager lifecycle."""

        def __init__(self, lifecycle) -> None:
            self.lifecycle = lifecycle
            self.installs = 0
            self.uninstalls = 0

        def install(self) -> None:
            """Record installation."""
            self.installs += 1

        def uninstall(self) -> None:
            """Record cleanup."""
            self.uninstalls += 1

    class LifecycleController:
        """Provide the task-change callback used by host registration."""

        def __init__(self, _host) -> None:
            self.task_changed_calls = 0
            self.workfile_save_before_calls = 0
            self.installs = 0
            self.uninstalls = 0

        def install(self) -> None:
            self.installs += 1

        def uninstall(self) -> None:
            self.uninstalls += 1

        def on_task_changed(self, _event=None) -> None:
            """Record task-change dispatch."""
            self.task_changed_calls += 1

        def on_workfile_save_before(self, _event=None) -> None:
            """Record Workfiles Save As dispatch."""
            self.workfile_save_before_calls += 1

    callbacks_module.CallbackManager = CallbackManager
    lifecycle_module.LifecycleController = LifecycleController
    monkeypatch.setitem(sys.modules, "ayon_katana", package_module)
    monkeypatch.setitem(sys.modules, "ayon_katana.api", api_package)
    monkeypatch.setitem(sys.modules, "ayon_katana.api.context", context_module)
    monkeypatch.setitem(sys.modules, "ayon_katana.api.containers", containers_module)
    monkeypatch.setitem(sys.modules, "ayon_katana.api.lib", lib_module)
    monkeypatch.setitem(sys.modules, "ayon_katana.api.workio", workio_module)
    monkeypatch.setitem(sys.modules, "ayon_katana.api.callbacks", callbacks_module)
    monkeypatch.setitem(sys.modules, "ayon_katana.api.lifecycle", lifecycle_module)

    module = _load_module(
        monkeypatch,
        "ayon_katana.api.pipeline",
        ROOT / "client" / "ayon_katana" / "api" / "pipeline.py",
    )
    return module, registered_events


def test_host_registers_and_removes_task_changed_callback_once(monkeypatch):
    """Host installation wires AYON task changes without duplicate callbacks."""
    module, registered_events = _load_pipeline_module(monkeypatch)
    host = module.KatanaHost()

    host.install()
    host.install()

    assert len(registered_events) == 2
    topic, callback, task_event_callback = registered_events[0]
    assert topic == "taskChanged"
    callback()
    assert host._lifecycle.task_changed_calls == 1
    topic, callback, save_event_callback = registered_events[1]
    assert topic == "workfile.save.before"
    callback()
    assert host._lifecycle.workfile_save_before_calls == 1

    host.uninstall()
    assert task_event_callback.deregistered is True
    assert save_event_callback.deregistered is True
    assert host._callback_manager.installs == 1
    assert host._callback_manager.uninstalls == 1
    assert host._lifecycle.installs == 1
    assert host._lifecycle.uninstalls == 1
