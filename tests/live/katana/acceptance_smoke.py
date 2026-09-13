"""High-level live acceptance checks executed inside real headless Katana.

The suite deliberately uses disposable workfile copies and local representation
fixtures. It exercises production workflows without publishing versions to AYON,
submitting Deadline jobs, or modifying the artist's source workfile.
"""

from __future__ import annotations

import json
import os
import runpy
import traceback
import types
from pathlib import Path

import pyblish.api
from ayon_core.pipeline import registered_host
from ayon_core.pipeline.create import CreateContext
from Katana import NodegraphAPI

import ayon_katana
from ayon_katana.api import (
    compat,
    containers,
    instances,
    render,
    workfile_template_builder,
    workio,
)
from ayon_katana.plugins.inventory.select_containers import SelectInScene
from ayon_katana.plugins.inventory.select_managed_sources import SelectManagedSources
from ayon_katana.plugins.load.load_image import ImageLoader
from ayon_katana.plugins.load.load_katana import KatanaImportLoader
from ayon_katana.plugins.publish.collect_nodegraph import (
    CollectNodegraph,
    CollectNodegraphDependencies,
)
from ayon_katana.plugins.publish.extract_nodegraph import ExtractNodegraph
from ayon_katana.plugins.publish.validate_nodegraph import ValidateNodegraph
from ayon_katana.plugins.workfile_build.load_placeholder import (
    KatanaPlaceholderLoadPlugin,
)

OUT = Path(os.environ["AYON_KATANA_LIVE_OUT"]).resolve()
RESULT = Path(os.environ["AYON_KATANA_LIVE_RESULT"]).resolve()
ROOT = Path(os.environ["AYON_KATANA_LIVE_ROOT"]).resolve()
APPLICATION = os.environ["AYON_KATANA_LIVE_APPLICATION"]


def _loader_helpers() -> dict:
    """Load the shared live representation helpers without making tests a package."""
    return runpy.run_path(
        str(ROOT / "tests" / "live" / "katana" / "integration_loaders.py")
    )


def _publish_instance(name: str, created_instance):
    """Wrap a real CreatedInstance in a minimal Pyblish instance."""
    context = pyblish.api.Context()
    item = context.create_instance(name)
    item.data.update(created_instance.data_to_store())
    return item


def _restore_workfile(original_workfile: str | None) -> None:
    """Restore the launch workfile without ever saving back to it."""
    if original_workfile and Path(original_workfile).is_file():
        workio.open_workfile(original_workfile)
    else:
        workio.new_workfile()


def exercise_workfile_roundtrip(host, result: dict) -> None:
    """Save As, reopen, and recollect a persisted creator instance natively."""
    original_workfile = workio.get_current_workfile()
    marker_name = "AYON_LiveAcceptance_RoundtripMarker"
    product_name = "LivePersistedImage"
    roundtrip_path = OUT / "acceptance-roundtrip.katana"
    save_as_path = OUT / "acceptance-save-as.katana"

    try:
        marker = NodegraphAPI.CreateNode("Group", NodegraphAPI.GetRootNode())
        marker.setName(marker_name)
        marker.addOutputPort("out")

        create_context = CreateContext(host, headless=True)
        created = create_context.create(
            "io.ayon.creators.katana.image",
            product_name,
            pre_create_data={
                "use_selection": False,
                "render_target": "local_no_render",
                "review": False,
                "extension": "exr",
                "single_frame": True,
                "frame": render.get_project_frame_range()[0],
                "output_path": str(OUT / "persisted-image.exr"),
            },
        )
        create_context.save_changes()
        created_instance_id = created["instance_id"]
        created_product_name = created["productName"]
        persisted_node_name = created["instance_node"]
        persisted_node = created.transient_data["node"]
        result["observations"]["persisted_instance_before_save"] = instances.read(
            persisted_node
        )

        saved = Path(workio.save_workfile(str(roundtrip_path)))
        assert saved.is_file()
        assert Path(workio.get_current_workfile()).resolve() == saved.resolve()

        workio.new_workfile()
        assert NodegraphAPI.GetNode(marker_name) is None
        workio.open_workfile(str(roundtrip_path))
        assert NodegraphAPI.GetNode(marker_name) is not None

        persisted_after_reload = [
            {
                "node": node.getName(),
                "data": data,
            }
            for node, data in instances.iter_instances()
        ]
        result["observations"]["persisted_instances_after_reload"] = (
            persisted_after_reload
        )

        recollected = CreateContext(host, headless=True)
        result["observations"]["create_context_instances_after_reload"] = [
            {
                "product": instance.get("productName"),
                "creator": instance.creator_identifier,
                "instance_node": instance.get("instance_node"),
            }
            for instance in recollected.instances
        ]
        matches = [
            instance
            for instance in recollected.instances
            if instance.get("instance_id") == created_instance_id
        ]
        assert len(matches) == 1
        assert matches[0].get("productName") == created_product_name
        recollected_node_name = matches[0].get("instance_node")
        assert recollected_node_name
        assert NodegraphAPI.GetNode(recollected_node_name) is not None
        result["observations"]["persisted_image_node_before_reload"] = (
            persisted_node_name
        )
        result["observations"]["persisted_image_node_after_reload"] = (
            recollected_node_name
        )

        second_saved = Path(workio.save_workfile(str(save_as_path)))
        assert second_saved.is_file()
        workio.new_workfile()
        workio.open_workfile(str(second_saved))
        assert NodegraphAPI.GetNode(marker_name) is not None
        second_recollected = CreateContext(host, headless=True)
        second_matches = [
            instance
            for instance in second_recollected.instances
            if instance.get("instance_id") == created_instance_id
        ]
        assert len(second_matches) == 1
        assert second_matches[0].get("productName") == created_product_name
        second_recollected_node_name = second_matches[0].get("instance_node")
        assert second_recollected_node_name
        assert NodegraphAPI.GetNode(second_recollected_node_name) is not None
        result["observations"]["persisted_image_node_after_second_reload"] = (
            second_recollected_node_name
        )
        result["checks"].append(
            "workfile Save As/new/open and creator persistence survive native reload"
        )
    finally:
        _restore_workfile(original_workfile)


def exercise_nodegraph_roundtrip(host, result: dict) -> None:
    """Publish a real Group, collect dependencies, and load the export back."""
    helpers = _loader_helpers()
    representation_context = helpers["representation_context"]

    image_path = OUT / "nodegraph-input.exr"
    image_path.write_bytes(b"live nodegraph dependency")
    dependency_context = representation_context(
        image_path,
        "acceptance-nodegraph-dependency",
        representation_name="exr",
        product_name="LiveNodegraphDependency",
        product_type="image",
    )
    dependency_node = ImageLoader().load(
        dependency_context,
        name="LiveNodegraphDependency",
        namespace="liveAcceptance",
    )

    source = NodegraphAPI.CreateNode("Group", NodegraphAPI.GetRootNode())
    source.setName("AYON_LiveAcceptance_NodegraphSource")
    source.addOutputPort("out")
    compat.set_parent(dependency_node, source)
    dependency_node.getOutputPort("out").connect(source.getReturnPort("out"))
    compat.set_selected_nodes([source])

    create_context = CreateContext(host, headless=True)
    created = create_context.create(
        "io.ayon.creators.katana.nodegraph",
        "LiveNodegraphAcceptance",
        pre_create_data={},
    )
    item = _publish_instance("nodegraphAcceptance", created)
    CollectNodegraph().process(item)
    CollectNodegraphDependencies().process(item)
    assert item.data["inputRepresentations"] == [
        dependency_context["representation"]["id"]
    ]
    ValidateNodegraph().process(item)

    staging_dir = OUT / "nodegraph-extract"
    extractor = ExtractNodegraph()
    extractor.staging_dir = lambda _instance: str(staging_dir)
    extractor.process(item)
    representation = item.data["representations"][0]
    exported_path = Path(representation["stagingDir"]) / representation["files"]
    assert exported_path.is_file()

    load_context = representation_context(
        exported_path,
        "acceptance-nodegraph-export",
        representation_name="katana",
        product_name="LiveNodegraphAcceptance",
        product_type="nodegraph",
    )
    loaded_node = KatanaImportLoader().load(
        load_context,
        name="LiveNodegraphReloaded",
        namespace="liveAcceptance",
    )
    loaded_container = containers.parse_container(loaded_node)
    assert loaded_container is not None
    assert loaded_container["representation"] == "acceptance-nodegraph-export"
    KatanaImportLoader().remove(loaded_container)

    original_container = containers.parse_container(dependency_node)
    if original_container is not None:
        ImageLoader().remove(original_container)
    created_node = created.transient_data.get("node")
    if created_node is not None:
        created_node.delete()
    if NodegraphAPI.GetNode(source.getName()) is not None:
        source.delete()
    compat.set_selected_nodes([])
    result["checks"].append(
        "nodegraph create/collect/dependency/validate/extract/load-back roundtrip"
    )


class _BuilderCache:
    """Minimal shared-data surface used by real Katana placeholder code."""

    def __init__(self) -> None:
        self._data: dict[str, object] = {}

    def get_shared_populate_data(self, key: str):
        """Return cached builder data."""
        return self._data.get(key)

    def set_shared_populate_data(self, key: str, value) -> None:
        """Store cached builder data."""
        self._data[key] = value


def exercise_workfile_builder_and_inventory(result: dict) -> None:
    """Exercise real placeholder graph behavior and Scene Inventory actions."""
    helpers = _loader_helpers()
    representation_context = helpers["representation_context"]
    image_path = OUT / "builder-inventory-input.exr"
    image_path.write_bytes(b"live builder inventory fixture")
    load_context = representation_context(
        image_path,
        "acceptance-builder-image",
        representation_name="exr",
        product_name="LiveBuilderImage",
        product_type="image",
    )
    loader = ImageLoader()
    container_node = loader.load(
        load_context,
        name="LiveBuilderImage",
        namespace="liveAcceptance",
    )
    container = containers.parse_container(container_node)
    assert container is not None

    SelectInScene().process([container])
    assert compat.get_selected_nodes() == [container_node]
    managed_source = containers.find_managed_node(
        container_node, containers.SOURCE_ROLE
    )
    assert managed_source is not None
    SelectManagedSources().process([container])
    assert compat.get_selected_nodes() == [managed_source]
    result["checks"].append("Scene Inventory selects containers and managed sources")

    placeholder_plugin = KatanaPlaceholderLoadPlugin(_BuilderCache())
    placeholder_node = placeholder_plugin.create_placeholder(
        {
            "product_name": "LiveBuilderImage",
            "loader": "ImageLoader",
        }
    )
    placeholders = placeholder_plugin.collect_placeholders()
    matching = [
        placeholder
        for placeholder in placeholders
        if placeholder.scene_identifier == placeholder_node.getName()
    ]
    assert len(matching) == 1
    assert matching[0].data["loader"] == "ImageLoader"

    placeholder_plugin.load_succeed(matching[0], container_node)
    loaded = placeholder_plugin.get_loaded_containers(placeholder_node)
    assert [item["representation"] for item in loaded] == ["acceptance-builder-image"]
    placeholder_plugin.delete_placeholder(matching[0])
    assert NodegraphAPI.GetNode(placeholder_node.getName()) is placeholder_node
    assert placeholder_plugin._read(placeholder_node) is None

    nested_container = containers.parse_container(container_node)
    if nested_container is not None:
        loader.remove(nested_container)
    placeholder_node.delete()
    compat.set_selected_nodes([])
    result["checks"].append(
        "Workfile Builder placeholder create/collect/connect/consume behavior"
    )


def exercise_builder_trigger(result: dict) -> None:
    """Evaluate the configured Workfile Builder new-file trigger non-destructively."""
    original_workfile = workio.get_current_workfile()
    try:
        workio.new_workfile()
        matched = workfile_template_builder.trigger_on_new_file()
        result["observations"]["workfile_builder_profile_matched"] = bool(matched)
        if matched:
            result["checks"].append("configured Workfile Builder new-file trigger")
        else:
            result["coverage_gaps"].append(
                "No Workfile Builder profile matched the live AYON context."
            )
    finally:
        _restore_workfile(original_workfile)


def exercise_deadline_metadata(result: dict) -> None:
    """Build real Katana Deadline command metadata without submitting a job."""
    try:
        from ayon_katana.plugins.deadline.submit_katana_deadline import (
            KatanaSubmitDeadline,
        )
    except ImportError as exc:
        result["coverage_gaps"].append(
            f"AYON Deadline addon is unavailable in this launch: {exc}"
        )
        return

    scene_path = workio.get_current_workfile() or str(OUT / "deadline-scene.katana")
    fake_context = types.SimpleNamespace(data={"currentFile": scene_path})
    fake_instance = types.SimpleNamespace(
        name="LiveDeadline",
        context=fake_context,
        data={
            "families": ["render", "katana.render"],
            "render_node": "AYON_LiveDeadline_Render",
            "frameStartHandle": 1001,
            "frameEndHandle": 1002,
            "byFrameStep": 1,
        },
    )
    plugin = KatanaSubmitDeadline()
    plugin._instance = fake_instance
    plugin.scene_path = scene_path
    plugin_info = plugin.get_plugin_info()
    executable = Path(plugin_info["Executable"])
    assert executable.is_file()
    assert "--batch" in plugin_info["Arguments"]
    assert '--render-node="AYON_LiveDeadline_Render"' in plugin_info["Arguments"]

    job_info = types.SimpleNamespace(Plugin="", Frames="", Name="", BatchName="")
    plugin.get_job_info(job_info)
    assert job_info.Plugin == "CommandLine"
    assert job_info.Frames == "1001-1002x1"
    assert "[RENDER]" in job_info.Name
    result["checks"].append("Deadline Katana executable/job/plugin metadata")
    result["coverage_gaps"].append(
        "Deadline transport submission is intentionally not performed by "
        "live acceptance."
    )


def exercise_publish_discovery(result: dict) -> None:
    """Assert the real host registered the core Katana publish plug-ins."""
    discovered = {plugin.__name__ for plugin in pyblish.api.discover()}
    required = {
        "CollectImage",
        "CollectRender",
        "CollectUsdLayer",
        "ExtractNodegraph",
        "ExtractUsdLayer",
        "ValidateImage",
        "ValidateNodegraph",
        "ValidateUsdLayer",
    }
    missing = sorted(required - discovered)
    assert not missing, f"Missing discovered Katana publish plug-ins: {missing}"
    result["observations"]["pyblish_plugin_count"] = len(discovered)
    result["checks"].append("real Pyblish discovery includes core Katana plug-ins")


def main() -> None:
    """Run high-level disposable acceptance workflows in a real Katana process."""
    result = {
        "success": False,
        "application": APPLICATION,
        "checks": [],
        "coverage_gaps": [],
        "observations": {},
    }
    original_workfile = None
    try:
        addon_path = Path(ayon_katana.__file__).resolve()
        assert ROOT / "client" in addon_path.parents, addon_path
        host = registered_host()
        assert host is not None and host.name == "katana"
        assert host.is_installed is True
        original_workfile = workio.get_current_workfile()

        exercise_publish_discovery(result)
        exercise_workfile_roundtrip(host, result)
        exercise_nodegraph_roundtrip(host, result)
        exercise_workfile_builder_and_inventory(result)
        exercise_builder_trigger(result)
        exercise_deadline_metadata(result)

        result["observations"]["renderers"] = render.get_registered_renderers()
        result["coverage_gaps"].extend(
            [
                "AYON server publish integration is not executed to avoid creating "
                "test versions.",
                "GUI menu placement/actions require an interactive Katana session.",
                "Viewer thumbnail and viewport review capture require an interactive "
                "UI session.",
            ]
        )
        result["success"] = True
    except Exception as exc:
        result["error_type"] = type(exc).__name__
        result["error"] = traceback.format_exc()
    finally:
        try:
            if original_workfile is not None:
                _restore_workfile(original_workfile)
        except Exception:
            result["success"] = False
            result["restore_error"] = traceback.format_exc()

    RESULT.parent.mkdir(parents=True, exist_ok=True)
    RESULT.write_text(json.dumps(result, indent=2, sort_keys=True), encoding="utf-8")
    print(json.dumps(result, indent=2, sort_keys=True))
    raise SystemExit(0 if result["success"] else 1)


main()
