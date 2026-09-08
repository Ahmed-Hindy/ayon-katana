"""Tests for Katana Deadline submission behavior."""

from __future__ import annotations

import importlib.util
import sys
import types
from pathlib import Path

import pytest


def _load_submitter(monkeypatch):
    """Load the submitter with minimal AYON and Deadline stubs."""

    class FakeAbstractSubmitDeadline:
        """Stand in for AYON Deadline's abstract submitter."""

        def process(self, instance) -> None:
            """Record the instance that would be submitted to Deadline."""
            self.base_process_instance = instance

    class FakeMixin:
        """Stand in for AYON's Pyblish settings mixin."""

    pyblish_api = types.ModuleType("pyblish.api")
    pyblish_api.IntegratorOrder = 2.0
    pyblish_module = types.ModuleType("pyblish")
    pyblish_module.api = pyblish_api

    ayon_core_pipeline = types.ModuleType("ayon_core.pipeline")
    ayon_core_pipeline.AYONPyblishPluginMixin = FakeMixin
    ayon_core_module = types.ModuleType("ayon_core")
    ayon_core_module.pipeline = ayon_core_pipeline

    abstract_module = types.ModuleType("ayon_deadline.abstract_submit_deadline")
    abstract_module.AbstractSubmitDeadline = FakeAbstractSubmitDeadline
    deadline_module = types.ModuleType("ayon_deadline")
    deadline_module.abstract_submit_deadline = abstract_module

    katana_module = types.ModuleType("ayon_katana")
    katana_module.__path__ = []
    katana_api_module = types.ModuleType("ayon_katana.api")
    katana_api_module.__path__ = []
    render_module = types.ModuleType("ayon_katana.api.render")
    katana_api_module.render = render_module

    monkeypatch.setitem(sys.modules, "pyblish", pyblish_module)
    monkeypatch.setitem(sys.modules, "pyblish.api", pyblish_api)
    monkeypatch.setitem(sys.modules, "ayon_core", ayon_core_module)
    monkeypatch.setitem(sys.modules, "ayon_core.pipeline", ayon_core_pipeline)
    monkeypatch.setitem(sys.modules, "ayon_deadline", deadline_module)
    monkeypatch.setitem(sys.modules, "ayon_katana", katana_module)
    monkeypatch.setitem(sys.modules, "ayon_katana.api", katana_api_module)
    monkeypatch.setitem(sys.modules, "ayon_katana.api.render", render_module)
    monkeypatch.setitem(
        sys.modules,
        "ayon_deadline.abstract_submit_deadline",
        abstract_module,
    )

    module_path = (
        Path(__file__).parents[1]
        / "client"
        / "ayon_katana"
        / "plugins"
        / "deadline"
        / "submit_katana_deadline.py"
    )
    module_spec = importlib.util.spec_from_file_location(
        "ayon_katana.plugins.deadline.submit_katana_deadline",
        module_path,
    )
    assert module_spec is not None
    assert module_spec.loader is not None
    module = importlib.util.module_from_spec(module_spec)
    module_spec.loader.exec_module(module)
    return module


def test_submitter_runs_after_core_integration(monkeypatch) -> None:
    """Published-workfile resolution must run after Core integration."""
    module = _load_submitter(monkeypatch)

    assert module.KatanaSubmitDeadline.order == pytest.approx(2.05)


@pytest.mark.parametrize("release", ("Katana8.0v1", "Katana9.0v1"))
def test_commandline_payload_uses_release_executable_scene_and_render_node(
    monkeypatch, tmp_path, release
) -> None:
    """Katana 8/9 submissions must use the launch executable and render node."""
    module = _load_submitter(monkeypatch)
    executable = tmp_path / release / "bin" / "katanaBin.exe"
    executable.parent.mkdir(parents=True)
    executable.touch()
    monkeypatch.setattr(
        module.render,
        "get_katana_executable",
        lambda: executable,
        raising=False,
    )

    scene_path = tmp_path / "scene.katana"
    plugin = module.KatanaSubmitDeadline()
    plugin.scene_path = str(scene_path)
    plugin._instance = types.SimpleNamespace(data={"render_node": "renderMain"})

    payload = plugin.get_plugin_info()

    assert payload["Executable"] == str(executable)
    assert payload["SceneFile"] == str(scene_path)
    assert payload["StartupDirectory"] == str(executable.parent)
    assert f'--katana-file="{scene_path}"' in payload["Arguments"]
    assert '--render-node="renderMain"' in payload["Arguments"]


def test_process_skips_non_farm_instance(monkeypatch) -> None:
    """Local render instances must not enter Deadline's submission base class."""
    module = _load_submitter(monkeypatch)
    debug_messages = []
    plugin = module.KatanaSubmitDeadline()
    plugin.log = types.SimpleNamespace(debug=debug_messages.append)
    instance = types.SimpleNamespace(data={"farm": False, "files": ["unused.exr"]})

    plugin.process(instance)

    assert not hasattr(plugin, "base_process_instance")
    assert debug_messages == ["Katana farm rendering is disabled; skipping Deadline."]


def test_process_submits_farm_instance_and_sets_output_directory(
    monkeypatch, tmp_path
) -> None:
    """Farm instances must submit through Deadline and retain their output path."""
    module = _load_submitter(monkeypatch)
    expected_file = tmp_path / "renders" / "beauty.0001.exr"
    plugin = module.KatanaSubmitDeadline()
    instance = types.SimpleNamespace(data={"farm": True, "files": [str(expected_file)]})

    plugin.process(instance)

    assert plugin.base_process_instance is instance
    assert instance.data["outputDir"] == str(expected_file.parent)


def test_job_info_uses_commandline_and_render_instance_frame_range(
    monkeypatch, tmp_path
) -> None:
    """Katana farm jobs must provide Deadline's command line and frame contract."""
    module = _load_submitter(monkeypatch)
    scene_path = tmp_path / "shots" / "lighting.katana"
    job_info = types.SimpleNamespace(Plugin="", Frames="", Name="", BatchName="")
    instance = types.SimpleNamespace(
        context=types.SimpleNamespace(data={"currentFile": str(scene_path)}),
        name="beauty",
        data={"frameStartHandle": 1001, "frameEndHandle": 1010, "byFrameStep": 2},
    )
    plugin = module.KatanaSubmitDeadline()
    plugin._instance = instance

    result = plugin.get_job_info(job_info)

    assert result is job_info
    assert job_info.Plugin == "CommandLine"
    assert job_info.Frames == "1001-1010x2"
    assert job_info.Name == "lighting.katana - beauty [RENDER]"
    assert job_info.BatchName == "lighting.katana"


def test_job_info_preserves_collected_frames(monkeypatch, tmp_path) -> None:
    """Global Deadline frame collectors must retain an explicit frame override."""
    module = _load_submitter(monkeypatch)
    job_info = types.SimpleNamespace(
        Plugin="", Frames="1001-1020x4", Name="", BatchName=""
    )
    instance = types.SimpleNamespace(
        context=types.SimpleNamespace(
            data={"currentFile": str(tmp_path / "scene.katana")}
        ),
        name="renderMain",
        data={"frameStartHandle": 1, "frameEndHandle": 2, "byFrameStep": 1},
    )
    plugin = module.KatanaSubmitDeadline()
    plugin._instance = instance

    plugin.get_job_info(job_info)

    assert job_info.Frames == "1001-1020x4"


def test_image_payload_uses_imagewrite_and_image_job_label(
    monkeypatch,
    tmp_path,
) -> None:
    """Image farm metadata targets ImageWrite without requiring a renderer."""
    module = _load_submitter(monkeypatch)
    executable = tmp_path / "Katana9.0v1" / "bin" / "katanaBin.exe"
    executable.parent.mkdir(parents=True)
    executable.touch()
    monkeypatch.setattr(
        module.render,
        "get_katana_executable",
        lambda: executable,
        raising=False,
    )
    scene_path = tmp_path / "shots" / "comp.katana"
    instance = types.SimpleNamespace(
        context=types.SimpleNamespace(data={"currentFile": str(scene_path)}),
        name="imageMain",
        data={
            "families": ["image", "katana.image", "render.farm"],
            "image_write_node": "imageMain",
            "frameStartHandle": 1001,
            "frameEndHandle": 1003,
            "byFrameStep": 1,
        },
    )
    plugin = module.KatanaSubmitDeadline()
    plugin.scene_path = str(scene_path)
    plugin._instance = instance
    job_info = types.SimpleNamespace(Plugin="", Frames="", Name="", BatchName="")

    payload = plugin.get_plugin_info()
    plugin.get_job_info(job_info)

    assert '--render-node="imageMain"' in payload["Arguments"]
    assert job_info.Plugin == "CommandLine"
    assert job_info.Frames == "1001-1003x1"
    assert job_info.Name.endswith("[IMAGE]")
