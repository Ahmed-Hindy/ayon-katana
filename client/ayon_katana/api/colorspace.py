"""Colorspace helpers for Katana render products."""

from __future__ import annotations

import os
from pathlib import Path
from typing import List, Optional

import attr
from ayon_core.pipeline.colorspace import get_ocio_config_colorspaces


@attr.s
class LayerMetadata:
    """Data class for Render Layer metadata."""

    products: List[RenderProduct] = attr.ib()


@attr.s
class RenderProduct:
    """Specific Render Product Parameter for submitting."""

    colorspace: str = attr.ib()
    productName: Optional[str] = attr.ib(default=None)


class ARenderProduct:
    """This is the minimal data structure required to get
    `ayon_core.pipeline.farm.pyblish_functions.create_instances_for_aov` to
    work with the Deadline addon's job submissions.
    """

    def __init__(self, aov_names: List[str], colorspace: str = ""):
        colorspace = colorspace or get_scene_linear_colorspace()
        products = [
            RenderProduct(colorspace=colorspace, productName=aov_name)
            for aov_name in aov_names
        ]
        self.layer_data = LayerMetadata(products=products)


def _get_ocio_config_path() -> str:
    config_path = os.environ.get("OCIO", "")
    if config_path and not Path(config_path).is_file():
        raise FileNotFoundError(f"OCIO config does not exist: {config_path!r}")
    return config_path


def get_imageio_file_rule_colorspace(
    filepath: str,
    context: dict,
    project_settings: Optional[dict] = None,
) -> str:
    """Return an AYON ImageIO file-rule colorspace for an image path.

    Callers should check representation metadata before evaluating host or
    global file rules. Configuration and Core API errors propagate.

    Args:
        filepath: Resolved image path used for file-rule matching.
        context: AYON load context containing project/folder/task entities.
        project_settings: Optional already-resolved project settings.

    Returns:
        Matched colorspace name, or an empty string when host management is
        disabled, context is incomplete, or no rule matches.
    """
    project = context.get("project") or {}
    project_name = project.get("name")
    if not project_name:
        return ""

    if project_settings is None:
        project_settings = context.get("project_settings")
    if project_settings is None:
        from ayon_core.settings import get_project_settings

        project_settings = get_project_settings(project_name)

    host_imageio = (project_settings.get("katana") or {}).get("imageio") or {}
    if not host_imageio.get("activate_host_color_management", True):
        return ""

    folder = context.get("folder") or {}
    task = context.get("task") or {}
    from ayon_core.pipeline.colorspace import (
        get_imageio_config_preset,
        get_imageio_file_rules,
        get_imageio_file_rules_colorspace_from_filepath,
    )

    config_data = get_imageio_config_preset(
        project_name,
        folder.get("path") or "",
        task.get("name") or "",
        "katana",
        os.environ.get("AYON_APP_NAME"),
        project_settings=project_settings,
    )
    if not config_data:
        return ""
    file_rules = get_imageio_file_rules(
        project_name,
        "katana",
        project_settings,
    )
    return str(
        get_imageio_file_rules_colorspace_from_filepath(
            filepath,
            "katana",
            project_name,
            config_data,
            file_rules=file_rules,
            project_settings=project_settings,
        )
        or ""
    )


def get_scene_linear_colorspace() -> str:
    """Return colorspace name for Katana's OCIO scene linear role.

    By default, renderers in Katana render output images in the scene linear
    role colorspace. Config parsing errors propagate from Core.

    Returns:
        The colorspace name for the ``scene_linear`` role in the active OCIO
        config, or an empty string when OCIO or the role is not configured.

    Raises:
        FileNotFoundError: The configured OCIO file does not exist.
    """
    ocio_config_path = _get_ocio_config_path()
    if not ocio_config_path:
        return ""

    colorspaces = get_ocio_config_colorspaces(ocio_config_path)
    return colorspaces["roles"].get("scene_linear", {}).get("colorspace", "")
