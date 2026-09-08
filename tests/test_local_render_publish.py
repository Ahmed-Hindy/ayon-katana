"""Tests for local Katana render collection and extraction."""

from __future__ import annotations

import importlib.util
import sys
import types
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).parents[1]


class FakePlugin:
    """Minimal Pyblish plugin base."""


class FakePublishError(Exception):
    """Publish error accepting AYON's optional detail argument."""

    def __init__(self, message: str, detail: str | None = None) -> None:
        super().__init__(message)
        self.detail = detail


class FakeLog:
    """Collect plugin log messages without depending on Pyblish."""

    def __init__(self) -> None:
        self.messages = []

    def debug(self, message, *args) -> None:
        self.messages.append(("debug", message, args))

    def info(self, message, *args) -> None:
        self.messages.append(("info", message, args))


class FakePublishInstance:
    """Small mapping wrapper returned by a fake publish context."""

    def __init__(self, name: str) -> None:
        self.name = name
        self.data = {}


class FakeAnatomy:
    """Restore rootless staging paths produced by AYON Core helpers."""

    @staticmethod
    def fill_root(path: str) -> str:
        return path.replace("{root[work]}", "G:/Projects/AYON_PROJECTS")


class FakeContext:
    """Publish context with anatomy and instance creation support."""

    def __init__(self) -> None:
        self.data = {"anatomy": FakeAnatomy()}
        self.created_instances = []

    def create_instance(self, name: str) -> FakePublishInstance:
        instance = FakePublishInstance(name)
        self.created_instances.append(instance)
        return instance


class FakeSourceInstance:
    """Source render instance used by local collector tests."""

    def __init__(self, data: dict, context: FakeContext) -> None:
        self.data = data
        self.context = context


def _install_pyblish(monkeypatch) -> None:
    pyblish_api = types.ModuleType("pyblish.api")
    pyblish_api.CollectorOrder = 1.0
    pyblish_api.ExtractorOrder = 2.0
    pyblish_module = types.ModuleType("pyblish")
    pyblish_module.api = pyblish_api
    monkeypatch.setitem(sys.modules, "pyblish", pyblish_module)
    monkeypatch.setitem(sys.modules, "pyblish.api", pyblish_api)


def _install_ayon_katana(monkeypatch, **api_modules) -> None:
    package_module = types.ModuleType("ayon_katana")
    package_module.__path__ = []
    api_package = types.ModuleType("ayon_katana.api")
    api_package.__path__ = []
    monkeypatch.setitem(sys.modules, "ayon_katana", package_module)
    monkeypatch.setitem(sys.modules, "ayon_katana.api", api_package)
    for name, module in api_modules.items():
        setattr(api_package, name, module)
        monkeypatch.setitem(sys.modules, f"ayon_katana.api.{name}", module)


def _load_module(monkeypatch, module_name: str, relative_path: str):
    module_path = PROJECT_ROOT / relative_path
    module_spec = importlib.util.spec_from_file_location(module_name, module_path)
    assert module_spec is not None
    assert module_spec.loader is not None
    module = importlib.util.module_from_spec(module_spec)
    monkeypatch.setitem(sys.modules, module_name, module)
    module_spec.loader.exec_module(module)
    return module


def _load_local_collector(monkeypatch, calls: dict):
    _install_pyblish(monkeypatch)
    plugin_module = types.SimpleNamespace(KatanaInstancePlugin=FakePlugin)
    _install_ayon_katana(monkeypatch, plugin=plugin_module)

    farm_functions = types.ModuleType("ayon_core.pipeline.farm.pyblish_functions")

    def create_skeleton_instance(instance, families_transfer, instance_transfer):
        calls["skeleton"] = (instance, families_transfer, instance_transfer)
        return {
            "productName": instance.data["productName"],
            "families": ["render"],
        }

    def create_instances_for_aov(**kwargs):
        calls["aov"] = kwargs
        return [
            {
                "productName": "renderMain",
                "families": ["render", "review"],
                "representations": [
                    {
                        "stagingDir": "{root[work]}/renders/beauty",
                        "files": ["beauty.1001.exr"],
                    }
                ],
            },
            {
                "productName": "renderMain_Z",
                "families": ["render"],
                "representations": [
                    {
                        "stagingDir": "{root[work]}/renders/depth",
                        "files": ["depth.1001.exr"],
                    }
                ],
            },
        ]

    farm_functions.create_skeleton_instance = create_skeleton_instance
    farm_functions.create_instances_for_aov = create_instances_for_aov
    ayon_core = types.ModuleType("ayon_core")
    pipeline_module = types.ModuleType("ayon_core.pipeline")
    farm_module = types.ModuleType("ayon_core.pipeline.farm")
    monkeypatch.setitem(sys.modules, "ayon_core", ayon_core)
    monkeypatch.setitem(sys.modules, "ayon_core.pipeline", pipeline_module)
    monkeypatch.setitem(sys.modules, "ayon_core.pipeline.farm", farm_module)
    monkeypatch.setitem(
        sys.modules,
        "ayon_core.pipeline.farm.pyblish_functions",
        farm_functions,
    )
    return _load_module(
        monkeypatch,
        "ayon_katana.plugins.publish.collect_local_render_instances",
        "client/ayon_katana/plugins/publish/collect_local_render_instances.py",
    )


def _load_local_extractor(monkeypatch, executable: Path):
    _install_pyblish(monkeypatch)
    core_module = types.ModuleType("ayon_core")
    pipeline_module = types.ModuleType("ayon_core.pipeline")
    pipeline_module.PublishError = FakePublishError
    lib_module = types.ModuleType("ayon_core.lib")
    lib_module.get_oiio_tool_args = lambda tool, *args: [tool, *args]
    lib_module.run_subprocess = lambda _args, logger=None: ""
    monkeypatch.setitem(sys.modules, "ayon_core", core_module)
    monkeypatch.setitem(sys.modules, "ayon_core.pipeline", pipeline_module)
    monkeypatch.setitem(sys.modules, "ayon_core.lib", lib_module)

    plugin_module = types.SimpleNamespace(KatanaExtractorPlugin=FakePlugin)
    render_module = types.SimpleNamespace(get_katana_executable=lambda: executable)
    workio_module = types.SimpleNamespace(
        validate_workfile_path=lambda path, require_exists: path
    )
    _install_ayon_katana(
        monkeypatch,
        plugin=plugin_module,
        render=render_module,
        workio=workio_module,
    )
    return _load_module(
        monkeypatch,
        "ayon_katana.plugins.publish.extract_local_render",
        "client/ayon_katana/plugins/publish/extract_local_render.py",
    )


def test_local_collector_creates_core_aov_instances(monkeypatch) -> None:
    """Local outputs become integration instances through AYON Core helpers."""
    calls = {}
    module = _load_local_collector(monkeypatch, calls)
    context = FakeContext()
    source_instance = FakeSourceInstance(
        {
            "farm": False,
            "productName": "renderMain",
            "expectedFiles": [{"": ["beauty.1001.exr"], "Z": ["depth.1001.exr"]}],
            "creator_attributes": {"render_target": "local", "review": True},
            "publish_attributes": {"CollectAssetHandles": {"use_handles": True}},
        },
        context,
    )
    plugin = module.CollectLocalRenderInstances()
    plugin.log = FakeLog()

    assert plugin.order < 1.49
    plugin.process(source_instance)

    assert source_instance.data["integrate"] is False
    assert len(context.created_instances) == 2
    assert context.created_instances[0].data["families"] == [
        "render.local.katana",
        "review",
    ]
    assert context.created_instances[1].data["families"] == ["render.local.katana"]
    assert (
        context.created_instances[0].data["representations"][0]["stagingDir"]
        == "G:/Projects/AYON_PROJECTS/renders/beauty"
    )
    assert context.created_instances[0].data["representations"][0]["tags"] == ["review"]
    assert "tags" not in context.created_instances[1].data["representations"][0]
    assert calls["aov"]["do_not_add_review"] is True
    assert calls["aov"]["aov_filter"] == {}


def test_local_collector_skips_farm_instances(monkeypatch) -> None:
    """Farm rendering remains owned by Deadline submission."""
    calls = {}
    module = _load_local_collector(monkeypatch, calls)
    source_instance = FakeSourceInstance(
        {"farm": True, "productName": "renderMain"},
        FakeContext(),
    )
    plugin = module.CollectLocalRenderInstances()
    plugin.log = FakeLog()

    plugin.process(source_instance)

    assert calls == {}
    assert "integrate" not in source_instance.data


def test_local_collector_marks_image_outputs_with_image_family(monkeypatch) -> None:
    """Renderer-independent ImageWrite outputs keep an image integration family."""
    calls = {}
    module = _load_local_collector(monkeypatch, calls)
    context = FakeContext()
    source_instance = FakeSourceInstance(
        {
            "farm": False,
            "productName": "imageMain",
            "families": ["image", "katana.image"],
            "expectedFiles": [{"": ["imageMain.1001.exr"]}],
            "creator_attributes": {"render_target": "local", "review": False},
        },
        context,
    )
    plugin = module.CollectLocalRenderInstances()
    plugin.log = FakeLog()

    plugin.process(source_instance)

    assert source_instance.data["integrate"] is False
    assert context.created_instances
    assert context.created_instances[0].data["families"] == ["image.local.katana"]


def test_local_extractor_renders_each_frame_and_checks_outputs(
    monkeypatch,
    tmp_path,
) -> None:
    """Batch extraction renders the native range and verifies every output."""
    executable = tmp_path / "Katana" / "bin" / "katanaBin.exe"
    executable.parent.mkdir(parents=True)
    executable.write_text("", encoding="utf-8")
    module = _load_local_extractor(monkeypatch, executable)
    output_directory = tmp_path / "renders"
    expected_files = [
        output_directory / "beauty.1001.exr",
        output_directory / "beauty.1002.exr",
    ]
    commands = []

    def run(command, **kwargs):
        commands.append((command, kwargs))
        for frame in (1001, 1002):
            (output_directory / f"beauty.{frame}.exr").write_bytes(b"render")
        return types.SimpleNamespace(returncode=0, stdout="rendered")

    monkeypatch.setenv("AYON_KATANA_WORKFILE_PATH", "C:/stale/scene.katana")
    monkeypatch.setattr(module.subprocess, "run", run)
    instance = types.SimpleNamespace(
        context=types.SimpleNamespace(
            data={"currentFile": str(tmp_path / "scene.katana")}
        ),
        data={
            "farm": False,
            "creator_attributes": {"render_target": "local"},
            "render_node": "AYON_renderMain_Render",
            "frameStartHandle": 1001,
            "frameEndHandle": 1002,
            "byFrameStep": 1,
            "expectedFiles": [{"": [str(path) for path in expected_files]}],
        },
    )
    plugin = module.ExtractLocalRender()
    plugin.log = FakeLog()

    plugin.process(instance)

    assert len(commands) == 1
    command, run_kwargs = commands[0]
    assert command[command.index("-t") + 1] == "1001-1002"
    assert command[0] == str(executable)
    assert "AYON_KATANA_WORKFILE_PATH" not in run_kwargs["env"]
    assert f"--render-node={instance.data['render_node']}" in command
    assert all(path.stat().st_size > 0 for path in expected_files)


def test_existing_frame_extractor_validates_multi_aov_without_rendering(
    monkeypatch,
    tmp_path,
) -> None:
    """Existing-frame mode validates all AOVs without touching source files."""
    executable = tmp_path / "Katana" / "bin" / "katanaBin.exe"
    module = _load_local_extractor(monkeypatch, executable)
    beauty = tmp_path / "renders" / "beauty.1001.exr"
    depth = tmp_path / "renders" / "depth.1001.exr"
    beauty.parent.mkdir(parents=True)
    beauty.write_bytes(b"beauty-source")
    depth.write_bytes(b"depth-source")
    before = {beauty: beauty.read_bytes(), depth: depth.read_bytes()}

    def fail_run(*_args, **_kwargs):
        raise AssertionError("Existing-frame publishing must not launch Katana batch.")

    monkeypatch.setattr(module.subprocess, "run", fail_run)
    instance = types.SimpleNamespace(
        context=types.SimpleNamespace(data={}),
        data={
            "farm": False,
            "creator_attributes": {"render_target": "local_no_render"},
            "expectedFiles": [{"": [str(beauty)], "Z": [str(depth)]}],
        },
    )
    plugin = module.ExtractLocalRender()
    plugin.log = FakeLog()

    plugin.process(instance)

    assert beauty.read_bytes() == before[beauty]
    assert depth.read_bytes() == before[depth]


@pytest.mark.parametrize("kind", ["missing", "empty"])
def test_existing_frame_extractor_rejects_invalid_source_files(
    monkeypatch,
    tmp_path,
    kind: str,
) -> None:
    """Missing and empty existing outputs fail without invoking a render."""
    executable = tmp_path / "Katana" / "bin" / "katanaBin.exe"
    module = _load_local_extractor(monkeypatch, executable)
    source = tmp_path / "renders" / "beauty.1001.exr"
    if kind == "empty":
        source.parent.mkdir(parents=True)
        source.write_bytes(b"")

    monkeypatch.setattr(
        module.subprocess,
        "run",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            AssertionError("Existing-frame publishing must not render.")
        ),
    )
    instance = types.SimpleNamespace(
        context=types.SimpleNamespace(data={}),
        data={
            "farm": False,
            "creator_attributes": {"render_target": "local_no_render"},
            "expectedFiles": [{"": [str(source)]}],
        },
    )
    plugin = module.ExtractLocalRender()
    plugin.log = FakeLog()

    with pytest.raises(FakePublishError, match="existing-frame publish") as exc_info:
        plugin.process(instance)

    assert source.name in exc_info.value.detail


def test_existing_frame_extractor_rejects_corrupt_image(
    monkeypatch,
    tmp_path,
) -> None:
    """A non-empty file that OpenImageIO cannot decode is not publishable."""
    executable = tmp_path / "Katana" / "bin" / "katanaBin.exe"
    module = _load_local_extractor(monkeypatch, executable)
    source = tmp_path / "renders" / "beauty.1001.exr"
    source.parent.mkdir(parents=True)
    source.write_bytes(b"x")
    oiio_calls = []

    def fail_decode(arguments, logger=None):
        oiio_calls.append((arguments, logger))
        raise RuntimeError("invalid EXR")

    sys.modules["ayon_core.lib"].run_subprocess = fail_decode
    instance = types.SimpleNamespace(
        context=types.SimpleNamespace(data={}),
        data={
            "farm": False,
            "creator_attributes": {"render_target": "local_no_render"},
            "expectedFiles": [{"": [str(source)]}],
        },
    )
    plugin = module.ExtractLocalRender()
    plugin.log = FakeLog()

    with pytest.raises(FakePublishError, match="existing-frame publish") as exc_info:
        plugin.process(instance)

    assert len(oiio_calls) == 1
    assert oiio_calls[0][0] == ["oiiotool", "--hash", str(source)]
    assert "OpenImageIO decode failed" in exc_info.value.detail
    assert "invalid EXR" in exc_info.value.detail


def test_output_file_validation_rejects_unreadable_files(monkeypatch, tmp_path) -> None:
    """Filesystem read failures are reported as invalid output inputs."""
    executable = tmp_path / "Katana" / "bin" / "katanaBin.exe"
    module = _load_local_extractor(monkeypatch, executable)

    class UnreadablePath:
        """Path-like test double that fails only when opened for reading."""

        @staticmethod
        def is_file() -> bool:
            return True

        @staticmethod
        def open(*_args, **_kwargs):
            raise OSError("permission denied")

        def __str__(self) -> str:
            return "unreadable.exr"

    with pytest.raises(FakePublishError, match="invalid existing frames") as exc_info:
        module.ExtractLocalRender._validate_output_files(
            [UnreadablePath()],
            failure_message="invalid existing frames",
        )

    assert "unreadable" in exc_info.value.detail
    assert "permission denied" in exc_info.value.detail


def test_local_extractor_formats_stepped_frames(monkeypatch, tmp_path) -> None:
    """Katana comma-separated time ranges preserve non-unit frame steps."""
    executable = tmp_path / "Katana" / "bin" / "katanaBin.exe"
    executable.parent.mkdir(parents=True)
    executable.write_text("", encoding="utf-8")
    module = _load_local_extractor(monkeypatch, executable)

    assert module.ExtractLocalRender._format_frame_range(1001, 1005, 2) == (
        "1001,1003,1005"
    )


def test_local_extractor_reports_bounded_batch_log(monkeypatch, tmp_path) -> None:
    """Failed Katana batches expose their captured renderer output."""
    executable = tmp_path / "Katana" / "bin" / "katanaBin.exe"
    executable.parent.mkdir(parents=True)
    executable.write_text("", encoding="utf-8")
    module = _load_local_extractor(monkeypatch, executable)

    def run(_command, **kwargs):
        kwargs["stdout"].write("renderer failed")
        return types.SimpleNamespace(returncode=3)

    monkeypatch.setattr(module.subprocess, "run", run)
    instance = types.SimpleNamespace(
        context=types.SimpleNamespace(
            data={"currentFile": str(tmp_path / "scene.katana")}
        ),
        data={
            "farm": False,
            "creator_attributes": {"render_target": "local"},
            "render_node": "AYON_renderMain_Render",
            "frameStartHandle": 1001,
            "frameEndHandle": 1001,
            "byFrameStep": 1,
            "expectedFiles": [{"": [str(tmp_path / "beauty.1001.exr")]}],
        },
    )
    plugin = module.ExtractLocalRender()
    plugin.log = FakeLog()

    with pytest.raises(FakePublishError, match="exit code 3") as exc_info:
        plugin.process(instance)

    assert exc_info.value.detail.endswith("renderer failed")


def test_local_extractor_rejects_missing_outputs(monkeypatch, tmp_path) -> None:
    """A successful process exit cannot hide missing render products."""
    executable = tmp_path / "Katana" / "bin" / "katanaBin.exe"
    executable.parent.mkdir(parents=True)
    executable.write_text("", encoding="utf-8")
    module = _load_local_extractor(monkeypatch, executable)
    monkeypatch.setattr(
        module.subprocess,
        "run",
        lambda *_args, **_kwargs: types.SimpleNamespace(returncode=0, stdout=""),
    )
    instance = types.SimpleNamespace(
        context=types.SimpleNamespace(
            data={"currentFile": str(tmp_path / "scene.katana")}
        ),
        data={
            "farm": False,
            "creator_attributes": {"render_target": "local"},
            "render_node": "AYON_renderMain_Render",
            "frameStartHandle": 1001,
            "frameEndHandle": 1001,
            "byFrameStep": 1,
            "expectedFiles": [{"": [str(tmp_path / "renders" / "beauty.1001.exr")]}],
        },
    )
    plugin = module.ExtractLocalRender()
    plugin.log = FakeLog()

    with pytest.raises(FakePublishError, match="did not produce") as exc_info:
        plugin.process(instance)

    assert "beauty.1001.exr" in exc_info.value.detail
