"""Focused unit tests for native Katana render-state publishing contracts."""

from __future__ import annotations

import dataclasses
import importlib.util
import os
import sys
import types
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).parents[1]


class FakeParameter:
    """Minimal Katana parameter with a numeric or string value."""

    def __init__(self, value) -> None:
        self.value = value

    def getValue(self, _time):
        """Return the stored Katana parameter value."""
        return self.value

    def setValue(self, value, _time) -> None:
        """Store a Katana parameter value."""
        self.value = value


class FakeNode:
    """Minimal Katana node exposing named parameters."""

    def __init__(self, name: str, parameters: dict[str, object]) -> None:
        self.name = name
        self.parameters = {
            key: value if isinstance(value, FakeParameter) else FakeParameter(value)
            for key, value in parameters.items()
        }

    def getName(self) -> str:
        """Return the stable fake node name."""
        return self.name

    def getParameter(self, name: str):
        """Return an optional fake Katana parameter."""
        return self.parameters.get(name)


class FakeInstancePlugin:
    """Minimal Pyblish base class for plugin imports."""

    log = types.SimpleNamespace(error=lambda *_args, **_kwargs: None)


class FakePublishValidationError(Exception):
    """Minimal Core validation error for validator imports."""

    def __init__(
        self,
        message: str | None = None,
        *,
        title: str | None = None,
        description: str | None = None,
    ) -> None:
        super().__init__(message or title)
        self.title = title
        self.description = description


class FakeRepairAction:
    """Minimal Core repair action base for validator imports."""


class FakeAttributeDef:
    """Minimal AYON Core attribute definition for publish-option tests."""

    def __init__(self, key: str, *args, **kwargs) -> None:
        self.key = key


class FakeOptionalPyblishPluginMixin:
    """Minimal optional-plugin activation mixin for validator tests."""

    def is_active(self, data: dict) -> bool:
        """Return the stored active state, defaulting to enabled."""
        attributes = (data.get("publish_attributes") or {}).get(
            self.__class__.__name__, {}
        )
        return bool(attributes.get("active", True))


class FakePublishPluginMixin:
    """Minimal AYON publish-attribute mixin for collector tests."""

    @classmethod
    def instance_matches_plugin_families(cls, instance) -> bool:
        """Return the fake instance's configured plugin-family match."""
        return bool(getattr(instance, "matches_task_handles", True))

    def get_attr_values_from_data(self, data: dict) -> dict:
        """Return values stored for the active publish plugin."""
        return (data.get("publish_attributes") or {}).get(self.__class__.__name__, {})


def _load_module(monkeypatch, module_name: str, module_path: Path):
    """Load one source module without requiring Katana or AYON installation."""
    module_spec = importlib.util.spec_from_file_location(module_name, module_path)
    assert module_spec is not None
    assert module_spec.loader is not None
    module = importlib.util.module_from_spec(module_spec)
    monkeypatch.setitem(sys.modules, module_name, module)
    module_spec.loader.exec_module(module)
    return module


def _install_publish_runtime(monkeypatch, api_modules: dict[str, object]) -> None:
    """Install the minimum fake AYON and Pyblish modules for plugin imports."""
    pyblish_api = types.ModuleType("pyblish.api")
    pyblish_api.CollectorOrder = 1.0
    pyblish_api.ValidatorOrder = 2.0
    pyblish_module = types.ModuleType("pyblish")
    pyblish_module.api = pyblish_api
    monkeypatch.setitem(sys.modules, "pyblish", pyblish_module)
    monkeypatch.setitem(sys.modules, "pyblish.api", pyblish_api)

    ayon_core = types.ModuleType("ayon_core")
    lib_module = types.ModuleType("ayon_core.lib")
    pipeline_module = types.ModuleType("ayon_core.pipeline")
    publish_module = types.ModuleType("ayon_core.pipeline.publish")
    lib_module.BoolDef = FakeAttributeDef
    pipeline_module.AYONPyblishPluginMixin = FakePublishPluginMixin
    pipeline_module.OptionalPyblishPluginMixin = FakeOptionalPyblishPluginMixin
    pipeline_module.PublishValidationError = FakePublishValidationError
    publish_module.PublishValidationError = FakePublishValidationError
    publish_module.RepairAction = FakeRepairAction
    ayon_core.lib = lib_module
    ayon_core.pipeline = pipeline_module
    monkeypatch.setitem(sys.modules, "ayon_core", ayon_core)
    monkeypatch.setitem(sys.modules, "ayon_core.lib", lib_module)
    monkeypatch.setitem(sys.modules, "ayon_core.pipeline", pipeline_module)
    monkeypatch.setitem(sys.modules, "ayon_core.pipeline.publish", publish_module)

    package_module = types.ModuleType("ayon_katana")
    package_module.__path__ = []
    api_package = types.ModuleType("ayon_katana.api")
    api_package.__path__ = []
    monkeypatch.setitem(sys.modules, "ayon_katana", package_module)
    monkeypatch.setitem(sys.modules, "ayon_katana.api", api_package)
    for name, module in api_modules.items():
        setattr(api_package, name, module)
        monkeypatch.setitem(sys.modules, f"ayon_katana.api.{name}", module)


def _load_render_module(monkeypatch, root_node: FakeNode):
    """Load render helpers with a fake Katana root timeline."""
    katana_module = types.ModuleType("Katana")
    katana_module.NodegraphAPI = types.SimpleNamespace(
        GetRootNode=lambda: root_node,
        GetNodePosition=lambda _node: (0.0, 0.0),
    )
    katana_module.RenderingAPI = types.SimpleNamespace(
        RenderPlugins=types.SimpleNamespace(GetRendererPluginNames=lambda: ["prman"])
    )
    monkeypatch.setitem(sys.modules, "Katana", katana_module)
    package_module = types.ModuleType("ayon_katana")
    package_module.__path__ = []
    api_package = types.ModuleType("ayon_katana.api")
    api_package.__path__ = []
    lib_module = types.ModuleType("ayon_katana.api.lib")
    monkeypatch.setitem(sys.modules, "ayon_katana", package_module)
    monkeypatch.setitem(sys.modules, "ayon_katana.api", api_package)
    monkeypatch.setitem(sys.modules, "ayon_katana.api.lib", lib_module)
    return _load_module(
        monkeypatch,
        "ayon_katana.api.render",
        PROJECT_ROOT / "client" / "ayon_katana" / "api" / "render.py",
    )


def test_native_node_position_errors_propagate(monkeypatch) -> None:
    """Broken native graph positioning cannot silently alter output ordering."""

    class OutputNode:
        def getName(self) -> str:
            return "output"

        def getType(self) -> str:
            return "RenderOutputDefine"

    output_node = OutputNode()
    root_node = types.SimpleNamespace(getChildren=lambda: [output_node])
    render = _load_render_module(monkeypatch, root_node)
    katana = sys.modules["Katana"]

    def fail(_node):
        raise RuntimeError("native node position failure")

    katana.NodegraphAPI.GetNodePosition = fail
    with pytest.raises(RuntimeError, match="native node position failure"):
        render.get_output_nodes(root_node)


def test_native_parameter_errors_propagate(monkeypatch) -> None:
    """Existing Katana parameters must not hide native evaluation failures."""
    parameter = FakeParameter("value")

    def fail(_time):
        raise RuntimeError("native parameter failure")

    parameter.getValue = fail
    root_node = FakeNode("root", {"broken": parameter})
    render = _load_render_module(monkeypatch, root_node)

    with pytest.raises(RuntimeError, match="native parameter failure"):
        render._parameter_value(root_node, "broken", "fallback")


def test_native_frame_range_overrides_stale_creator_metadata(monkeypatch) -> None:
    """Frame collection must trust Render parameters over Creator metadata."""
    root_node = FakeNode(
        "root",
        {"inTime": 1, "outTime": 100, "timeIncrement": 2},
    )
    render = _load_render_module(monkeypatch, root_node)
    render_node = FakeNode(
        "render",
        {
            "farmSettings.setActiveFrameRange": "Yes",
            "farmSettings.activeFrameRange.start": 1002,
            "farmSettings.activeFrameRange.end": 1006,
        },
    )
    _install_publish_runtime(
        monkeypatch,
        {
            "compat": types.SimpleNamespace(get_node=lambda _name: render_node),
            "plugin": types.SimpleNamespace(KatanaInstancePlugin=FakeInstancePlugin),
            "render": render,
        },
    )
    collector = _load_module(
        monkeypatch,
        "ayon_katana.plugins.publish.collect_render_frame_range",
        PROJECT_ROOT
        / "client"
        / "ayon_katana"
        / "plugins"
        / "publish"
        / "collect_render_frame_range.py",
    )
    instance = types.SimpleNamespace(
        data={
            "render_node": "render",
            "creator_attributes": {
                "frame_start": 1,
                "frame_end": 1,
                "frame_step": 1,
            },
        }
    )

    collector.CollectRenderFrameRange().process(instance)

    assert instance.data["frameStartHandle"] == 1002
    assert instance.data["frameEndHandle"] == 1006
    assert instance.data["byFrameStep"] == 2
    assert instance.data["katanaFrameRangeSource"] == "render"


def test_native_frame_range_falls_back_to_project_timeline(monkeypatch) -> None:
    """Disabled Render overrides must use Katana's native project timeline."""
    root_node = FakeNode(
        "root",
        {"inTime": 10, "outTime": 20, "timeIncrement": 3},
    )
    render = _load_render_module(monkeypatch, root_node)
    render_node = FakeNode("render", {"farmSettings.setActiveFrameRange": "No"})

    frame_range = render.get_render_frame_range(render_node)

    assert frame_range == render.RenderFrameRange(10, 20, 3, "project")


@pytest.mark.parametrize(
    ("use_handles", "entity", "expected"),
    [
        (
            True,
            {"attrib": {"handleStart": 8, "handleEnd": 8}},
            (1001, 1050, 8, 8),
        ),
        (False, {"attrib": {"handleStart": 8, "handleEnd": 8}}, (993, 1058, 0, 0)),
        (True, {}, (993, 1058, 0, 0)),
    ],
)
def test_task_handles_follow_the_ayon_core_contract(
    monkeypatch,
    use_handles,
    entity,
    expected,
) -> None:
    """Task, disabled, and missing handles must produce predictable data."""
    _install_publish_runtime(
        monkeypatch,
        {"plugin": types.SimpleNamespace(KatanaInstancePlugin=FakeInstancePlugin)},
    )
    collector = _load_module(
        monkeypatch,
        "ayon_katana.plugins.publish.collect_render_task_handles",
        PROJECT_ROOT
        / "client"
        / "ayon_katana"
        / "plugins"
        / "publish"
        / "collect_render_task_handles.py",
    )
    instance = types.SimpleNamespace(
        data={
            "frameStartHandle": 993,
            "frameEndHandle": 1058,
            "publish_attributes": {"CollectAssetHandles": {"use_handles": use_handles}},
            "taskEntity": entity,
        }
    )

    collector.CollectAssetHandles().process(instance)

    assert (
        instance.data["frameStart"],
        instance.data["frameEnd"],
        instance.data["handleStart"],
        instance.data["handleEnd"],
    ) == expected


def test_task_handles_use_plugin_default_without_publish_attribute(monkeypatch) -> None:
    """Missing publish attributes use the collector's configured default."""
    _install_publish_runtime(
        monkeypatch,
        {"plugin": types.SimpleNamespace(KatanaInstancePlugin=FakeInstancePlugin)},
    )
    collector = _load_module(
        monkeypatch,
        "ayon_katana.plugins.publish.collect_render_task_handles",
        PROJECT_ROOT
        / "client"
        / "ayon_katana"
        / "plugins"
        / "publish"
        / "collect_render_task_handles.py",
    )
    instance = types.SimpleNamespace(
        data={
            "frameStartHandle": 993,
            "frameEndHandle": 1058,
            "taskEntity": {"attrib": {"handleStart": 8, "handleEnd": 8}},
        }
    )

    collector.CollectAssetHandles().process(instance)

    assert (
        instance.data["frameStart"],
        instance.data["frameEnd"],
        instance.data["handleStart"],
        instance.data["handleEnd"],
    ) == (1001, 1050, 8, 8)


def test_task_handles_exposes_publish_attribute(monkeypatch) -> None:
    """Only matching render instances receive the publisher-time toggle."""
    _install_publish_runtime(
        monkeypatch,
        {"plugin": types.SimpleNamespace(KatanaInstancePlugin=FakeInstancePlugin)},
    )
    collector = _load_module(
        monkeypatch,
        "ayon_katana.plugins.publish.collect_render_task_handles",
        PROJECT_ROOT
        / "client"
        / "ayon_katana"
        / "plugins"
        / "publish"
        / "collect_render_task_handles.py",
    )

    matching_instance = types.SimpleNamespace(matches_task_handles=True)
    nonmatching_instance = types.SimpleNamespace(matches_task_handles=False)

    definitions = collector.CollectAssetHandles.get_attr_defs_for_instance(
        None,
        matching_instance,
    )

    assert [definition.key for definition in definitions] == ["use_handles"]
    assert (
        collector.CollectAssetHandles.get_attr_defs_for_instance(
            None,
            nonmatching_instance,
        )
        == []
    )


def test_native_resolution_uses_katana_resource_data(monkeypatch, tmp_path) -> None:
    """Resolution dimensions must come from Katana's installed XML resources."""
    resource_dir = tmp_path / "plugins" / "Resources" / "Core" / "Resolutions"
    resource_dir.mkdir(parents=True)
    (resource_dir / "formats.xml").write_text(
        '<stormXML><formats><format name="Test" width="1920" '
        'height="1080" pixelAspect="1.0" /></formats></stormXML>',
        encoding="utf-8",
    )
    monkeypatch.setenv("KATANA_ROOT", str(tmp_path))
    render = _load_render_module(
        monkeypatch,
        FakeNode("root", {"inTime": 1, "outTime": 1, "timeIncrement": 1}),
    )

    resolution = render.get_resolution("Test")

    assert resolution == render.RenderResolution("Test", 1920, 1080, 1.0)


def _load_colorspace_modules(monkeypatch):
    """Load addon classes with Core services and attrs constructors stubbed."""
    colorspace_core = types.ModuleType("ayon_core.pipeline.colorspace")
    colorspace_core.get_ocio_config_colorspaces = lambda _path: {
        "roles": {"scene_linear": {"colorspace": "ACEScg"}}
    }
    ayon_core = types.ModuleType("ayon_core")
    pipeline_module = types.ModuleType("ayon_core.pipeline")
    pipeline_module.colorspace = colorspace_core
    ayon_core.pipeline = pipeline_module
    monkeypatch.setitem(sys.modules, "ayon_core", ayon_core)
    monkeypatch.setitem(sys.modules, "ayon_core.pipeline", pipeline_module)
    monkeypatch.setitem(sys.modules, "ayon_core.pipeline.colorspace", colorspace_core)

    attr_module = types.ModuleType("attr")
    attr_module.s = dataclasses.dataclass

    def _attr_ib(*, default=dataclasses.MISSING):
        if default is dataclasses.MISSING:
            return dataclasses.field()
        return dataclasses.field(default=default)

    attr_module.ib = _attr_ib
    monkeypatch.setitem(sys.modules, "attr", attr_module)

    package_module = types.ModuleType("ayon_katana")
    package_module.__path__ = []
    api_package = types.ModuleType("ayon_katana.api")
    api_package.__path__ = []
    monkeypatch.setitem(sys.modules, "ayon_katana", package_module)
    monkeypatch.setitem(sys.modules, "ayon_katana.api", api_package)
    colorspace = _load_module(
        monkeypatch,
        "ayon_katana.api.colorspace",
        PROJECT_ROOT / "client" / "ayon_katana" / "api" / "colorspace.py",
    )
    api_package.colorspace = colorspace
    lib = _load_module(
        monkeypatch,
        "ayon_katana.api.lib",
        PROJECT_ROOT / "client" / "ayon_katana" / "api" / "lib.py",
    )
    return colorspace, lib


def test_colorspace_requires_an_active_ocio_config(monkeypatch, tmp_path) -> None:
    """OCIO absence cannot fabricate colorspace metadata."""
    config_path = tmp_path / "config.ocio"
    config_path.write_text("ocio_profile_version: 2", encoding="utf-8")
    _colorspace, lib = _load_colorspace_modules(monkeypatch)

    monkeypatch.delenv("OCIO", raising=False)
    assert lib.get_color_management_preferences() == {}
    monkeypatch.setenv("OCIO", str(config_path))
    assert lib.get_color_management_preferences() == {
        "config": str(config_path),
        "colorspace": "ACEScg",
    }


@pytest.fixture
def render_colorspace(monkeypatch, tmp_path):
    """Create validator input using the addon's render-product constructor."""
    colorspace, _lib = _load_colorspace_modules(monkeypatch)
    module = _load_validator(
        monkeypatch,
        "validate_render_colorspace.py",
        {"plugin": types.SimpleNamespace(KatanaInstancePlugin=FakeInstancePlugin)},
    )
    config = tmp_path / "config.ocio"
    config.write_text("ocio_profile_version: 2", encoding="utf-8")
    instance = types.SimpleNamespace(
        data={
            "colorspaceConfig": str(config),
            "colorspace": "ACEScg",
            "renderProducts": colorspace.ARenderProduct(["beauty", "depth"], "ACEScg"),
        }
    )
    return module.ValidateRenderColorspace(), instance


def test_render_colorspace_accepts_addon_products(render_colorspace):
    """The addon-owned render-product structure satisfies the validator."""
    validator, instance = render_colorspace
    validator.process(instance)


@pytest.mark.parametrize("state", ["missing", "none", "empty"])
def test_render_colorspace_requires_products(render_colorspace, state):
    """Absent products and empty product lists remain validation errors."""
    validator, instance = render_colorspace
    if state == "missing":
        del instance.data["renderProducts"]
    elif state == "none":
        instance.data["renderProducts"] = None
    else:
        instance.data["renderProducts"].layer_data.products.clear()
    with pytest.raises(FakePublishValidationError, match="no colorspace data"):
        validator.process(instance)


def test_render_colorspace_rejects_mismatched_product(render_colorspace):
    """Every product must match the collected scene-linear colorspace."""
    validator, instance = render_colorspace
    instance.data["renderProducts"].layer_data.products[1].colorspace = "sRGB"
    with pytest.raises(FakePublishValidationError, match="do not share"):
        validator.process(instance)


@pytest.mark.parametrize("field", ["colorspaceConfig", "colorspace"])
def test_render_colorspace_requires_config_and_role(render_colorspace, field):
    """Valid products cannot substitute for missing configuration metadata."""
    validator, instance = render_colorspace
    instance.data[field] = ""
    with pytest.raises(FakePublishValidationError, match="active OCIO"):
        validator.process(instance)


@pytest.mark.parametrize("missing_layer", [True, False])
def test_render_colorspace_surfaces_broken_internal_structure(
    render_colorspace, missing_layer
):
    """Broken owned objects surface programming errors instead of empty data."""
    validator, instance = render_colorspace
    if missing_layer:
        del instance.data["renderProducts"].layer_data
    else:
        del instance.data["renderProducts"].layer_data.products
    with pytest.raises(AttributeError):
        validator.process(instance)


def test_render_colorspace_can_be_disabled(render_colorspace):
    """Disabled validation does not access required colorspace data."""
    validator, instance = render_colorspace
    instance.data = {
        "publish_attributes": {"ValidateRenderColorspace": {"active": False}}
    }
    validator.process(instance)


def test_expected_files_expand_distinct_aov_outputs(monkeypatch) -> None:
    """Expected file expansion preserves distinct native AOV products."""
    root_node = FakeNode("root", {"inTime": 1, "outTime": 1, "timeIncrement": 1})
    render = _load_render_module(monkeypatch, root_node)
    _install_publish_runtime(
        monkeypatch,
        {
            "compat": types.SimpleNamespace(),
            "plugin": types.SimpleNamespace(KatanaInstancePlugin=FakeInstancePlugin),
            "render": render,
        },
    )
    collector = _load_module(
        monkeypatch,
        "ayon_katana.plugins.publish.collect_render",
        PROJECT_ROOT
        / "client"
        / "ayon_katana"
        / "plugins"
        / "publish"
        / "collect_render.py",
    )
    definitions = [
        render.RenderOutputDefinition(
            "beauty",
            "primary",
            "C:/renders/beauty.####.exr",
            "exr",
            "rgba",
            True,
        ),
        render.RenderOutputDefinition(
            "depth",
            "depth",
            "C:/renders/depth.####.exr",
            "exr",
            "Z",
            True,
        ),
    ]

    expected_files = collector.collect_expected_files_by_aov(definitions, 1001, 1005, 2)

    assert set(expected_files) == {"", "Z"}
    assert expected_files[""] == [
        os.path.normpath("C:/renders/beauty.1001.exr"),
        os.path.normpath("C:/renders/beauty.1003.exr"),
        os.path.normpath("C:/renders/beauty.1005.exr"),
    ]
    assert expected_files["Z"][-1].endswith("depth.1005.exr")


def _load_validator(monkeypatch, filename: str, api_modules: dict[str, object]):
    """Load one render validator with a minimal publishing runtime."""
    _install_publish_runtime(monkeypatch, api_modules)
    if filename in {
        "validate_render.py",
        "validate_render_frame_range.py",
        "validate_render_output_extensions.py",
        "validate_render_output_names.py",
        "validate_render_output_paths.py",
        "validate_render_output_tokens.py",
        "validate_render_resolution.py",
    }:
        plugins_package = types.ModuleType("ayon_katana.plugins")
        plugins_package.__path__ = []
        publish_package = types.ModuleType("ayon_katana.plugins.publish")
        publish_package.__path__ = []
        actions_module = types.ModuleType("ayon_katana.plugins.publish.actions")
        if filename == "validate_render.py":
            actions_module.ReconnectAYONRenderGraphAction = type(
                "ReconnectAYONRenderGraphAction",
                (),
                {},
            )
        actions_module.SelectInvalidInstanceNodes = type(
            "SelectInvalidInstanceNodes",
            (),
            {},
        )
        actions_module.SelectInvalidOutputNodes = type(
            "SelectInvalidOutputNodes",
            (),
            {},
        )
        monkeypatch.setitem(sys.modules, "ayon_katana.plugins", plugins_package)
        monkeypatch.setitem(
            sys.modules,
            "ayon_katana.plugins.publish",
            publish_package,
        )
        monkeypatch.setitem(
            sys.modules,
            "ayon_katana.plugins.publish.actions",
            actions_module,
        )
    return _load_module(
        monkeypatch,
        f"ayon_katana.plugins.publish.{filename[:-3]}",
        PROJECT_ROOT / "client" / "ayon_katana" / "plugins" / "publish" / filename,
    )


def test_render_path_validator_rejects_same_path_outputs(monkeypatch) -> None:
    """Katana outputs cannot safely share a destination path."""
    plugin = types.SimpleNamespace(KatanaInstancePlugin=FakeInstancePlugin)
    nodes = {
        "instance": object(),
        "beautyNode": FakeNode("beautyNode", {}),
        "depthNode": FakeNode("depthNode", {}),
    }
    output_definitions = [
        types.SimpleNamespace(
            name="primary",
            node_name="beautyNode",
            aov_identifier="",
            path="C:/renders/main.####.exr",
            extension="exr",
        ),
        types.SimpleNamespace(
            name="depth",
            node_name="depthNode",
            aov_identifier="Z",
            path="C:/renders/main.####.exr",
            extension="exr",
        ),
    ]
    path_validator = _load_validator(
        monkeypatch,
        "validate_render_output_paths.py",
        {
            "compat": types.SimpleNamespace(get_node=lambda name: nodes.get(name)),
            "plugin": plugin,
            "render": types.SimpleNamespace(
                get_output_definitions=lambda _node: output_definitions,
            ),
        },
    )

    with pytest.raises(FakePublishValidationError, match="shared by outputs"):
        path_validator.ValidateRenderOutputPaths().process(
            types.SimpleNamespace(data={"instance_node": "instance"})
        )


def test_frame_range_repair_disables_task_handles(monkeypatch) -> None:
    """The shared repair action disables the handle collector attribute."""
    plugin = types.SimpleNamespace(KatanaInstancePlugin=FakeInstancePlugin)
    frame_validator = _load_validator(
        monkeypatch,
        "validate_render_frame_range.py",
        {"plugin": plugin},
    )
    created_instance = types.SimpleNamespace(
        publish_attributes={"CollectAssetHandles": {"use_handles": True}}
    )
    save_calls = []
    create_context = types.SimpleNamespace(
        get_instance_by_id=lambda instance_id: (
            created_instance if instance_id == "instance-id" else None
        ),
        save_changes=lambda: save_calls.append(True),
    )
    instance = types.SimpleNamespace(
        data={
            "instance_id": "instance-id",
            "frameStart": 2,
            "frameEnd": 1,
        },
        context=types.SimpleNamespace(data={"create_context": create_context}),
    )

    frame_validator.ValidateFrameRange.repair(instance)

    assert created_instance.publish_attributes["CollectAssetHandles"] == {
        "use_handles": False
    }
    assert save_calls == [True]


def test_render_validators_reject_invalid_native_state(monkeypatch, tmp_path) -> None:
    """Frame, camera, resolution, token, renderer, and OCIO errors stay explicit."""
    plugin = types.SimpleNamespace(KatanaInstancePlugin=FakeInstancePlugin)
    frame_validator = _load_validator(
        monkeypatch,
        "validate_render_frame_range.py",
        {"plugin": plugin},
    )
    with pytest.raises(FakePublishValidationError, match="native frame end"):
        frame_validator.ValidateFrameRange().process(
            types.SimpleNamespace(
                data={
                    "frameStartHandle": 2,
                    "frameEndHandle": 1,
                    "byFrameStep": 1,
                    "frameStart": 2,
                    "frameEnd": 1,
                }
            )
        )

    camera_validator = _load_validator(
        monkeypatch,
        "validate_render_camera.py",
        {
            "compat": types.SimpleNamespace(),
            "plugin": plugin,
            "render": types.SimpleNamespace(),
        },
    )
    with pytest.raises(FakePublishValidationError, match="no camera"):
        camera_validator.ValidateRenderCamera().process(
            types.SimpleNamespace(data={"camera": ""})
        )

    def fail_camera_cook(_node, _path):
        raise RuntimeError("native camera cook failure")

    camera_validator = _load_validator(
        monkeypatch,
        "validate_render_camera.py",
        {
            "compat": types.SimpleNamespace(get_node=lambda _name: object()),
            "plugin": plugin,
            "render": types.SimpleNamespace(
                get_scenegraph_location_type=fail_camera_cook
            ),
        },
    )
    with pytest.raises(RuntimeError, match="native camera cook failure"):
        camera_validator.ValidateRenderCamera().process(
            types.SimpleNamespace(
                data={"camera": "/root/world/cam/main", "render_node": "render"}
            )
        )

    resolution_validator = _load_validator(
        monkeypatch,
        "validate_render_resolution.py",
        {"plugin": plugin},
    )
    with pytest.raises(FakePublishValidationError, match="invalid resolution"):
        resolution_validator.ValidateRenderResolution().process(
            types.SimpleNamespace(data={"resolutionWidth": 0})
        )

    output_definition = types.SimpleNamespace(
        node_name="outputNode",
        path="C:/renders/image.exr",
    )
    token_validator = _load_validator(
        monkeypatch,
        "validate_render_output_tokens.py",
        {
            "compat": types.SimpleNamespace(
                get_node=lambda name: (
                    FakeNode("outputNode", {}) if name == "outputNode" else object()
                )
            ),
            "plugin": plugin,
            "render": types.SimpleNamespace(
                get_output_definitions=lambda _node: [output_definition]
            ),
        },
    )
    with pytest.raises(FakePublishValidationError, match="frame token"):
        token_validator.ValidateRenderOutputTokens().process(
            types.SimpleNamespace(
                data={
                    "instance_node": "instance",
                    "frameStartHandle": 1,
                    "frameEndHandle": 2,
                    "byFrameStep": 1,
                }
            )
        )

    render_validator = _load_validator(
        monkeypatch,
        "validate_render.py",
        {
            "compat": types.SimpleNamespace(get_node=lambda _name: object()),
            "plugin": plugin,
            "render": types.SimpleNamespace(
                get_render_node=lambda _node: object(),
                get_settings_node=lambda _node: object(),
                is_renderer_registered=lambda _name: False,
            ),
        },
    )
    with pytest.raises(FakePublishValidationError, match="not registered"):
        render_validator.ValidateRender().process(
            types.SimpleNamespace(
                data={"instance_node": "instance", "renderer": "missing"}
            )
        )

    class ConnectedInput:
        """Input port with one upstream connection for graph validation."""

        @staticmethod
        def getConnectedPorts():
            return [object()]

    class OutputNode:
        """Render output node with a connected input port."""

        @staticmethod
        def getInputPort(name):
            return ConnectedInput() if name == "input" else None

    output_definition = types.SimpleNamespace(node_name="outputNode")
    existing_frame_validator = _load_validator(
        monkeypatch,
        "validate_render.py",
        {
            "compat": types.SimpleNamespace(
                get_node=lambda name: OutputNode() if name == "outputNode" else object()
            ),
            "plugin": plugin,
            "render": types.SimpleNamespace(
                get_render_node=lambda _node: object(),
                get_settings_node=lambda _node: object(),
                is_renderer_registered=lambda _name: False,
                get_output_definitions=lambda _node: [output_definition],
            ),
        },
    )
    existing_frame_validator.ValidateRender().process(
        types.SimpleNamespace(
            data={
                "instance_node": "instance",
                "renderer": "missing",
                "creator_attributes": {"render_target": "local_no_render"},
            }
        )
    )

    colorspace_validator = _load_validator(
        monkeypatch,
        "validate_render_colorspace.py",
        {"plugin": plugin},
    )
    with pytest.raises(FakePublishValidationError, match="active OCIO"):
        colorspace_validator.ValidateRenderColorspace().process(
            types.SimpleNamespace(data={"colorspaceConfig": str(tmp_path / "none")})
        )
