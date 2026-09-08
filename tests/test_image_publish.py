"""Focused contracts for native Katana ImageWrite publishing."""

from __future__ import annotations

import ast
import importlib.util
import logging
import sys
import types
from pathlib import Path

import pytest

ROOT = Path(__file__).parents[1]


class FakeParameter:
    """Small Katana parameter storing one value."""

    def __init__(self, value) -> None:
        self.value = value

    def getValue(self, _time: float):
        """Return the current value."""
        return self.value

    def setValue(self, value, _time: float) -> None:
        """Replace the current value."""
        self.value = value


class FakePort:
    """Katana port stand-in with connection tracking."""

    def __init__(self) -> None:
        self.connected = []

    def connect(self, other) -> None:
        """Connect this output to an input."""
        self.connected.append(other)
        other.connected.append(self)

    def getConnectedPorts(self) -> list:
        """Return all connected ports."""
        return list(self.connected)


class FakeImageWriteNode:
    """Native ImageWrite stand-in used by creator and publish tests."""

    def __init__(self, name: str = "imageMain") -> None:
        self.name = name
        self.input_port = FakePort()
        self.deleted = False
        self.parameters = {
            "inputs.in.file": FakeParameter("G:/renders/image.####.exr"),
            "inputs.in.image.fileFormat": FakeParameter("exr"),
            "inputs.in.image.colorspace": FakeParameter("sRGB"),
            "singleFrame": FakeParameter(0),
            "frame": FakeParameter(1001),
        }

    def getName(self) -> str:
        """Return the node name."""
        return self.name

    def getType(self) -> str:
        """Return the native node type."""
        return "ImageWrite"

    def getParameter(self, name: str):
        """Return a named fake parameter."""
        return self.parameters.get(name)

    def getInputPort(self, name: str):
        """Return the native image input."""
        return self.input_port if name == "in" else None

    def delete(self) -> None:
        """Record node deletion."""
        self.deleted = True


class FakeCreatedInstance(dict):
    """CreatedInstance-compatible creator return value."""

    def __init__(self, data: dict, node: FakeImageWriteNode) -> None:
        super().__init__(data)
        self.transient_data = {"node": node}

    def data_to_store(self) -> dict:
        """Return serializable creator data."""
        return dict(self)


class FakeCreatorBase:
    """Minimal inherited Katana creator behavior."""

    def create(self, _product_name, instance_data, _pre_create_data):
        """Return the prepared instance around the fake ImageWrite node."""
        return FakeCreatedInstance(instance_data, self.image_write_node)

    def _remove_instance_from_context(self, instance) -> None:
        """Record creator-context cleanup."""
        self.removed_instance = instance


class FakeCreatorError(RuntimeError):
    """Creator error counterpart for isolated tests."""


class FakeOptionalMixin:
    """Minimal optional plug-in activation mixin."""

    def is_active(self, _data: dict) -> bool:
        """Keep the validator active."""
        return True


class FakeInstancePlugin:
    """Minimal instance plug-in base."""

    log = logging.getLogger("test_image_publish")


class FakeValidationError(RuntimeError):
    """Validation error preserving AYON's title argument."""

    def __init__(self, message: str, *, title: str | None = None) -> None:
        super().__init__(message)
        self.title = title


def _load_module(monkeypatch, name: str, path: Path):
    """Load one source file under a controlled module name."""
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    monkeypatch.setitem(sys.modules, name, module)
    spec.loader.exec_module(module)
    return module


def _load_image_api(monkeypatch):
    """Load the native image helper module."""
    return _load_module(
        monkeypatch,
        "ayon_katana.api.image",
        ROOT / "client" / "ayon_katana" / "api" / "image.py",
    )


def _install_api_package(monkeypatch, **modules) -> None:
    """Install a compact ``ayon_katana.api`` module tree."""
    package = types.ModuleType("ayon_katana")
    package.__path__ = []
    api = types.ModuleType("ayon_katana.api")
    api.__path__ = []
    plugins = types.ModuleType("ayon_katana.plugins")
    plugins.__path__ = []
    create = types.ModuleType("ayon_katana.plugins.create")
    create.__path__ = []
    publish = types.ModuleType("ayon_katana.plugins.publish")
    publish.__path__ = []
    monkeypatch.setitem(sys.modules, "ayon_katana", package)
    monkeypatch.setitem(sys.modules, "ayon_katana.api", api)
    monkeypatch.setitem(sys.modules, "ayon_katana.plugins", plugins)
    monkeypatch.setitem(sys.modules, "ayon_katana.plugins.create", create)
    monkeypatch.setitem(sys.modules, "ayon_katana.plugins.publish", publish)
    for name, module in modules.items():
        setattr(api, name, module)
        monkeypatch.setitem(sys.modules, f"ayon_katana.api.{name}", module)


def test_image_api_configures_native_node_and_expands_sequence(monkeypatch) -> None:
    """ImageWrite settings and hash-frame expansion stay deterministic."""
    image = _load_image_api(monkeypatch)
    node = FakeImageWriteNode()

    image.configure_image_write(
        node,
        output_path="G:/renders/comp.####.png",
        file_format="png",
        colorspace="sRGB",
        single_frame=False,
        frame=1001,
    )

    assert image.read_image_write_settings(node) == {
        "output_path": "G:/renders/comp.####.png",
        "file_format": "png",
        "colorspace": "sRGB",
        "single_frame": False,
        "frame": 1001,
    }
    assert image.expand_image_output_pattern(
        "G:/renders/comp.####.png", 1001, 1005, 2
    ) == [
        str(Path("G:/renders/comp.1001.png")),
        str(Path("G:/renders/comp.1003.png")),
        str(Path("G:/renders/comp.1005.png")),
    ]


def test_image_api_rejects_mismatched_format_and_ambiguous_sequences(
    monkeypatch,
) -> None:
    """Output extension mismatches and missing sequence tokens fail early."""
    image = _load_image_api(monkeypatch)
    node = FakeImageWriteNode()

    with pytest.raises(ValueError, match="does not match"):
        image.configure_image_write(
            node,
            output_path="G:/renders/comp.png",
            file_format="exr",
        )
    with pytest.raises(ValueError, match="exactly one hash"):
        image.expand_image_output_pattern("G:/renders/comp.exr", 1, 2, 1)


def _load_creator(monkeypatch, selected_nodes):
    """Load ``CreateImage`` with controlled Core and Katana APIs."""
    image = _load_image_api(monkeypatch)
    ayon_core = types.ModuleType("ayon_core")
    lib = types.ModuleType("ayon_core.lib")

    class AttrDef:
        def __init__(self, *_args, **_kwargs) -> None:
            pass

    lib.BoolDef = AttrDef
    lib.EnumDef = AttrDef
    lib.NumberDef = AttrDef
    lib.TextDef = AttrDef
    pipeline = types.ModuleType("ayon_core.pipeline")
    pipeline.CreatorError = FakeCreatorError
    ayon_core.lib = lib
    ayon_core.pipeline = pipeline
    monkeypatch.setitem(sys.modules, "ayon_core", ayon_core)
    monkeypatch.setitem(sys.modules, "ayon_core.lib", lib)
    monkeypatch.setitem(sys.modules, "ayon_core.pipeline", pipeline)

    imprinted = []
    compat = types.SimpleNamespace(
        get_selected_nodes=lambda: list(selected_nodes),
        get_output_ports=lambda node: [node.output_port],
    )
    instances = types.SimpleNamespace(
        imprint=lambda node, data: imprinted.append((node, dict(data)))
    )
    plugin = types.SimpleNamespace(KatanaCreator=FakeCreatorBase)
    _install_api_package(
        monkeypatch,
        compat=compat,
        image=image,
        instances=instances,
        plugin=plugin,
    )
    module = _load_module(
        monkeypatch,
        "ayon_katana.plugins.create.create_image",
        ROOT / "client" / "ayon_katana" / "plugins" / "create" / "create_image.py",
    )
    return module, imprinted


def test_creator_connects_image_source_and_persists_farm_contract(
    monkeypatch,
    tmp_path: Path,
) -> None:
    """Creator makes ImageWrite both the instance and batch render node."""

    class Source:
        def __init__(self) -> None:
            self.output_port = FakePort()

        def getName(self) -> str:
            return "ImageBlack"

        def getOutputPort(self, name: str):
            return self.output_port if name == "out" else None

    source = Source()
    module, imprinted = _load_creator(monkeypatch, [source])
    creator = object.__new__(module.CreateImage)
    creator.image_write_node = FakeImageWriteNode()
    creator.create_context = types.SimpleNamespace(
        get_current_folder_entity=lambda: {
            "attrib": {"frameStart": 1001, "frameEnd": 1010}
        },
        host=types.SimpleNamespace(
            get_current_workfile=lambda: str(tmp_path / "scene.katana")
        ),
    )

    created = creator.create(
        "imageMain",
        {"families": []},
        {
            "use_selection": True,
            "render_target": "farm",
            "review": True,
            "output_path": str(tmp_path / "imageMain.####.exr"),
            "extension": "exr",
            "colorspace": "sRGB",
        },
    )

    assert creator.image_write_node.input_port in source.output_port.connected
    assert created["image_write_node"] == "imageMain"
    assert created["render_node"] == "imageMain"
    assert created["farm"] is True
    assert created["families"] == ["image", "katana.image", "render.farm"]
    assert imprinted[-1][1]["creator_attributes"] == {
        "render_target": "farm",
        "review": True,
    }


def test_creator_persists_existing_frame_image_as_non_farm(
    monkeypatch,
    tmp_path: Path,
) -> None:
    """Existing-frame image instances persist without farm submission metadata."""
    module, _imprinted = _load_creator(monkeypatch, [])
    creator = object.__new__(module.CreateImage)
    creator.image_write_node = FakeImageWriteNode()
    creator.create_context = types.SimpleNamespace(
        get_current_folder_entity=lambda: {
            "attrib": {"frameStart": 1001, "frameEnd": 1010}
        },
        host=types.SimpleNamespace(
            get_current_workfile=lambda: str(tmp_path / "scene.katana")
        ),
    )

    created = creator.create(
        "imageMain",
        {"families": ["render.farm"]},
        {
            "use_selection": False,
            "render_target": "local_no_render",
            "output_path": str(tmp_path / "imageMain.####.exr"),
            "extension": "exr",
            "colorspace": "sRGB",
        },
    )

    assert created["farm"] is False
    assert "render.farm" not in created["families"]
    assert created["creator_attributes"]["render_target"] == "local_no_render"


def _install_publish_runtime(monkeypatch, node_map, image_module) -> None:
    """Install focused collector and validator dependencies."""
    pyblish_api = types.ModuleType("pyblish.api")
    pyblish_api.CollectorOrder = 1.0
    pyblish_api.ValidatorOrder = 2.0
    pyblish = types.ModuleType("pyblish")
    pyblish.api = pyblish_api
    monkeypatch.setitem(sys.modules, "pyblish", pyblish)
    monkeypatch.setitem(sys.modules, "pyblish.api", pyblish_api)

    ayon_core = types.ModuleType("ayon_core")
    pipeline = types.ModuleType("ayon_core.pipeline")
    pipeline.OptionalPyblishPluginMixin = FakeOptionalMixin
    publish = types.ModuleType("ayon_core.pipeline.publish")
    publish.PublishValidationError = FakeValidationError
    ayon_core.pipeline = pipeline
    monkeypatch.setitem(sys.modules, "ayon_core", ayon_core)
    monkeypatch.setitem(sys.modules, "ayon_core.pipeline", pipeline)
    monkeypatch.setitem(sys.modules, "ayon_core.pipeline.publish", publish)

    class RenderProducts:
        def __init__(self, names, colorspace_name="") -> None:
            self.layer_data = types.SimpleNamespace(
                products=[
                    types.SimpleNamespace(
                        productName=name,
                        colorspace=colorspace_name,
                    )
                    for name in names
                ]
            )

    _install_api_package(
        monkeypatch,
        colorspace=types.SimpleNamespace(ARenderProduct=RenderProducts),
        compat=types.SimpleNamespace(get_node=node_map.get),
        image=image_module,
        lib=types.SimpleNamespace(
            get_color_management_preferences=lambda: {
                "config": "G:/ocio/config.ocio",
                "colorspace": "ACEScg",
            }
        ),
        plugin=types.SimpleNamespace(KatanaInstancePlugin=FakeInstancePlugin),
        render=types.SimpleNamespace(
            get_project_frame_range=lambda: (1001, 1005),
            get_project_frame_step=lambda: 2,
        ),
    )


def _load_publish_modules(monkeypatch, node: FakeImageWriteNode):
    """Load the native image collector and validator around one node."""
    image = _load_image_api(monkeypatch)
    _install_publish_runtime(monkeypatch, {node.getName(): node}, image)
    collector = _load_module(
        monkeypatch,
        "ayon_katana.plugins.publish.collect_image",
        ROOT / "client" / "ayon_katana" / "plugins" / "publish" / "collect_image.py",
    )
    validator = _load_module(
        monkeypatch,
        "ayon_katana.plugins.publish.validate_image",
        ROOT / "client" / "ayon_katana" / "plugins" / "publish" / "validate_image.py",
    )
    return collector, validator


def test_collect_and_validate_image_builds_local_and_farm_metadata(
    monkeypatch,
) -> None:
    """ImageWrite collection produces expected files and Deadline metadata."""
    node = FakeImageWriteNode()
    FakePort().connect(node.input_port)
    collector, validator = _load_publish_modules(monkeypatch, node)
    instance = types.SimpleNamespace(
        data={
            "image_write_node": node.getName(),
            "creator_attributes": {"render_target": "farm", "review": True},
            "families": ["image", "katana.image"],
        }
    )

    collector.CollectImage().process(instance)
    validator.ValidateImage().process(instance)

    assert instance.data["expectedFiles"] == [
        {
            "": [
                str(Path("G:/renders/image.1001.exr")),
                str(Path("G:/renders/image.1003.exr")),
                str(Path("G:/renders/image.1005.exr")),
            ]
        }
    ]
    assert instance.data["frameStartHandle"] == 1001
    assert instance.data["frameEndHandle"] == 1005
    assert instance.data["byFrameStep"] == 2
    assert instance.data["farm"] is True
    assert "render.farm" in instance.data["families"]
    assert "review" in instance.data["families"]
    assert instance.data["colorspace"] == "sRGB"


def test_collector_refreshes_canonical_imagewrite_node_name(monkeypatch) -> None:
    """Live transient node identity wins when Katana canonicalizes ImageWrite names."""
    node = FakeImageWriteNode()
    node.name = "comp1"
    FakePort().connect(node.input_port)
    collector, validator = _load_publish_modules(monkeypatch, node)
    instance = types.SimpleNamespace(
        data={
            "image_write_node": "imageRequestedName",
            "instance_node": "imageRequestedName",
            "render_node": "imageRequestedName",
            "transientData": {"node": node},
            "creator_attributes": {"render_target": "farm", "review": False},
            "families": ["image", "katana.image"],
        }
    )

    collector.CollectImage().process(instance)
    validator.ValidateImage().process(instance)

    assert instance.data["image_write_node"] == "comp1"
    assert instance.data["instance_node"] == "comp1"
    assert instance.data["render_node"] == "comp1"


def test_collector_preserves_existing_frame_image_target(monkeypatch) -> None:
    """Image collection keeps existing-frame outputs on the local integration path."""
    node = FakeImageWriteNode()
    FakePort().connect(node.input_port)
    collector, validator = _load_publish_modules(monkeypatch, node)
    instance = types.SimpleNamespace(
        data={
            "image_write_node": node.getName(),
            "creator_attributes": {
                "render_target": "local_no_render",
                "review": False,
            },
            "families": ["image", "katana.image", "render.farm"],
        }
    )

    collector.CollectImage().process(instance)
    validator.ValidateImage().process(instance)

    assert instance.data["farm"] is False
    assert "render.farm" not in instance.data["families"]
    assert instance.data["creator_attributes"]["render_target"] == "local_no_render"


def test_validator_rejects_missing_source_and_review_colorspace(monkeypatch) -> None:
    """Disconnected or untagged review images fail before rendering."""
    node = FakeImageWriteNode()
    collector, validator = _load_publish_modules(monkeypatch, node)
    instance = types.SimpleNamespace(
        data={
            "image_write_node": node.getName(),
            "creator_attributes": {"render_target": "local", "review": False},
            "families": ["image", "katana.image"],
        }
    )
    collector.CollectImage().process(instance)
    with pytest.raises(FakeValidationError, match="exactly one"):
        validator.ValidateImage().process(instance)

    FakePort().connect(node.input_port)
    node.getParameter("inputs.in.image.colorspace").value = ""
    instance.data["creator_attributes"]["review"] = True
    collector.CollectImage().process(instance)
    with pytest.raises(FakeValidationError, match="explicit"):
        validator.ValidateImage().process(instance)


def test_server_settings_register_image_creator_and_publish_plugins() -> None:
    """Image creator, collector, and validator default to enabled."""
    tree = ast.parse(
        (ROOT / "server" / "settings" / "main.py").read_text(encoding="utf-8")
    )
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

    assert defaults["create"]["CreateImage"] == {
        "enabled": True,
        "default_render_target": "local",
        "default_extension": "exr",
        "default_colorspace": "",
        "default_frame_padding": 4,
        "default_review": False,
    }
    assert defaults["publish"]["CollectImage"] == {"enabled": True}
    assert defaults["publish"]["ValidateImage"] == {
        "enabled": True,
        "optional": False,
        "active": True,
    }
