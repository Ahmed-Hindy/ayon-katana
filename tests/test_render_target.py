"""Tests for Katana farm and local render target contracts."""

from __future__ import annotations

import ast
import importlib.util
import sys
import types
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).parents[1]


class FakeAttributeDef:
    """Minimal AYON Core attribute definition for creator option tests."""

    def __init__(self, key: str, *args, **kwargs) -> None:
        self.key = key


class FakeNode:
    """Minimal Katana node used by render creator and collector tests."""

    def __init__(self, name: str) -> None:
        self.name = name
        self.deleted = False

    def getName(self) -> str:
        """Return the node name."""
        return self.name

    def setName(self, name: str) -> None:
        """Rename the fake node."""
        self.name = name

    def delete(self) -> None:
        """Record deletion requested by creator cleanup."""
        self.deleted = True


class FakeCreatedInstance(dict):
    """Mapping-compatible stand-in for AYON's created instance."""

    def __init__(self, data: dict) -> None:
        super().__init__(data)
        self.transient_data = {"node": FakeNode("renderInstance")}

    def data_to_store(self) -> dict:
        """Return serialized data for the fake imprint call."""
        return dict(self)


class FakeKatanaCreator:
    """Minimal base creator that preserves the prepared instance data."""

    def create(self, product_name: str, instance_data: dict, pre_create_data: dict):
        """Create a fake AYON instance."""
        self.created_instance = FakeCreatedInstance(instance_data)
        return self.created_instance

    def _remove_instance_from_context(self, created_instance) -> None:
        """Record Creator-context cleanup."""
        self.removed_instance = created_instance

    def update_instances(self, update_list) -> None:
        """Apply the base creator's product-name rename behavior."""
        for created_instance, changes in update_list:
            if "productName" not in changes.changed_keys:
                continue
            created_instance.transient_data["node"].setName(
                changes["productName"].new_value
            )


class FakeCreatorError(Exception):
    """Minimal creator error used by renderer configuration tests."""


class FakeKatanaInstancePlugin:
    """Minimal base class for importing the collector."""


def _install_ayon_katana_package(monkeypatch, api_modules: dict[str, object]) -> None:
    """Install the minimum package modules needed to import a plugin."""
    package_module = types.ModuleType("ayon_katana")
    package_module.__path__ = []
    api_package = types.ModuleType("ayon_katana.api")
    api_package.__path__ = []
    monkeypatch.setitem(sys.modules, "ayon_katana", package_module)
    monkeypatch.setitem(sys.modules, "ayon_katana.api", api_package)
    for name, module in api_modules.items():
        setattr(api_package, name, module)
        monkeypatch.setitem(sys.modules, f"ayon_katana.api.{name}", module)


def _load_create_render_module(monkeypatch, default_renderer: str = "prman"):
    """Load the render creator with lightweight Katana and AYON stubs."""
    ayon_core_lib = types.ModuleType("ayon_core.lib")
    ayon_core_lib.BoolDef = FakeAttributeDef
    ayon_core_lib.EnumDef = FakeAttributeDef
    ayon_core_lib.NumberDef = FakeAttributeDef
    ayon_core_lib.TextDef = FakeAttributeDef
    ayon_core_pipeline = types.ModuleType("ayon_core.pipeline")
    ayon_core_pipeline.CreatorError = FakeCreatorError
    ayon_core = types.ModuleType("ayon_core")
    ayon_core.lib = ayon_core_lib
    ayon_core.pipeline = ayon_core_pipeline
    monkeypatch.setitem(sys.modules, "ayon_core", ayon_core)
    monkeypatch.setitem(sys.modules, "ayon_core.lib", ayon_core_lib)
    monkeypatch.setitem(sys.modules, "ayon_core.pipeline", ayon_core_pipeline)

    compat = types.SimpleNamespace(get_selected_nodes=lambda: [])
    instances = types.SimpleNamespace(imprint=lambda node, data: None)
    plugin = types.SimpleNamespace(KatanaCreator=FakeKatanaCreator)
    render = types.SimpleNamespace(
        get_default_renderer=lambda preferred=None: preferred or default_renderer,
        get_registered_renderers=lambda: ["prman"],
        create_render_graph=lambda **kwargs: FakeNode("renderMain"),
        get_settings_node=lambda _node: FakeNode("renderSettingsMain"),
        update_render_graph=lambda **kwargs: FakeNode("renderMain"),
    )
    _install_ayon_katana_package(
        monkeypatch,
        {
            "compat": compat,
            "instances": instances,
            "plugin": plugin,
            "render": render,
        },
    )

    module_path = (
        PROJECT_ROOT
        / "client"
        / "ayon_katana"
        / "plugins"
        / "create"
        / "create_render.py"
    )
    module_spec = importlib.util.spec_from_file_location(
        "ayon_katana.plugins.create.create_render",
        module_path,
    )
    assert module_spec is not None
    assert module_spec.loader is not None
    module = importlib.util.module_from_spec(module_spec)
    monkeypatch.setitem(
        sys.modules,
        "ayon_katana.plugins.create.create_render",
        module,
    )
    module_spec.loader.exec_module(module)
    return module


def _load_collect_render_module(monkeypatch):
    """Load the render collector with lightweight Katana and AYON stubs."""
    pyblish_api = types.ModuleType("pyblish.api")
    pyblish_api.CollectorOrder = 1.0
    pyblish_module = types.ModuleType("pyblish")
    pyblish_module.api = pyblish_api
    monkeypatch.setitem(sys.modules, "pyblish", pyblish_module)
    monkeypatch.setitem(sys.modules, "pyblish.api", pyblish_api)

    instance_node = FakeNode("renderInstance")
    render_node = FakeNode("renderMain")
    output_definition = types.SimpleNamespace(
        name="primary",
        path="C:/renders/renderMain.####.exr",
        extension="exr",
        aov_identifier="",
    )
    compat = types.SimpleNamespace(get_node=lambda name: instance_node)
    plugin = types.SimpleNamespace(KatanaInstancePlugin=FakeKatanaInstancePlugin)
    render = types.SimpleNamespace(
        get_default_renderer=lambda: "prman",
        get_render_node=lambda node: render_node,
        get_output_definitions=lambda node: [output_definition],
    )
    _install_ayon_katana_package(
        monkeypatch,
        {
            "compat": compat,
            "plugin": plugin,
            "render": render,
        },
    )

    module_path = (
        PROJECT_ROOT
        / "client"
        / "ayon_katana"
        / "plugins"
        / "publish"
        / "collect_render.py"
    )
    module_spec = importlib.util.spec_from_file_location(
        "ayon_katana.plugins.publish.collect_render",
        module_path,
    )
    assert module_spec is not None
    assert module_spec.loader is not None
    module = importlib.util.module_from_spec(module_spec)
    monkeypatch.setitem(
        sys.modules,
        "ayon_katana.plugins.publish.collect_render",
        module,
    )
    module_spec.loader.exec_module(module)
    return module


def _new_creator(module):
    """Create a render creator without invoking AYON Core initialization."""
    creator = object.__new__(module.CreateRender)
    creator.create_context = types.SimpleNamespace(
        headless=True,
        host=types.SimpleNamespace(get_current_workfile=lambda: "C:/work/scene.katana"),
        get_current_folder_entity=lambda: {
            "attrib": {"frameStart": 1001, "frameEnd": 1002}
        },
    )
    return creator


def test_creator_exposes_render_target_and_publish_owned_handles(monkeypatch) -> None:
    """Render target and handle ownership must match the AYON contract."""
    module = _load_create_render_module(monkeypatch)
    creator = _new_creator(module)

    pre_create_keys = {
        definition.key for definition in creator.get_pre_create_attr_defs()
    }
    instance_keys = {definition.key for definition in creator.get_instance_attr_defs()}

    assert "render_target" in pre_create_keys
    assert "render_target" in instance_keys
    assert "use_handles" in pre_create_keys
    assert "use_handles" not in instance_keys


def test_created_render_instances_default_to_farm(monkeypatch) -> None:
    """Farm remains the default render target for new instances."""
    module = _load_create_render_module(monkeypatch)
    creator = _new_creator(module)

    created_instance = creator.create(
        "renderMain",
        {"families": []},
        {"use_selection": False},
    )

    assert {"render", "katana.render", "render.farm"} <= set(
        created_instance["families"]
    )
    assert created_instance["farm"] is True
    assert created_instance["render_settings_node"] == "renderSettingsMain"
    assert created_instance["creator_attributes"]["render_target"] == "farm"
    assert "use_handles" not in created_instance["creator_attributes"]
    assert created_instance["publish_attributes"]["CollectAssetHandles"] == {
        "use_handles": True
    }


def test_created_local_render_instances_do_not_use_farm_family(monkeypatch) -> None:
    """Local render targets persist without the farm submission family."""
    module = _load_create_render_module(monkeypatch)
    creator = _new_creator(module)

    created_instance = creator.create(
        "renderMain",
        {"families": ["render.farm"]},
        {"render_target": "local", "use_selection": False},
    )

    assert {"render", "katana.render"} <= set(created_instance["families"])
    assert "render.farm" not in created_instance["families"]
    assert created_instance["farm"] is False
    assert created_instance["creator_attributes"]["render_target"] == "local"


def test_created_existing_frame_render_instances_do_not_use_farm_family(
    monkeypatch,
) -> None:
    """Existing-frame renders persist as non-farm without changing defaults."""
    module = _load_create_render_module(monkeypatch)
    creator = _new_creator(module)

    created_instance = creator.create(
        "renderMain",
        {"families": ["render.farm"]},
        {"render_target": "local_no_render", "use_selection": False},
    )

    assert {"render", "katana.render"} <= set(created_instance["families"])
    assert "render.farm" not in created_instance["families"]
    assert created_instance["farm"] is False
    assert created_instance["creator_attributes"]["render_target"] == "local_no_render"


def test_context_driven_product_rename_refreshes_render_node_references(
    monkeypatch,
) -> None:
    """A context edit cannot leave a stale outer render-group reference."""
    module = _load_create_render_module(monkeypatch)
    creator = _new_creator(module)
    imprints = []
    module.instances.imprint = lambda node, data: imprints.append(
        (node.getName(), data.copy())
    )
    created_instance = creator.create(
        "renderStoryboardMain",
        {"families": []},
        {"use_selection": False},
    )

    class Changes:
        """Minimal AYON change set for a product-name update."""

        changed_keys = {"productName"}

        def __getitem__(self, key: str):
            assert key == "productName"
            return types.SimpleNamespace(new_value="renderB04_context_mismatchMain")

    creator.update_instances([(created_instance, Changes())])

    assert created_instance["instance_node"] == "renderB04_context_mismatchMain"
    assert created_instance["render_node"] == "renderMain"
    assert created_instance["render_settings_node"] == "renderSettingsMain"
    assert imprints[-1][0] == "renderB04_context_mismatchMain"


def test_creator_rejects_unknown_render_target(monkeypatch) -> None:
    """Only the explicit farm and local targets are supported."""
    module = _load_create_render_module(monkeypatch)
    creator = _new_creator(module)

    with pytest.raises(FakeCreatorError, match="Unsupported Katana render target"):
        creator.create(
            "renderMain",
            {"families": []},
            {"render_target": "hybrid", "use_selection": False},
        )


def test_creator_expands_cut_range_with_task_handles(monkeypatch) -> None:
    """Creator frame inputs are cut frames, not already-expanded render frames."""
    module = _load_create_render_module(monkeypatch)
    creator = _new_creator(module)
    creator.create_context = types.SimpleNamespace(
        headless=True,
        host=types.SimpleNamespace(get_current_workfile=lambda: "C:/work/scene.katana"),
        get_current_folder_entity=lambda: {
            "attrib": {"frameStart": 1001, "frameEnd": 1050}
        },
        get_current_task_entity=lambda: {"attrib": {"handleStart": 8, "handleEnd": 8}},
    )
    graph_arguments = {}

    def create_render_graph(**kwargs):
        graph_arguments.update(kwargs)
        return FakeNode("renderMain")

    module.render.create_render_graph = create_render_graph
    creator.create(
        "renderMain",
        {"families": []},
        {
            "frame_start": 1001,
            "frame_end": 1050,
            "use_handles": True,
            "use_selection": False,
        },
    )

    assert graph_arguments["frame_start"] == 993
    assert graph_arguments["frame_end"] == 1058


def test_creator_preserves_valid_zero_frame_defaults(monkeypatch) -> None:
    """Frame zero is a valid AYON cut-frame value."""
    module = _load_create_render_module(monkeypatch)
    creator = _new_creator(module)
    creator.create_context.get_current_folder_entity = lambda: {
        "attrib": {"frameStart": 0, "frameEnd": 0}
    }

    assert creator._current_frame_range() == (0, 0)


def test_creator_removes_incomplete_instance_when_graph_creation_fails(
    monkeypatch,
) -> None:
    """A failed render graph must not leave a Publisher ghost instance."""
    module = _load_create_render_module(monkeypatch)
    creator = _new_creator(module)
    module.render.create_render_graph = lambda **_kwargs: (_ for _ in ()).throw(
        RuntimeError("graph failure")
    )

    with pytest.raises(FakeCreatorError, match="Katana render creator failed"):
        creator.create("renderMain", {"families": []}, {"use_selection": False})

    assert creator.created_instance.transient_data["node"].deleted
    assert creator.removed_instance is creator.created_instance


def test_creator_rejects_an_empty_renderer_configuration(monkeypatch) -> None:
    """An empty renderer setting must not select an arbitrary registry entry."""
    module = _load_create_render_module(monkeypatch, default_renderer="")
    creator = _new_creator(module)

    with pytest.raises(FakeCreatorError, match="renderer is not configured"):
        creator.create("renderMain", {"families": []}, {"use_selection": False})


@pytest.mark.parametrize("render_target", ["local", "local_no_render"])
def test_collector_preserves_non_farm_target_and_removes_farm_family(
    monkeypatch,
    render_target: str,
) -> None:
    """Collected render data follows each persisted non-farm render target."""
    module = _load_collect_render_module(monkeypatch)
    instance = types.SimpleNamespace(
        data={
            "instance_node": "renderInstance",
            "families": ["render", "katana.render", "render.farm"],
            "creator_attributes": {
                "render_target": render_target,
                "review": False,
            },
            "frameStartHandle": 1001,
            "frameEndHandle": 1002,
            "byFrameStep": 1,
        }
    )

    module.CollectRender().process(instance)

    assert instance.data["farm"] is False
    assert instance.data["multipartExr"] is False
    assert "render.farm" not in instance.data["families"]
    assert instance.data["creator_attributes"]["render_target"] == render_target


def test_server_settings_expose_render_target_without_renderer_fallback() -> None:
    """Settings expose all explicit targets without arbitrary renderer fallback."""
    settings_dir = PROJECT_ROOT / "server" / "settings"
    defaults_source = (settings_dir / "main.py").read_text(encoding="utf-8")
    create_source = (settings_dir / "create.py").read_text(encoding="utf-8")
    settings_tree = ast.parse(defaults_source)
    defaults_assignment = next(
        node
        for node in settings_tree.body
        if isinstance(node, ast.Assign)
        and any(
            isinstance(target, ast.Name) and target.id == "DEFAULT_VALUES"
            for target in node.targets
        )
    )
    defaults = ast.literal_eval(defaults_assignment.value)

    assert "def render_targets_enum" in create_source
    assert '"local_no_render", "label": "Use existing frames"' in create_source
    assert "first available renderer" not in create_source
    assert defaults["create"]["CreateRender"]["default_render_target"] == "farm"
    assert defaults["publish"]["CollectLocalRenderInstances"]["enabled"] is True
    assert defaults["publish"]["ExtractLocalRender"]["enabled"] is True
