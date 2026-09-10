"""Load AYON image products through Katana ImageRead."""

from __future__ import annotations

import re
from contextlib import suppress
from pathlib import Path

from Katana import NodegraphAPI

from ayon_katana.api import colorspace as colorspace_api
from ayon_katana.api import containers, plugin

_PRINTF_TOKEN = re.compile(r"%0?(\d+)d")
_DOLLAR_F_TOKEN = re.compile(r"\$F(\d*)")
_FRAME_NUMBER = re.compile(r"^(.*?)(\d+)(\.[^.]+)$")


def normalize_image_sequence_path(filepath: str, representation: dict) -> str:
    """Normalize an AYON sequence path to Katana's hash-token syntax.

    Args:
        filepath: Resolved representation file path.
        representation: AYON representation entity.

    Returns:
        Forward-slash path with a hash token for sequence representations.
    """
    path = filepath.replace("\\", "/")
    frame = (representation.get("context") or {}).get("frame")
    if frame is None:
        return path

    printf_match = _PRINTF_TOKEN.search(path)
    if printf_match:
        return _PRINTF_TOKEN.sub("#" * int(printf_match.group(1)), path, count=1)
    dollar_f_match = _DOLLAR_F_TOKEN.search(path)
    if dollar_f_match:
        padding = int(dollar_f_match.group(1) or 1)
        return _DOLLAR_F_TOKEN.sub("#" * padding, path, count=1)

    filename = Path(path).name
    frame_match = _FRAME_NUMBER.match(filename)
    if frame_match is None:
        return path
    try:
        if int(frame_match.group(2)) != int(frame):
            return path
    except (TypeError, ValueError):
        return path
    tokenized_name = (
        frame_match.group(1) + ("#" * len(frame_match.group(2))) + frame_match.group(3)
    )
    return path[: -len(filename)] + tokenized_name


def _representation_colorspace(representation: dict) -> str:
    colorspace_data = (representation.get("data") or {}).get("colorspaceData") or {}
    return colorspace_data.get("colorspace") or ""


def _image_colorspace(filepath: str, context: dict) -> str:
    published = _representation_colorspace(context["representation"])
    if published:
        return published
    return colorspace_api.get_imageio_file_rule_colorspace(filepath, context)


class ImageLoader(plugin.KatanaLoader):
    """Load still images and sequences into a managed ImageRead node."""

    product_base_types = {
        "image",
        "imagesequence",
        "online",
        "plate",
        "render",
        "review",
    }
    product_types = product_base_types
    label = "Load Image"
    representations = {"*"}
    extensions = {
        "bmp",
        "cin",
        "dpx",
        "exr",
        "gif",
        "hdr",
        "jpeg",
        "jpg",
        "png",
        "psd",
        "sgi",
        "tga",
        "tif",
        "tiff",
        "tx",
    }
    order = -9

    icon = "picture-o"
    color = "orange"

    @classmethod
    def _path_from_context(cls, context: dict) -> str:
        filepath = cls.filepath_from_context(context)
        return normalize_image_sequence_path(filepath, context["representation"])

    def load(self, context, name=None, namespace=None, options=None):
        """Load an image representation and return its container node."""
        product_name = name or context["product"]["name"]
        namespace = namespace or context["folder"]["name"]
        container_node = None
        try:
            container_node = containers.containerise(
                name=product_name,
                namespace=namespace,
                context=context,
                loader=self.__class__.__name__,
            )
            managed_group = containers.get_managed_group(container_node)
            if managed_group is None:
                raise RuntimeError("Failed to create the AYON managed group.")

            source_node = NodegraphAPI.CreateNode("ImageRead", managed_group)
            source_node.setName(f"{namespace}_{product_name}_ImageRead")
            filepath = self._path_from_context(context)
            source_node.getParameter("file").setValue(filepath, 0.0)
            colorspace = _image_colorspace(filepath, context)
            if colorspace:
                source_node.getParameter("image.colorspace").setValue(
                    colorspace,
                    0.0,
                )
            containers.set_managed_node_role(source_node, containers.SOURCE_ROLE)
            source_node.getOutputPort("out").connect(managed_group.getReturnPort("out"))
            self[:] = [container_node, source_node]
            return container_node
        except Exception:
            if container_node is not None:
                with suppress(Exception):
                    container_node.delete()
            raise

    def update(self, container, context):
        """Update the managed path, colorspace, and container transactionally."""
        container_node = container["node"]
        source_node = containers.find_managed_node(
            container_node,
            containers.SOURCE_ROLE,
        )
        if source_node is None:
            raise RuntimeError(
                "The AYON container is missing its managed ImageRead node."
            )

        file_parameter = source_node.getParameter("file")
        colorspace_parameter = source_node.getParameter("image.colorspace")
        old_filepath = file_parameter.getValue(0.0)
        old_colorspace = colorspace_parameter.getValue(0.0)
        old_container_data = containers.parse_container(container_node)
        if old_container_data is None:
            raise RuntimeError("The AYON image container has invalid metadata.")
        old_container_data.pop("node", None)
        old_container_data.pop("objectName", None)

        filepath = self._path_from_context(context)
        colorspace = _image_colorspace(filepath, context)
        project = context.get("project") or {}
        try:
            file_parameter.setValue(filepath, 0.0)
            colorspace_parameter.setValue(colorspace, 0.0)
            containers.update_container(
                container_node,
                {
                    "representation": context["representation"]["id"],
                    "project_name": project.get("name"),
                    "loader": self.__class__.__name__,
                },
            )
        except Exception:
            with suppress(Exception):
                file_parameter.setValue(old_filepath, 0.0)
            with suppress(Exception):
                colorspace_parameter.setValue(old_colorspace, 0.0)
            with suppress(Exception):
                containers.update_container(container_node, old_container_data)
            raise

    def remove(self, container):
        """Remove the complete AYON image container."""
        container["node"].delete()

    def switch(self, container, context):
        """Switch the container through the transactional update path."""
        self.update(container, context)
