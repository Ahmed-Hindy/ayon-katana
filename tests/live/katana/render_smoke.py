"""Real one-frame local render smoke executed inside headless Katana.

The suite uses an existing valid AYON render graph from the launch workfile, saves
it to a disposable copy, redirects one output into the live-test artifact folder,
and renders exactly one frame through the production local-render extractor.
The artist's original workfile is never saved by this test.
"""

from __future__ import annotations

import json
import os
import traceback
from pathlib import Path

import pyblish.api

from ayon_katana.api import instances, render, workio
from ayon_katana.plugins.publish.extract_local_render import ExtractLocalRender

OUT = Path(os.environ["AYON_KATANA_LIVE_OUT"]).resolve()
RESULT = Path(os.environ["AYON_KATANA_LIVE_RESULT"]).resolve()
APPLICATION = os.environ["AYON_KATANA_LIVE_APPLICATION"]


def _restore_workfile(original_workfile: str | None) -> None:
    """Restore the launch workfile without saving changes into it."""
    if original_workfile and Path(original_workfile).is_file():
        workio.open_workfile(original_workfile)
    else:
        workio.new_workfile()


def _render_instance():
    """Return the first complete persisted render instance in the scene."""
    for instance_node, data in instances.iter_instances():
        if data.get("productType") != "render":
            continue
        render_node = render.get_render_node(instance_node)
        settings_node = render.get_settings_node(instance_node)
        definitions = render.get_output_definitions(instance_node)
        if render_node is not None and settings_node is not None and definitions:
            return instance_node, data, render_node, settings_node, definitions[0]
    return None


def main() -> None:
    """Render one frame from a disposable copy of an existing render graph."""
    result = {
        "success": False,
        "application": APPLICATION,
        "checks": [],
        "coverage_gaps": [],
        "observations": {},
    }
    original_workfile = workio.get_current_workfile()
    try:
        selected = _render_instance()
        if selected is None:
            result["coverage_gaps"].append(
                "The launch workfile has no complete persisted Render instance."
            )
            result["success"] = True
            return

        instance_node, instance_data, render_node, settings_node, definition = selected
        settings = render.get_effective_render_settings(settings_node)
        renderers = render.get_registered_renderers()
        result["observations"]["registered_renderers"] = renderers
        result["observations"]["renderer"] = settings.renderer
        result["observations"]["camera"] = settings.camera
        result["observations"]["resolution"] = settings.resolution_name
        if not settings.renderer or settings.renderer not in renderers:
            result["coverage_gaps"].append(
                f"Render instance renderer {settings.renderer!r} is not registered."
            )
            result["success"] = True
            return
        if not settings.camera:
            result["coverage_gaps"].append(
                "Render instance has no effective camera; one-frame render skipped."
            )
            result["success"] = True
            return

        frame_range = render.get_render_frame_range(render_node)
        frame = frame_range.start
        scene_path = OUT / "render-smoke.katana"
        output_pattern = OUT / "render-smoke.####.exr"
        expected_path = OUT / f"render-smoke.{frame:04d}.exr"
        scene_path.parent.mkdir(parents=True, exist_ok=True)

        workio.save_workfile(str(scene_path))
        render.update_render_graph(
            instance_node=instance_node,
            product_name=instance_data.get("productName") or "LiveRenderSmoke",
            output_name=definition.name or "primary",
            output_path=output_pattern.as_posix(),
            extension="exr",
            channel=definition.channel or "beauty",
            renderer=settings.renderer,
            camera=settings.camera,
            frame_start=frame,
            frame_end=frame,
            frame_step=1,
            resolution=settings.resolution_name,
        )
        workio.save_workfile(str(scene_path))

        context = pyblish.api.Context()
        context.data["currentFile"] = str(scene_path)
        item = context.create_instance("LiveRenderSmoke")
        item.data.update(
            farm=False,
            creator_attributes={"render_target": "local"},
            expectedFiles=[{"beauty": [str(expected_path)]}],
            render_node=render_node.getName(),
            frameStartHandle=frame,
            frameEndHandle=frame,
            byFrameStep=1,
        )
        ExtractLocalRender().process(item)
        assert expected_path.is_file()
        assert expected_path.stat().st_size > 0
        result["observations"]["frame"] = frame
        result["observations"]["output_bytes"] = expected_path.stat().st_size
        result["checks"].append(
            "one-frame local render through production ExtractLocalRender"
        )
        result["success"] = True
    except Exception:
        result["error_type"] = "RenderSmokeFailure"
        result["error"] = traceback.format_exc()
    finally:
        try:
            _restore_workfile(original_workfile)
        except Exception:
            result["success"] = False
            result["restore_error"] = traceback.format_exc()

        RESULT.parent.mkdir(parents=True, exist_ok=True)
        RESULT.write_text(
            json.dumps(result, indent=2, sort_keys=True),
            encoding="utf-8",
        )
        print(json.dumps(result, indent=2, sort_keys=True))

    raise SystemExit(0 if result["success"] else 1)


main()
