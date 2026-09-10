"""BETA/WIP read-only compatibility smoke for an existing AYON Katana workfile."""

from __future__ import annotations

import hashlib
import json
import os
import traceback
from pathlib import Path

import pyblish.api
from ayon_core.pipeline import registered_host
from ayon_core.pipeline.create import CreateContext
from Katana import KatanaFile

import ayon_katana
from ayon_katana.api import dependencies, instances, render
from ayon_katana.plugins.publish.collect_render import CollectRender
from ayon_katana.plugins.publish.collect_render_frame_range import (
    CollectRenderFrameRange,
)
from ayon_katana.plugins.publish.collect_render_node import CollectRenderNode
from ayon_katana.plugins.publish.collect_render_settings import CollectRenderSettings
from ayon_katana.plugins.publish.validate_render import ValidateRender
from ayon_katana.plugins.publish.validate_render_colorspace import (
    ValidateRenderColorspace,
)
from ayon_katana.plugins.publish.validate_render_output_extensions import (
    ValidateRenderOutputExtensions,
)
from ayon_katana.plugins.publish.validate_render_output_names import (
    ValidateRenderOutputNames,
)
from ayon_katana.plugins.publish.validate_render_output_paths import (
    ValidateRenderOutputPaths,
)
from ayon_katana.plugins.publish.validate_render_output_tokens import (
    ValidateRenderOutputTokens,
)
from ayon_katana.plugins.publish.validate_render_resolution import (
    ValidateRenderResolution,
)
from ayon_katana.plugins.publish.validate_workfile_context import (
    ValidateWorkfileContext,
)

RESULT = Path(os.environ["AYON_KATANA_LIVE_RESULT"])
ROOT = Path(os.environ["AYON_KATANA_LIVE_ROOT"]).resolve()
APPLICATION = os.environ["AYON_KATANA_LIVE_APPLICATION"]
WORKFILE = Path(os.environ["AYON_KATANA_LIVE_WORKFILE"]).resolve()


def digest(path: Path) -> str:
    """Return SHA-256 for read-only fixture verification."""
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> None:
    """Load and inspect one existing workfile without saving it."""
    result = {
        "success": False,
        "application": APPLICATION,
        "workfile": str(WORKFILE),
        "checks": [],
        "coverage_gaps": [],
    }
    before = None
    try:
        if not WORKFILE.is_file():
            raise RuntimeError(f"Existing workfile does not exist: {WORKFILE}")
        before = digest(WORKFILE)
        addon_path = Path(ayon_katana.__file__).resolve()
        assert ROOT / "client" in addon_path.parents, addon_path

        KatanaFile.Load(WORKFILE.as_posix())
        host = registered_host()
        assert host is not None and host.name == "katana"

        workfile_data = host.get_context_data().get("workfile")
        if workfile_data:
            publish = pyblish.api.Context()
            publish.data["projectName"] = host.get_current_project_name()
            item = publish.create_instance("workfileExisting")
            item.data.update(workfile_data)
            ValidateWorkfileContext().process(item)
            result["checks"].append("embedded workfile context validates")
        else:
            result["coverage_gaps"].append(
                "No embedded workfile creator metadata was found; context "
                "validation skipped."
            )

        create_context = CreateContext(host, headless=True)
        result["creator_instance_count"] = len(create_context.instances)
        result["creator_instances"] = [
            {
                "id": instance.id,
                "creator": instance.creator_identifier,
                "product": instance.get("productName"),
                "instance_node": instance.get("instance_node"),
            }
            for instance in create_context.instances
        ]
        result["checks"].append("existing creator instances recollect headlessly")

        persisted = list(instances.iter_instances())
        render_instances = [
            data for _node, data in persisted if data.get("productType") == "render"
        ]
        result["persisted_instance_count"] = len(persisted)
        result["render_instance_count"] = len(render_instances)
        if render_instances:
            registered_renderers = set(render.get_registered_renderers())
            render_results = []
            for index, render_data in enumerate(render_instances):
                publish = pyblish.api.Context()
                publish.data.update(
                    projectName=host.get_current_project_name(),
                    folderPath=host.get_current_folder_path(),
                    task=host.get_current_task_name(),
                )
                frame_start, frame_end = render.get_project_frame_range()
                publish.data.update(
                    frameStart=frame_start,
                    frameEnd=frame_end,
                    frameStep=1,
                )
                item = publish.create_instance(f"renderExisting{index}")
                item.data.update(render_data)
                for collector in (
                    CollectRenderNode,
                    CollectRenderFrameRange,
                    CollectRender,
                    CollectRenderSettings,
                ):
                    collector().process(item)

                renderer_name = str(item.data.get("renderer") or "")
                validators = [
                    ValidateRenderOutputNames,
                    ValidateRenderOutputExtensions,
                    ValidateRenderOutputPaths,
                    ValidateRenderOutputTokens,
                    ValidateRenderResolution,
                    ValidateRenderColorspace,
                ]
                if not renderer_name or renderer_name in registered_renderers:
                    validators.insert(0, ValidateRender)
                else:
                    result["coverage_gaps"].append(
                        f"Renderer {renderer_name!r} is not registered in "
                        f"{APPLICATION}; renderer-registration validation skipped "
                        f"for {item.data.get('productName') or item.name!r}."
                    )
                for validator in validators:
                    validator().process(item)
                render_results.append(
                    {
                        key: item.data.get(key)
                        for key in (
                            "productName",
                            "instance_node",
                            "render_node",
                            "render_settings_node",
                            "renderer",
                            "camera",
                            "resolutionWidth",
                            "resolutionHeight",
                            "colorspace",
                            "colorspaceConfig",
                        )
                    }
                )
            result["renders"] = render_results
            result["checks"].append(
                "all existing native render graphs recollect and validate"
            )
        else:
            result["coverage_gaps"].append(
                "Workfile contains no persisted render instance; render compatibility "
                "skipped."
            )

        references = dependencies.collect_workfile_references()
        result["reference_count"] = len(references)
        result["reference_nodes"] = sorted({item.node_name for item in references})
        result["checks"].append("existing workfile dependency scan completes")
        result["success"] = True
    except Exception as exc:
        result["error_type"] = type(exc).__name__
        result["error"] = traceback.format_exc()
    finally:
        if before is None or not WORKFILE.is_file():
            result["fixture_unchanged"] = None
        else:
            result["fixture_unchanged"] = digest(WORKFILE) == before
            if not result["fixture_unchanged"]:
                result["success"] = False

    RESULT.parent.mkdir(parents=True, exist_ok=True)
    RESULT.write_text(json.dumps(result, indent=2, sort_keys=True), encoding="utf-8")
    print(json.dumps(result, indent=2, sort_keys=True))
    raise SystemExit(0 if result["success"] else 1)


main()
