"""Collect render products from Katana output nodes."""

from __future__ import annotations

import os
import re
from pathlib import Path

import pyblish.api

from ayon_katana.api import compat, plugin, render

_FRAME_TOKEN_PATTERN = re.compile(r"(#+)")


def expand_output_pattern(
    output_pattern: str,
    frame_start: int,
    frame_end: int,
    frame_step: int,
) -> list[str]:
    """Expand Katana ``#`` padding into concrete output file paths."""
    if frame_end < frame_start:
        raise RuntimeError(f"Invalid Katana render range: {frame_start}-{frame_end}.")
    if frame_step < 1:
        raise RuntimeError(f"Invalid Katana render frame step: {frame_step}.")
    output = []
    for frame in range(frame_start, frame_end + 1, frame_step):
        filepath = _FRAME_TOKEN_PATTERN.sub(
            lambda match, value=str(frame): value.zfill(len(match.group(1))),
            output_pattern,
        )
        output.append(os.path.normpath(filepath))
    return output


def collect_expected_files_by_aov(
    output_definitions: list[render.RenderOutputDefinition],
    frame_start: int,
    frame_end: int,
    frame_step: int,
) -> dict[str, list[str]]:
    """Return AYON's expected-files mapping from Katana outputs."""
    expected_files_by_aov: dict[str, list[str]] = {}
    for output_definition in output_definitions:
        aov_identifier = output_definition.aov_identifier
        if aov_identifier in expected_files_by_aov:
            label = aov_identifier or "main"
            raise RuntimeError(f"Multiple Katana outputs use AOV identifier {label!r}.")
        expected_files_by_aov[aov_identifier] = expand_output_pattern(
            output_definition.path,
            frame_start,
            frame_end,
            frame_step,
        )
    return expected_files_by_aov


class CollectRender(plugin.KatanaInstancePlugin):
    """Collect enabled render products."""

    label = "Collect Render Products"
    order = pyblish.api.CollectorOrder + 0.410
    families = ["render", "katana.render"]

    def process(self, instance) -> None:
        """Collect render outputs and expected files."""
        creator_attributes = instance.data.get("creator_attributes") or {}
        render_target = creator_attributes.get("render_target", "farm")
        if render_target not in {"farm", "local", "local_no_render"}:
            raise RuntimeError(f"Unsupported Katana render target: {render_target!r}.")
        instance_node = compat.get_node(instance.data.get("instance_node"))
        if instance_node is None:
            raise RuntimeError("Katana render instance node must be collected first.")
        output_definitions = render.get_output_definitions(instance_node)
        if not output_definitions:
            raise RuntimeError("Katana render instance has no enabled outputs.")
        for output_definition in output_definitions:
            if not output_definition.path:
                raise RuntimeError(
                    f"Katana output {output_definition.name!r} has no render path."
                )

        expected_files_by_aov = collect_expected_files_by_aov(
            output_definitions,
            int(instance.data["frameStartHandle"]),
            int(instance.data["frameEndHandle"]),
            int(instance.data["byFrameStep"]),
        )
        output_patterns = [definition.path for definition in output_definitions]
        first_expected_files = next(iter(expected_files_by_aov.values()))
        output_directory = str(Path(first_expected_files[0]).parent)
        instance.data["farm"] = render_target == "farm"
        instance.data.update(
            {
                "expectedFiles": [expected_files_by_aov],
                "files": output_patterns,
                "outputDir": output_directory,
                "multipartExr": False,
                "attachTo": [],
            }
        )
        families = instance.data.setdefault("families", [])
        for family in ("render", "katana.render"):
            if family not in families:
                families.append(family)
        if instance.data["farm"] and "render.farm" not in families:
            families.append("render.farm")
        if not instance.data["farm"] and "render.farm" in families:
            families.remove("render.farm")
        review = bool((instance.data.get("creator_attributes") or {}).get("review"))
        if review and "review" not in families:
            families.append("review")
        if not review and "review" in families:
            families.remove("review")
