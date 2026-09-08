"""Tests for Katana workfile Viewer thumbnail capture."""

from __future__ import annotations

import ast
import importlib.util
import sys
import types
from pathlib import Path

import pytest

ROOT = Path(__file__).parents[1]


class FakeViewer:
    """Minimal visible/focused Viewer tab substitute."""

    def __init__(self, *, visible: bool = True, descendants=None) -> None:
        self.visible = visible
        self.descendants = set(descendants or [])

    def isVisible(self) -> bool:
        """Return configured visibility."""
        return self.visible

    def isAncestorOf(self, widget) -> bool:
        """Return whether the supplied widget belongs to this Viewer."""
        return widget in self.descendants


class FakePixmap:
    """Small Qt pixmap substitute used by capture tests."""

    def __init__(self, width: int, height: int, *, save_result: bool = True) -> None:
        self._width = width
        self._height = height
        self.save_result = save_result
        self.scaled_args = None
        self.saved_path = None

    def isNull(self) -> bool:
        """Return whether the fake image is empty."""
        return False

    def width(self) -> int:
        """Return width."""
        return self._width

    def height(self) -> int:
        """Return height."""
        return self._height

    def scaled(self, *args):
        """Return a scaled pixmap and record the Qt arguments."""
        self.scaled_args = args
        ratio = min(args[0] / self._width, args[1] / self._height)
        return FakePixmap(
            max(1, int(self._width * ratio)),
            max(1, int(self._height * ratio)),
            save_result=self.save_result,
        )

    def save(self, path: str, file_format: str) -> bool:
        """Write deterministic bytes when saving succeeds."""
        self.saved_path = path
        if not self.save_result:
            return False
        Path(path).write_bytes(b"png")
        return file_format == "PNG"


class FakeWidget:
    """Qt widget substitute exposing only ``grab``."""

    def __init__(self, pixmap: FakePixmap) -> None:
        self.pixmap = pixmap

    def grab(self):
        """Return the configured captured image."""
        return self.pixmap


class FakeLog:
    """Capture plugin diagnostics."""

    def __init__(self) -> None:
        self.messages = []

    def debug(self, message, *args) -> None:
        """Record a debug message."""
        self.messages.append(("debug", message, args))

    def warning(self, message, *args) -> None:
        """Record a warning message."""
        self.messages.append(("warning", message, args))


def _load_thumbnail_api(monkeypatch):
    """Load the thumbnail helper in isolation."""
    module_name = "ayon_katana.api.thumbnail_test"
    module_path = ROOT / "client" / "ayon_katana" / "api" / "thumbnail.py"
    spec = importlib.util.spec_from_file_location(module_name, module_path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    monkeypatch.setitem(sys.modules, module_name, module)
    spec.loader.exec_module(module)
    return module


def _load_thumbnail_plugin(monkeypatch, thumbnail_module):
    """Load the thumbnail extractor with lightweight plugin dependencies."""
    pyblish_api = types.ModuleType("pyblish.api")
    pyblish_api.ExtractorOrder = 2.0
    pyblish = types.ModuleType("pyblish")
    pyblish.api = pyblish_api
    monkeypatch.setitem(sys.modules, "pyblish", pyblish)
    monkeypatch.setitem(sys.modules, "pyblish.api", pyblish_api)

    pipeline = types.ModuleType("ayon_core.pipeline")

    class OptionalMixin:
        """Minimal optional-plugin activation contract."""

        @staticmethod
        def is_active(data: dict) -> bool:
            return data.get("active", True)

    pipeline.OptionalPyblishPluginMixin = OptionalMixin
    ayon_core = types.ModuleType("ayon_core")
    ayon_core.pipeline = pipeline
    monkeypatch.setitem(sys.modules, "ayon_core", ayon_core)
    monkeypatch.setitem(sys.modules, "ayon_core.pipeline", pipeline)

    package = types.ModuleType("ayon_katana")
    package.__path__ = []
    api_package = types.ModuleType("ayon_katana.api")
    api_package.__path__ = []

    class KatanaInstancePlugin:
        """Minimal instance plugin base."""

    plugin_module = types.SimpleNamespace(KatanaInstancePlugin=KatanaInstancePlugin)
    api_package.plugin = plugin_module
    api_package.thumbnail = thumbnail_module
    monkeypatch.setitem(sys.modules, "ayon_katana", package)
    monkeypatch.setitem(sys.modules, "ayon_katana.api", api_package)

    module_name = "ayon_katana.plugins.publish.extract_workfile_thumbnail"
    module_path = (
        ROOT
        / "client"
        / "ayon_katana"
        / "plugins"
        / "publish"
        / "extract_workfile_thumbnail.py"
    )
    spec = importlib.util.spec_from_file_location(module_name, module_path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    monkeypatch.setitem(sys.modules, module_name, module)
    spec.loader.exec_module(module)
    return module


def test_viewer_tabs_use_layout_aware_katana_api(monkeypatch) -> None:
    """Viewer enumeration uses Katana's layout-aware tab API."""
    module = _load_thumbnail_api(monkeypatch)
    calls = []
    viewer = object()
    layouts = types.SimpleNamespace(
        GetTabs=lambda *args, **kwargs: calls.append((args, kwargs)) or [viewer]
    )
    katana = types.ModuleType("Katana")
    katana.UI4 = types.SimpleNamespace(App=types.SimpleNamespace(Layouts=layouts))
    monkeypatch.setitem(sys.modules, "Katana", katana)

    assert module.get_viewer_tabs() == [viewer]
    assert calls == [
        (
            ("Viewer",),
            {"includeFloating": True, "includeDockWidgets": True},
        )
    ]


def test_viewer_tabs_skip_when_katana_ui_is_unavailable(monkeypatch) -> None:
    """Headless Katana UI lookup failures behave like an unavailable Viewer."""
    module = _load_thumbnail_api(monkeypatch)

    def _raise(*_args, **_kwargs):
        raise AttributeError("'NoneType' object has no attribute 'centralWidget'")

    layouts = types.SimpleNamespace(GetTabs=_raise)
    katana = types.ModuleType("Katana")
    katana.UI4 = types.SimpleNamespace(App=types.SimpleNamespace(Layouts=layouts))
    monkeypatch.setitem(sys.modules, "Katana", katana)

    assert module.get_viewer_tabs() == []


def test_viewer_selection_prefers_focus_then_requires_unambiguous_visibility(
    monkeypatch,
) -> None:
    """Focused Viewer wins; otherwise only one visible Viewer is safe."""
    module = _load_thumbnail_api(monkeypatch)
    focus_child = object()
    focused = FakeViewer(descendants={focus_child})
    other = FakeViewer()
    monkeypatch.setattr(module, "get_viewer_tabs", lambda: [focused, other])
    monkeypatch.setattr(module, "_get_focus_widget", lambda: focus_child)

    viewer, reason = module.select_viewer_widget()
    assert viewer is focused
    assert reason == "focused Viewer"

    monkeypatch.setattr(module, "_get_focus_widget", lambda: None)
    viewer, reason = module.select_viewer_widget()
    assert viewer is None
    assert "ambiguous" in reason

    other.visible = False
    viewer, reason = module.select_viewer_widget()
    assert viewer is focused
    assert reason == "sole visible Viewer"


def test_capture_scales_longest_dimension_and_writes_png(monkeypatch) -> None:
    """Large Viewer captures preserve aspect ratio within 1024 pixels."""
    module = _load_thumbnail_api(monkeypatch)
    qtcore = types.ModuleType("qtpy.QtCore")
    qtcore.Qt = types.SimpleNamespace(
        KeepAspectRatio="keep",
        SmoothTransformation="smooth",
    )
    qtpy = types.ModuleType("qtpy")
    qtpy.QtCore = qtcore
    monkeypatch.setitem(sys.modules, "qtpy", qtpy)
    monkeypatch.setitem(sys.modules, "qtpy.QtCore", qtcore)

    pixmap = FakePixmap(2048, 1024)
    output_path = module.capture_viewer_thumbnail(FakeWidget(pixmap))
    try:
        assert Path(output_path).read_bytes() == b"png"
        assert pixmap.scaled_args == (1024, 1024, "keep", "smooth")
    finally:
        Path(output_path).unlink(missing_ok=True)


def test_capture_failure_does_not_leave_temp_png(monkeypatch, tmp_path) -> None:
    """A failed Qt save reports failure instead of publishing an empty PNG."""
    module = _load_thumbnail_api(monkeypatch)
    candidate = tmp_path / "failed.png"

    class NamedFile:
        """Context manager returning a deterministic temporary filename."""

        name = str(candidate)

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

    monkeypatch.setattr(
        module.tempfile,
        "NamedTemporaryFile",
        lambda **_kwargs: NamedFile(),
    )

    with pytest.raises(RuntimeError, match="could not save"):
        module.capture_viewer_thumbnail(
            FakeWidget(FakePixmap(100, 50, save_result=False))
        )

    assert not candidate.exists()


def test_extractor_preserves_existing_thumbnail(monkeypatch) -> None:
    """An artist/Core supplied thumbnail is never replaced."""
    thumbnail = types.SimpleNamespace(
        select_viewer_widget=lambda: (_ for _ in ()).throw(
            AssertionError("Viewer lookup should not run")
        )
    )
    module = _load_thumbnail_plugin(monkeypatch, thumbnail)
    context = types.SimpleNamespace(data={})
    instance = types.SimpleNamespace(
        data={"thumbnailPath": "existing.png"},
        context=context,
    )
    extractor = module.ExtractWorkfileThumbnail()
    extractor.log = FakeLog()

    extractor.process(instance)

    assert instance.data["thumbnailPath"] == "existing.png"
    assert context.data == {}


def test_extractor_registers_capture_for_cleanup(monkeypatch) -> None:
    """A captured PNG becomes the thumbnail and a Core cleanup path."""
    thumbnail = types.SimpleNamespace(
        select_viewer_widget=lambda: (object(), "focused Viewer"),
        capture_viewer_thumbnail=lambda _widget: "C:/temp/workfile.png",
    )
    module = _load_thumbnail_plugin(monkeypatch, thumbnail)
    context = types.SimpleNamespace(data={"cleanupFullPaths": []})
    instance = types.SimpleNamespace(data={}, context=context)
    extractor = module.ExtractWorkfileThumbnail()
    extractor.log = FakeLog()

    extractor.process(instance)

    assert instance.data["thumbnailPath"] == "C:/temp/workfile.png"
    assert context.data["cleanupFullPaths"] == ["C:/temp/workfile.png"]


def test_extractor_skips_ambiguous_or_failed_capture(monkeypatch) -> None:
    """Ambiguous Viewer selection and capture failures do not publish thumbnails."""
    thumbnail = types.SimpleNamespace(
        select_viewer_widget=lambda: (
            None,
            "multiple visible Viewer tabs are ambiguous",
        ),
        capture_viewer_thumbnail=lambda _widget: "unused.png",
    )
    module = _load_thumbnail_plugin(monkeypatch, thumbnail)
    instance = types.SimpleNamespace(data={}, context=types.SimpleNamespace(data={}))
    extractor = module.ExtractWorkfileThumbnail()
    extractor.log = FakeLog()

    extractor.process(instance)
    assert "thumbnailPath" not in instance.data

    thumbnail.select_viewer_widget = lambda: (object(), "focused Viewer")
    thumbnail.capture_viewer_thumbnail = lambda _widget: (_ for _ in ()).throw(
        RuntimeError("capture failed")
    )
    extractor.process(instance)
    assert "thumbnailPath" not in instance.data


def test_server_settings_enable_optional_workfile_thumbnail() -> None:
    """Workfile thumbnail extraction is optional and active by default."""
    source = (ROOT / "server" / "settings" / "main.py").read_text(encoding="utf-8")
    tree = ast.parse(source)
    assignment = next(
        node
        for node in tree.body
        if isinstance(node, ast.Assign)
        and any(
            isinstance(target, ast.Name) and target.id == "DEFAULT_VALUES"
            for target in node.targets
        )
    )
    defaults = ast.literal_eval(assignment.value)

    assert defaults["publish"]["ExtractWorkfileThumbnail"] == {
        "enabled": True,
        "optional": True,
        "active": True,
    }
