"""Submit Katana outputs to Deadline through CommandLine."""

from __future__ import annotations

import os

import pyblish.api
from ayon_core.pipeline import AYONPyblishPluginMixin
from ayon_deadline import abstract_submit_deadline

from ayon_katana.api import render


class KatanaSubmitDeadline(
    abstract_submit_deadline.AbstractSubmitDeadline,
    AYONPyblishPluginMixin,
):
    """Submit Render and ImageWrite outputs through CommandLine."""

    label = "Submit Output to Deadline"
    # Core's workfile integration must finish before Deadline resolves
    # ``use_published=True`` to the published scene path.
    order = pyblish.api.IntegratorOrder + 0.05
    hosts = ["katana"]
    families = ["render", "katana.render", "image", "katana.image"]
    targets = ["local"]
    settings_category = "deadline"

    def process(self, instance):
        """Submit farm output instances."""
        if not instance.data.get("farm"):
            self.log.debug("Katana farm rendering is disabled; skipping Deadline.")
            return
        super().process(instance)
        instance.data["outputDir"] = os.path.dirname(instance.data["files"][0])

    def get_job_info(self, job_info=None, **_kwargs):
        """Build Deadline job information for Katana batch mode."""
        instance = self._instance
        context = instance.context
        job_info.Plugin = "CommandLine"
        if not job_info.Frames:
            start = int(instance.data["frameStartHandle"])
            end = int(instance.data["frameEndHandle"])
            step = int(instance.data["byFrameStep"])
            job_info.Frames = f"{start}-{end}x{step}"

        filename = os.path.basename(context.data["currentFile"])
        families = set(instance.data.get("families") or [])
        job_kind = "IMAGE" if {"image", "katana.image"} & families else "RENDER"
        job_info.Name = f"{filename} - {instance.name} [{job_kind}]"
        job_info.BatchName = filename
        return job_info

    def get_plugin_info(self, **_kwargs):
        """Build Deadline CommandLine plugin data."""
        executable = render.get_katana_executable()
        render_node = self._instance.data.get("render_node") or self._instance.data.get(
            "image_write_node"
        )
        if not render_node:
            raise RuntimeError(
                "Katana Deadline submission has no Render or ImageWrite node."
            )
        arguments = (
            f'--batch --katana-file="{self.scene_path}" '
            f'-t <STARTFRAME>-<ENDFRAME> --render-node="{render_node}"'
        )
        return {
            "Executable": str(executable),
            "Arguments": arguments,
            "SceneFile": self.scene_path,
            "StartupDirectory": str(executable.parent),
            "ShellExecute": False,
            "SingleFramesOnly": False,
        }
