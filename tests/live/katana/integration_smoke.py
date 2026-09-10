"""BETA/WIP live AYON integration smoke executed inside real Katana."""

from __future__ import annotations

import json
import os
import runpy
import traceback
from pathlib import Path

import pyblish.api
from ayon_core.pipeline import CreatorError, registered_host
from ayon_core.pipeline.create import CreateContext, CreatorsSaveFailed
from ayon_core.pipeline.publish import PublishValidationError
from Katana import NodegraphAPI

import ayon_katana
from ayon_katana.api import context, instances, render, usd
from ayon_katana.plugins.publish.collect_image import CollectImage
from ayon_katana.plugins.publish.collect_render import CollectRender
from ayon_katana.plugins.publish.collect_render_frame_range import (
    CollectRenderFrameRange,
)
from ayon_katana.plugins.publish.collect_render_node import CollectRenderNode
from ayon_katana.plugins.publish.collect_render_settings import CollectRenderSettings
from ayon_katana.plugins.publish.collect_usd_layer import CollectUsdLayer
from ayon_katana.plugins.publish.extract_usd_layer import ExtractUsdLayer
from ayon_katana.plugins.publish.validate_image import ValidateImage
from ayon_katana.plugins.publish.validate_render_camera import ValidateRenderCamera
from ayon_katana.plugins.publish.validate_usd_layer import ValidateUsdLayer

OUT = Path(os.environ["AYON_KATANA_LIVE_OUT"]).resolve()
RESULT = Path(os.environ["AYON_KATANA_LIVE_RESULT"]).resolve()
ROOT = Path(os.environ["AYON_KATANA_LIVE_ROOT"]).resolve()
APPLICATION = os.environ["AYON_KATANA_LIVE_APPLICATION"]
PROJECT_NAME = os.environ["AYON_PROJECT_NAME"]
FOLDER_PATH = os.environ["AYON_FOLDER_PATH"]
TASK_NAME = os.environ["AYON_TASK_NAME"]


def root_names() -> set[str]:
    """Return names of direct root children."""
    return {node.getName() for node in NodegraphAPI.GetRootNode().getChildren()}


def publish_context(host) -> pyblish.api.Context:
    """Create the minimal real Pyblish context used by live collectors."""
    output = pyblish.api.Context()
    output.data.update(
        projectName=host.get_current_project_name(),
        folderPath=host.get_current_folder_path(),
        task=host.get_current_task_name(),
    )
    frame_start, frame_end = render.get_project_frame_range()
    output.data.update(frameStart=frame_start, frameEnd=frame_end, frameStep=1)
    return output


def publish_instance(
    publish: pyblish.api.Context,
    name: str,
    created_instance,
):
    """Wrap a real CreatedInstance in a real Pyblish instance."""
    item = publish.create_instance(name)
    item.data.update(created_instance.data_to_store())
    return item


def assert_creator_error_and_rollback(
    create_context: CreateContext,
    creator_identifier: str,
    product_name: str,
    pre_create_data: dict,
) -> str:
    """Assert known invalid creator settings remain AYON ``CreatorError``."""
    before = root_names()
    try:
        create_context.create(
            creator_identifier,
            product_name,
            pre_create_data=pre_create_data,
        )
    except CreatorError as exc:
        message = str(exc)
    else:
        raise AssertionError(
            f"Invalid creator unexpectedly succeeded: {creator_identifier}"
        )
    assert root_names() == before
    return message


def exercise_loader_transactions() -> None:
    """Run the loader-specific live integration module."""
    loader_module = runpy.run_path(
        str(ROOT / "tests" / "live" / "katana" / "integration_loaders.py")
    )
    loader_module["exercise_loaders"]()


def main() -> None:
    """Run the real AYON/Katana integration smoke."""
    result = {
        "success": False,
        "application": APPLICATION,
        "checks": [],
        "coverage_gaps": [],
        "observations": {},
    }
    try:
        addon_path = Path(ayon_katana.__file__).resolve()
        assert ROOT / "client" in addon_path.parents, addon_path
        host = registered_host()
        assert host is not None and host.name == "katana"
        assert host.get_current_project_name() == PROJECT_NAME
        assert host.get_current_folder_path() == FOLDER_PATH
        assert host.get_current_task_name() == TASK_NAME
        assert host.is_installed is True

        applied = context.apply_context_settings(host)
        assert applied["project_name"] == PROJECT_NAME
        assert applied["folder_path"] == FOLDER_PATH
        assert applied["task_name"] == TASK_NAME

        original_task_lookup = context._get_current_task_entity

        def fail_task_lookup():
            """Simulate an AYON/server lookup failure at the lifecycle boundary."""
            raise RuntimeError("live test injected task lookup failure")

        context._get_current_task_entity = fail_task_lookup
        try:
            context.apply_context_settings(host)
            assert context.apply_current_frame_range() is False
        finally:
            context._get_current_task_entity = original_task_lookup
        result["checks"].append("AYON lifecycle task lookup failures remain contained")

        create_context = CreateContext(host, headless=True)
        identifiers = {
            creator.identifier for creator in create_context.creators.values()
        }
        assert {
            "io.ayon.creators.katana.image",
            "io.ayon.creators.katana.usd_layer",
            "io.ayon.creators.katana.render",
        } <= identifiers

        image_error = assert_creator_error_and_rollback(
            create_context,
            "io.ayon.creators.katana.image",
            "LiveInvalidImage",
            {
                "use_selection": False,
                "render_target": "local_no_render",
                "extension": "definitely-invalid",
                "output_path": str(OUT / "invalid.image"),
            },
        )
        result["observations"]["invalid_image_creator"] = image_error

        usd_error = assert_creator_error_and_rollback(
            create_context,
            "io.ayon.creators.katana.usd_layer",
            "LiveInvalidUsd",
            {
                "use_selection": False,
                "usd_format": "definitely-invalid",
            },
        )
        result["observations"]["invalid_usd_creator"] = usd_error
        result["checks"].append(
            "known invalid creator settings use CreatorError and rollback"
        )

        publish = publish_context(host)
        image_source = NodegraphAPI.CreateNode("ImageRead", NodegraphAPI.GetRootNode())
        image_source.setName("AYON_Live_ImageSource")
        image_source_path = OUT / "input.exr"
        image_source_path.write_bytes(b"live image source")
        image_source.getParameter("file").setValue(image_source_path.as_posix(), 0.0)
        image_entry = create_context.create(
            "io.ayon.creators.katana.image",
            "LiveImage",
            pre_create_data={
                "use_selection": False,
                "render_target": "local_no_render",
                "review": False,
                "extension": "exr",
                "single_frame": True,
                "frame": render.get_project_frame_range()[0],
                "output_path": str(OUT / "LiveImage.exr"),
            },
        )
        image_node = image_entry.transient_data["node"]
        image_source.getOutputPort("out").connect(image_node.getInputPort("in"))
        image_item = publish_instance(publish, "imageLive", image_entry)
        CollectImage().process(image_item)
        ValidateImage().process(image_item)

        usd_source = NodegraphAPI.CreateNode(
            "UsdPrimCreate", NodegraphAPI.GetRootNode()
        )
        usd_source.setName("AYON_Live_UsdSource")
        prim_paths = usd_source.getParameter("primPaths")
        prim_paths.resizeArray(1)
        prim_paths.getChildByIndex(0).setValue("/LiveTest", 0.0)
        assert usd.is_native_usd_node(usd_source)
        usd_entry = create_context.create(
            "io.ayon.creators.katana.usd_layer",
            "LiveUsd",
            pre_create_data={
                "use_selection": False,
                "usd_format": "usda",
                "time_samples": "Current Frame",
                "samples_per_frame": 1.0,
                "export_method": "Keep Composition Arcs",
            },
        )
        usd_node = usd_entry.transient_data["node"]
        usd_source.getOutputPort("out").connect(usd_node.getInputPort("in"))
        usd_item = publish_instance(publish, "usdLive", usd_entry)
        CollectUsdLayer().process(usd_item)
        ValidateUsdLayer().process(usd_item)
        usd_staging = OUT / "usd-extract"
        extractor = ExtractUsdLayer()
        extractor.staging_dir = lambda _instance: str(usd_staging)
        extractor.process(usd_item)
        representation = usd_item.data["representations"][0]
        extracted_path = Path(representation["stagingDir"]) / representation["files"]
        assert extracted_path.is_file()
        result["checks"].append(
            "real Image and USD creators collect/validate; USD extracts"
        )

        renderer_names = render.get_registered_renderers()
        result["observations"]["renderers"] = renderer_names
        if renderer_names:
            render_entry = create_context.create(
                "io.ayon.creators.katana.render",
                "LiveRender",
                pre_create_data={
                    "use_selection": False,
                    "render_target": "local_no_render",
                    "review": False,
                    "renderer": renderer_names[0],
                    "output_path": str(OUT / "LiveRender.####.exr"),
                    "extension": "exr",
                    "channel": "beauty",
                    "camera": "",
                },
            )
            render_item = publish_instance(publish, "renderLive", render_entry)
            for collector in (
                CollectRenderNode,
                CollectRenderFrameRange,
                CollectRender,
                CollectRenderSettings,
            ):
                collector().process(render_item)
            render_node = NodegraphAPI.GetNode(render_item.data["render_node"])
            assert render_node is not None
            missing_type = render.get_scenegraph_location_type(
                render_node, "/__missing__"
            )
            assert missing_type == ""
            render_item.data["camera"] = "/__missing__"
            try:
                ValidateRenderCamera().process(render_item)
            except PublishValidationError as exc:
                assert "could not be resolved" in str(exc)
            else:
                raise AssertionError("Missing camera unexpectedly passed validation.")

            create_context.save_changes()
            before_name = render_entry.transient_data["node"].getName()
            before_data = instances.read(render_entry.transient_data["node"])
            settings_node = render.get_settings_node(
                render_entry.transient_data["node"]
            )
            assert settings_node is not None
            settings_node.delete()
            render_entry["productName"] = "LiveRenderDamagedRename"
            try:
                create_context.save_changes()
            except CreatorsSaveFailed:
                pass
            else:
                raise AssertionError("Damaged render graph unexpectedly saved.")
            after_node = render_entry.transient_data["node"]
            after_data = instances.read(after_node)
            assert after_node.getName() == before_name
            assert after_data.get("productName") == before_data.get("productName")
            result["checks"].append(
                "render missing-camera validation and damaged-graph preflight "
                "are transactional"
            )
        else:
            result["coverage_gaps"].append(
                "No registered renderer plugins; render creator/camera tests skipped."
            )

        exercise_loader_transactions()
        result["checks"].append("real Image/Alembic/USD/Katana loader transactions")
        result["success"] = True
    except Exception as exc:
        result["error_type"] = type(exc).__name__
        result["error"] = traceback.format_exc()

    RESULT.parent.mkdir(parents=True, exist_ok=True)
    RESULT.write_text(json.dumps(result, indent=2, sort_keys=True), encoding="utf-8")
    print(json.dumps(result, indent=2, sort_keys=True))
    raise SystemExit(0 if result["success"] else 1)


main()
