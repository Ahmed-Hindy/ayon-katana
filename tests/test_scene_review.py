"""Tests for Katana Scene Review creation and Viewer capture."""

from __future__ import annotations

import ast
import importlib.util
import sys
import types
from pathlib import Path

import pytest

ROOT = Path(__file__).parents[1]


def _load(monkeypatch, name: str, path: str):
    """Load a repository module under a controlled test module name."""
    spec = importlib.util.spec_from_file_location(name, ROOT / path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    monkeypatch.setitem(sys.modules, name, module)
    spec.loader.exec_module(module)
    return module


def _api(monkeypatch, **members):
    """Install a minimal mocked ``ayon_katana.api`` package."""
    package = types.ModuleType("ayon_katana")
    package.__path__ = []
    api = types.ModuleType("ayon_katana.api")
    api.__path__ = []
    for name, value in members.items():
        setattr(api, name, value)
        monkeypatch.setitem(sys.modules, f"ayon_katana.api.{name}", value)
    package.api = api
    monkeypatch.setitem(sys.modules, "ayon_katana", package)
    monkeypatch.setitem(sys.modules, "ayon_katana.api", api)


def _pyblish(monkeypatch):
    """Install the Pyblish order constants required by plugin imports."""
    api = types.ModuleType("pyblish.api")
    api.CollectorOrder = 0.0
    api.ValidatorOrder = 1.0
    api.ExtractorOrder = 2.0
    package = types.ModuleType("pyblish")
    package.api = api
    monkeypatch.setitem(sys.modules, "pyblish", package)
    monkeypatch.setitem(sys.modules, "pyblish.api", api)


def _capture_runtime(monkeypatch, current=42.0):
    """Install minimal Katana and Qt frame-control runtime stubs."""
    times = []

    class NodegraphAPI:
        value = current

        @classmethod
        def GetCurrentTime(cls):
            """Return the mocked current Katana frame."""
            return cls.value

        @classmethod
        def SetCurrentTime(cls, value):
            """Set and record the mocked current Katana frame."""
            cls.value = value
            times.append(value)

    katana = types.ModuleType("Katana")
    katana.NodegraphAPI = NodegraphAPI
    monkeypatch.setitem(sys.modules, "Katana", katana)
    qtwidgets = types.ModuleType("qtpy.QtWidgets")
    qtwidgets.QApplication = types.SimpleNamespace(
        instance=lambda: types.SimpleNamespace(processEvents=lambda: None)
    )
    qtpy = types.ModuleType("qtpy")
    qtpy.QtWidgets = qtwidgets
    monkeypatch.setitem(sys.modules, "qtpy", qtpy)
    monkeypatch.setitem(sys.modules, "qtpy.QtWidgets", qtwidgets)
    return NodegraphAPI, times


def test_review_sequence_restores_frame_and_cleans_partial_failure(
    monkeypatch, tmp_path
) -> None:
    """Restore the original frame and remove partial output on failure."""
    module = _load(
        monkeypatch, "ayon_katana.api.review", "client/ayon_katana/api/review.py"
    )
    viewport = object()
    monkeypatch.setattr(module, "_select_review_viewport", lambda _viewer: viewport)

    def write_image(candidate, output_path):
        """Write one fake PNG and fail on the second frame."""
        assert candidate is viewport
        if output_path.name.endswith("1002.png"):
            raise RuntimeError("capture failed")
        output_path.write_bytes(b"png")

    monkeypatch.setattr(module, "_write_viewport_image", write_image)
    synchronized = []
    monkeypatch.setattr(
        module,
        "_synchronize_viewport",
        lambda candidate: synchronized.append(candidate),
    )
    nodegraph, times = _capture_runtime(monkeypatch)

    with pytest.raises(RuntimeError, match="capture failed"):
        module.capture_viewer_sequence(object(), tmp_path, "reviewMain", 1001, 1003, 1)

    assert not (tmp_path / "reviewMain.1001.png").exists()
    assert nodegraph.value == 42.0
    assert times == [1001, 1002, 42.0]
    assert synchronized == [viewport, viewport, viewport]
    assert module.frame_numbers(7, 9, 1) == (7, 8, 9)


def test_review_sequence_cleans_output_when_restore_sync_fails(
    monkeypatch, tmp_path
) -> None:
    """A failed Viewer restoration cannot leave completed review PNGs behind."""
    module = _load(
        monkeypatch, "ayon_katana.api.review", "client/ayon_katana/api/review.py"
    )
    viewport = object()
    monkeypatch.setattr(module, "_select_review_viewport", lambda _viewer: viewport)
    monkeypatch.setattr(
        module,
        "_write_viewport_image",
        lambda _candidate, output_path: output_path.write_bytes(b"png"),
    )
    sync_count = {"value": 0}

    def synchronize(_candidate):
        sync_count["value"] += 1
        if sync_count["value"] == 2:
            raise RuntimeError("restore sync failed")

    monkeypatch.setattr(module, "_synchronize_viewport", synchronize)
    nodegraph, _times = _capture_runtime(monkeypatch)

    with pytest.raises(RuntimeError, match="restore sync failed"):
        module.capture_viewer_sequence(object(), tmp_path, "reviewMain", 1001, 1001, 1)

    assert not (tmp_path / "reviewMain.1001.png").exists()
    assert nodegraph.value == 42.0


def test_review_sequence_cleans_output_when_restore_time_fails(
    monkeypatch, tmp_path
) -> None:
    """A failed timeline restoration cannot leave completed review PNGs behind."""
    module = _load(
        monkeypatch, "ayon_katana.api.review", "client/ayon_katana/api/review.py"
    )
    viewport = object()
    monkeypatch.setattr(module, "_select_review_viewport", lambda _viewer: viewport)
    monkeypatch.setattr(module, "_synchronize_viewport", lambda _candidate: None)
    monkeypatch.setattr(
        module,
        "_write_viewport_image",
        lambda _candidate, output_path: output_path.write_bytes(b"png"),
    )
    nodegraph, _times = _capture_runtime(monkeypatch)
    set_current_time = nodegraph.SetCurrentTime

    def fail_restore(value):
        """Reject restoration to the original mocked frame."""
        if value == 42.0:
            raise RuntimeError("restore time failed")
        set_current_time(value)

    monkeypatch.setattr(nodegraph, "SetCurrentTime", fail_restore)

    with pytest.raises(RuntimeError, match="restore time failed"):
        module.capture_viewer_sequence(object(), tmp_path, "reviewMain", 1001, 1001, 1)

    assert not (tmp_path / "reviewMain.1001.png").exists()


def test_review_sequence_rejects_unsafe_product_names(monkeypatch, tmp_path) -> None:
    """Reject product names that can escape the review staging directory."""
    module = _load(
        monkeypatch, "ayon_katana.api.review", "client/ayon_katana/api/review.py"
    )
    monkeypatch.setattr(
        module,
        "_select_review_viewport",
        lambda _viewer: pytest.fail("viewport selection should not run"),
    )

    for product_name in ("", ".", "..", "../escape", "..\\escape", "/escape"):
        with pytest.raises(ValueError, match="single non-empty filename component"):
            module.capture_viewer_sequence(
                object(), tmp_path, product_name, 1001, 1001, 1
            )


def test_review_viewport_requires_one_visible_candidate(monkeypatch) -> None:
    """Scene Review resolves capture viewports through Katana's Viewer API."""
    module = _load(
        monkeypatch, "ayon_katana.api.review", "client/ayon_katana/api/review.py"
    )

    def candidate(*, visible=True, width=640, height=360):
        return types.SimpleNamespace(
            grabFramebuffer=lambda: object(),
            isVisible=lambda: visible,
            width=lambda: width,
            height=lambda: height,
        )

    delegate = object()

    def viewer_for(viewports):
        return types.SimpleNamespace(
            getNumberOfViewerDelegates=lambda: 1,
            getViewerDelegateByIndex=lambda _index: delegate,
            getViewports=lambda _delegate: list(viewports),
            getViewportWidget=lambda viewport, _delegate: viewport,
        )

    selected = candidate()
    viewer = viewer_for([candidate(visible=False), candidate(width=0), selected])
    assert module._select_review_viewport(viewer) is selected

    with pytest.raises(RuntimeError, match="found 0"):
        module._select_review_viewport(viewer_for([]))

    with pytest.raises(RuntimeError, match="found 2"):
        module._select_review_viewport(viewer_for([candidate(), candidate()]))


def test_review_viewport_sync_uses_two_katana_repaint_passes(monkeypatch) -> None:
    """Hydra capture flushes Katana and repaints twice before writing the image."""
    module = _load(
        monkeypatch, "ayon_katana.api.review", "client/ayon_katana/api/review.py"
    )
    events = []
    katana = types.ModuleType("Katana")
    katana.Utils = types.SimpleNamespace(
        EventModule=types.SimpleNamespace(
            ProcessAllEvents=lambda: events.append("katana")
        )
    )
    monkeypatch.setitem(sys.modules, "Katana", katana)
    qtwidgets = types.ModuleType("qtpy.QtWidgets")
    qtwidgets.QApplication = types.SimpleNamespace(
        instance=lambda: types.SimpleNamespace(
            processEvents=lambda: events.append("qt")
        )
    )
    qtpy = types.ModuleType("qtpy")
    qtpy.QtWidgets = qtwidgets
    monkeypatch.setitem(sys.modules, "qtpy", qtpy)
    monkeypatch.setitem(sys.modules, "qtpy.QtWidgets", qtwidgets)
    viewport = types.SimpleNamespace(repaint=lambda: events.append("repaint"))

    module._synchronize_viewport(viewport)

    assert events == [
        "katana",
        "repaint",
        "qt",
        "katana",
        "repaint",
        "qt",
    ]


def test_review_sequence_fails_without_live_viewport(monkeypatch, tmp_path) -> None:
    """Scene Review fails instead of falling back to generic widget capture."""
    module = _load(
        monkeypatch, "ayon_katana.api.review", "client/ayon_katana/api/review.py"
    )

    def no_viewport(_viewer):
        raise RuntimeError(
            "Scene Review requires exactly one visible capture viewport; found 0."
        )

    monkeypatch.setattr(module, "_select_review_viewport", no_viewport)
    with pytest.raises(RuntimeError, match="found 0"):
        module.capture_viewer_sequence(object(), tmp_path, "reviewMain", 1001, 1001, 1)


def test_review_viewport_capture_writes_framebuffer(monkeypatch, tmp_path) -> None:
    """Write the Katana viewport framebuffer directly as PNG."""
    module = _load(
        monkeypatch, "ayon_katana.api.review", "client/ayon_katana/api/review.py"
    )

    class Image:
        def isNull(self) -> bool:
            """Return whether the fake image is empty."""
            return False

        def save(self, path, _format):
            """Write one fake PNG payload."""
            Path(path).write_bytes(b"png")
            return True

    viewport = types.SimpleNamespace(grabFramebuffer=lambda: Image())
    output = tmp_path / "capture.png"
    module._write_viewport_image(viewport, output)

    assert output.read_bytes() == b"png"


def test_review_viewport_capture_failure_removes_stale_output(
    monkeypatch, tmp_path
) -> None:
    """A failed framebuffer capture cannot leave an older PNG behind."""
    module = _load(
        monkeypatch, "ayon_katana.api.review", "client/ayon_katana/api/review.py"
    )
    output = tmp_path / "failed.png"
    output.write_bytes(b"stale")
    viewport = types.SimpleNamespace(
        grabFramebuffer=lambda: (_ for _ in ()).throw(RuntimeError("grab failed"))
    )

    with pytest.raises(RuntimeError, match="could not capture"):
        module._write_viewport_image(viewport, output)

    assert not output.exists()


def test_review_viewport_capture_rejects_unremovable_stale_output(
    monkeypatch, tmp_path
) -> None:
    """Do not accept capture over an existing file that cannot be removed."""
    module = _load(
        monkeypatch, "ayon_katana.api.review", "client/ayon_katana/api/review.py"
    )
    output = tmp_path / "locked.png"
    output.write_bytes(b"stale")
    original_unlink = Path.unlink

    def fail_target_unlink(path, *args, **kwargs):
        """Simulate a stale capture file that cannot be replaced."""
        if path == output:
            raise PermissionError("locked")
        return original_unlink(path, *args, **kwargs)

    monkeypatch.setattr(Path, "unlink", fail_target_unlink)
    viewport = types.SimpleNamespace(
        grabFramebuffer=lambda: pytest.fail("capture should not start")
    )

    with pytest.raises(RuntimeError, match="cannot replace existing output"):
        module._write_viewport_image(viewport, output)

    assert output.read_bytes() == b"stale"


def test_review_viewport_capture_requires_output_file(monkeypatch, tmp_path) -> None:
    """A silent framebuffer-save failure is reported and cleaned up."""
    module = _load(
        monkeypatch, "ayon_katana.api.review", "client/ayon_katana/api/review.py"
    )
    image = types.SimpleNamespace(isNull=lambda: False, save=lambda *_args: True)
    viewport = types.SimpleNamespace(grabFramebuffer=lambda: image)
    output = tmp_path / "missing.png"

    with pytest.raises(RuntimeError, match="produced no image"):
        module._write_viewport_image(viewport, output)

    assert not output.exists()


def _collector(monkeypatch, project_range=(1, 2)):
    """Load the Scene Review collector with lightweight host stubs."""
    _pyblish(monkeypatch)

    class KatanaInstancePlugin:
        pass

    plugin = types.SimpleNamespace(KatanaInstancePlugin=KatanaInstancePlugin)
    render = types.SimpleNamespace(get_project_frame_range=lambda: project_range)
    _api(monkeypatch, plugin=plugin, render=render)
    return _load(
        monkeypatch,
        "ayon_katana.plugins.publish.collect_review",
        "client/ayon_katana/plugins/publish/collect_review.py",
    )


def test_collect_review_normalizes_task_range_handles_and_fps(monkeypatch) -> None:
    """Normalize task ranges, handles, FPS, and review families."""
    module = _collector(monkeypatch)
    assert module.CollectReview.families == ["katana.review"]
    instance = types.SimpleNamespace(
        data={
            "taskEntity": {
                "attrib": {
                    "frameStart": 1001,
                    "frameEnd": 1005,
                    "handleStart": 8,
                    "handleEnd": 4,
                    "fps": 25,
                }
            },
            "families": [],
        },
        context=types.SimpleNamespace(data={}),
    )

    module.CollectReview().process(instance)

    assert instance.data["frameStartHandle"] == 993
    assert instance.data["frameEndHandle"] == 1009
    assert instance.data["byFrameStep"] == 1
    assert instance.data["fps"] == 25.0
    assert instance.data["review"] is True
    assert instance.data["families"] == ["review", "katana.review"]


def test_collect_review_project_fallback_still_requires_fps(monkeypatch) -> None:
    """Use the project range fallback without weakening FPS requirements."""
    module = _collector(monkeypatch, (10, 12))
    instance = types.SimpleNamespace(
        data={"families": []}, context=types.SimpleNamespace(data={"fps": 24})
    )
    module.CollectReview().process(instance)
    assert (instance.data["frameStartHandle"], instance.data["frameEndHandle"]) == (
        10,
        12,
    )
    missing_fps = types.SimpleNamespace(
        data={"families": []}, context=types.SimpleNamespace(data={})
    )
    with pytest.raises(RuntimeError, match="requires a valid AYON task FPS"):
        module.CollectReview().process(missing_fps)

    for fps in (float("nan"), float("inf"), float("-inf"), 0, -1):
        invalid_fps = types.SimpleNamespace(
            data={"families": []}, context=types.SimpleNamespace(data={"fps": fps})
        )
        with pytest.raises(RuntimeError, match="finite positive AYON task FPS"):
            module.CollectReview().process(invalid_fps)


def test_review_creator_marks_review_product(monkeypatch) -> None:
    """Mark created Scene Review instances for AYON review processing."""

    class KatanaCreator:
        def create(self, _product_name, instance_data, _pre_create_data):
            """Return the created instance data for assertions."""
            return instance_data

    _api(monkeypatch, plugin=types.SimpleNamespace(KatanaCreator=KatanaCreator))
    module = _load(
        monkeypatch,
        "ayon_katana.plugins.create.create_review",
        "client/ayon_katana/plugins/create/create_review.py",
    )
    result = module.CreateReview().create("reviewMain", {"families": []}, {})
    assert result["review"] is True
    assert result["families"] == ["review", "katana.review"]


def test_review_extractor_emits_core_compatible_representation(
    monkeypatch, tmp_path
) -> None:
    """Emit a review-tagged PNG representation with validated metadata."""
    _pyblish(monkeypatch)

    class KatanaExtractorPlugin:
        def staging_dir(self, _instance):
            """Return the temporary extraction directory."""
            return str(tmp_path)

    captured = {}

    def capture(*args, **kwargs):
        """Record capture arguments and return representative frame names."""
        captured["args"] = args
        return ["reviewMain.1001.png", "reviewMain.1002.png"]

    _api(
        monkeypatch,
        plugin=types.SimpleNamespace(KatanaExtractorPlugin=KatanaExtractorPlugin),
        review=types.SimpleNamespace(capture_viewer_sequence=capture),
        thumbnail=types.SimpleNamespace(
            select_viewer_widget=lambda: (object(), "focused Viewer")
        ),
    )
    publish = types.ModuleType("ayon_core.pipeline.publish")
    publish.PublishError = RuntimeError
    pipeline = types.ModuleType("ayon_core.pipeline")
    pipeline.publish = publish
    core = types.ModuleType("ayon_core")
    core.pipeline = pipeline
    monkeypatch.setitem(sys.modules, "ayon_core", core)
    monkeypatch.setitem(sys.modules, "ayon_core.pipeline", pipeline)
    monkeypatch.setitem(sys.modules, "ayon_core.pipeline.publish", publish)

    module = _load(
        monkeypatch,
        "ayon_katana.plugins.publish.extract_review_capture",
        "client/ayon_katana/plugins/publish/extract_review_capture.py",
    )
    assert module.ExtractReviewCapture.families == ["katana.review"]
    instance = types.SimpleNamespace(
        data={
            "productName": "reviewMain",
            "frameStartHandle": 1001,
            "frameEndHandle": 1002,
            "byFrameStep": 1,
            "fps": 25,
        }
    )
    extractor = module.ExtractReviewCapture()
    extractor.log = types.SimpleNamespace(info=lambda *_args, **_kwargs: None)
    extractor.process(instance)

    representation = instance.data["representations"][0]
    assert captured["args"][2:] == ("reviewMain", 1001, 1002, 1)
    assert representation["tags"] == ["review"]
    assert representation["files"] == [
        "reviewMain.1001.png",
        "reviewMain.1002.png",
    ]
    assert representation["stagingDir"] == str(tmp_path)
    assert representation["fps"] == 25.0

    captured.clear()
    invalid_instance = types.SimpleNamespace(
        data={
            "productName": "reviewMain",
            "frameStartHandle": 1001,
            "frameEndHandle": 1002,
            "byFrameStep": 1,
            "fps": float("nan"),
        }
    )
    with pytest.raises(RuntimeError, match="finite positive AYON task FPS"):
        extractor.process(invalid_instance)
    assert captured == {}


def test_review_validator_requires_positive_fps_and_visible_viewer(monkeypatch) -> None:
    """Reject invalid FPS metadata and missing visible Viewer widgets."""
    _pyblish(monkeypatch)

    class KatanaInstancePlugin:
        pass

    class OptionalMixin:
        @staticmethod
        def is_active(_data):
            """Keep the optional validator active in the test runtime."""
            return True

    class ValidationError(RuntimeError):
        def __init__(self, message, *, title=None):
            """Store the validation title alongside the message."""
            super().__init__(message)
            self.title = title

    pipeline = types.ModuleType("ayon_core.pipeline")
    pipeline.OptionalPyblishPluginMixin = OptionalMixin
    publish = types.ModuleType("ayon_core.pipeline.publish")
    publish.PublishValidationError = ValidationError
    core = types.ModuleType("ayon_core")
    core.pipeline = pipeline
    pipeline.publish = publish
    monkeypatch.setitem(sys.modules, "ayon_core", core)
    monkeypatch.setitem(sys.modules, "ayon_core.pipeline", pipeline)
    monkeypatch.setitem(sys.modules, "ayon_core.pipeline.publish", publish)

    review = types.SimpleNamespace(
        frame_numbers=lambda start, end, step: tuple(range(start, end + 1, step))
    )
    thumbnail = types.SimpleNamespace(
        select_viewer_widget=lambda: (object(), "focused Viewer")
    )
    _api(
        monkeypatch,
        plugin=types.SimpleNamespace(KatanaInstancePlugin=KatanaInstancePlugin),
        review=review,
        thumbnail=thumbnail,
    )
    module = _load(
        monkeypatch,
        "ayon_katana.plugins.publish.validate_review",
        "client/ayon_katana/plugins/publish/validate_review.py",
    )
    assert module.ValidateReview.families == ["katana.review"]
    instance = types.SimpleNamespace(
        data={
            "frameStartHandle": 1001,
            "frameEndHandle": 1002,
            "byFrameStep": 1,
            "fps": 25,
        }
    )

    module.ValidateReview().process(instance)

    for fps in (0, -1, float("nan"), float("inf"), float("-inf")):
        instance.data["fps"] = fps
        with pytest.raises(ValidationError, match="finite positive"):
            module.ValidateReview().process(instance)

    instance.data["fps"] = 25
    module.thumbnail.select_viewer_widget = lambda: (None, "no Viewer tab is available")
    with pytest.raises(ValidationError, match="cannot select a Katana Viewer"):
        module.ValidateReview().process(instance)


def test_scene_review_server_models_register_all_plugins() -> None:
    """Register all Scene Review plugins in the server settings models."""
    create_source = (ROOT / "server/settings/create.py").read_text(encoding="utf-8")
    publish_source = (ROOT / "server/settings/publish.py").read_text(encoding="utf-8")
    assert "CreateReview: EnabledPluginModel" in create_source
    assert "CollectReview: EnabledPluginModel" in publish_source
    assert "ValidateReview: OptionalPluginModel" in publish_source
    assert "ExtractReviewCapture: EnabledPluginModel" in publish_source


def test_scene_review_server_defaults_are_enabled() -> None:
    """Enable the Scene Review plugin defaults in server settings."""
    tree = ast.parse((ROOT / "server/settings/main.py").read_text(encoding="utf-8"))
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
    assert defaults["create"]["CreateReview"] == {"enabled": True}
    assert defaults["publish"]["CollectReview"] == {"enabled": True}
    assert defaults["publish"]["ValidateReview"] == {
        "enabled": True,
        "optional": False,
        "active": True,
    }
    assert defaults["publish"]["ExtractReviewCapture"] == {"enabled": True}
