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
    spec = importlib.util.spec_from_file_location(name, ROOT / path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    monkeypatch.setitem(sys.modules, name, module)
    spec.loader.exec_module(module)
    return module


def _api(monkeypatch, **members):
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
    api = types.ModuleType("pyblish.api")
    api.CollectorOrder = 0.0
    api.ValidatorOrder = 1.0
    api.ExtractorOrder = 2.0
    package = types.ModuleType("pyblish")
    package.api = api
    monkeypatch.setitem(sys.modules, "pyblish", package)
    monkeypatch.setitem(sys.modules, "pyblish.api", api)


def _capture_runtime(monkeypatch, current=42.0):
    times = []

    class NodegraphAPI:
        value = current

        @classmethod
        def GetCurrentTime(cls):
            return cls.value

        @classmethod
        def SetCurrentTime(cls, value):
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
    thumbnail = types.ModuleType("ayon_katana.api.thumbnail")

    def capture(_widget, output_path):
        path = Path(output_path)
        if path.name.endswith("1002.png"):
            raise RuntimeError("capture failed")
        path.write_bytes(b"png")
        return str(path)

    thumbnail.capture_viewer_image = capture
    _api(monkeypatch, thumbnail=thumbnail)
    module = _load(
        monkeypatch, "ayon_katana.api.review", "client/ayon_katana/api/review.py"
    )
    nodegraph, times = _capture_runtime(monkeypatch)

    with pytest.raises(RuntimeError, match="capture failed"):
        module.capture_viewer_sequence(object(), tmp_path, "reviewMain", 1001, 1003, 1)

    assert not (tmp_path / "reviewMain.1001.png").exists()
    assert nodegraph.value == 42.0
    assert times == [1001, 1002, 42.0]
    assert module.frame_numbers(7, 9, 1) == (7, 8, 9)


def _collector(monkeypatch, project_range=(1, 2)):
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
    module = _collector(monkeypatch)
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


def test_review_creator_marks_review_product(monkeypatch) -> None:
    class KatanaCreator:
        def create(self, _product_name, instance_data, _pre_create_data):
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
    _pyblish(monkeypatch)

    class KatanaExtractorPlugin:
        def staging_dir(self, _instance):
            return str(tmp_path)

    captured = {}

    def capture(*args, **kwargs):
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


def test_review_validator_requires_positive_fps_and_visible_viewer(monkeypatch) -> None:
    _pyblish(monkeypatch)

    class KatanaInstancePlugin:
        pass

    class OptionalMixin:
        @staticmethod
        def is_active(_data):
            return True

    class ValidationError(RuntimeError):
        def __init__(self, message, *, title=None):
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
    instance = types.SimpleNamespace(
        data={
            "frameStartHandle": 1001,
            "frameEndHandle": 1002,
            "byFrameStep": 1,
            "fps": 25,
        }
    )

    module.ValidateReview().process(instance)

    instance.data["fps"] = 0
    with pytest.raises(ValidationError, match="positive"):
        module.ValidateReview().process(instance)

    instance.data["fps"] = 25
    module.thumbnail.select_viewer_widget = lambda: (None, "no Viewer tab is available")
    with pytest.raises(ValidationError, match="cannot select a Katana Viewer"):
        module.ValidateReview().process(instance)


def test_scene_review_server_models_register_all_plugins() -> None:
    create_source = (ROOT / "server/settings/create.py").read_text(encoding="utf-8")
    publish_source = (ROOT / "server/settings/publish.py").read_text(encoding="utf-8")
    assert "CreateReview: EnabledPluginModel" in create_source
    assert "CollectReview: EnabledPluginModel" in publish_source
    assert "ValidateReview: OptionalPluginModel" in publish_source
    assert "ExtractReviewCapture: EnabledPluginModel" in publish_source


def test_scene_review_server_defaults_are_enabled() -> None:
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
