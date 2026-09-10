"""Create Katana ImageWrite publish instances."""

from __future__ import annotations

from contextlib import suppress
from pathlib import Path
from typing import Any

from ayon_core.lib import BoolDef, EnumDef, NumberDef, TextDef
from ayon_core.pipeline import CreatorError

from ayon_katana.api import compat, plugin
from ayon_katana.api.image import configure_image_write


class CreateImage(plugin.KatanaCreator):
    """Create an ``ImageWrite`` publish instance."""

    identifier = "io.ayon.creators.katana.image"
    label = "Image"
    product_base_type = "image"
    product_type = product_base_type
    icon = "picture-o"
    description = "Publish a selected image stream locally or on the farm"

    default_render_target = "local"
    default_extension = "exr"
    default_colorspace = ""
    default_frame_padding = 4
    default_review = False

    def _current_frame_range(self) -> tuple[int, int]:
        folder_entity = self.create_context.get_current_folder_entity()
        attributes = (folder_entity or {}).get("attrib") or {}
        frame_start = attributes.get("frameStart")
        if frame_start is None:
            frame_start = 1001
        frame_end = attributes.get("frameEnd")
        if frame_end is None:
            frame_end = frame_start
        return int(frame_start), int(frame_end)

    def _default_output_path(
        self,
        product_name: str,
        extension: str,
        *,
        single_frame: bool,
        frame: int,
    ) -> str:
        current_workfile = self.create_context.host.get_current_workfile()
        base_directory = (
            Path(current_workfile).parent if current_workfile else Path.cwd()
        )
        frame_component = (
            str(frame).zfill(self.default_frame_padding)
            if single_frame
            else "#" * self.default_frame_padding
        )
        return str(
            base_directory
            / "images"
            / product_name
            / f"{product_name}.{frame_component}.{extension}"
        ).replace("\\", "/")

    @staticmethod
    def _selected_output_port():
        selected_nodes = compat.get_selected_nodes()
        if len(selected_nodes) != 1:
            raise CreatorError(
                "Select exactly one Katana image node to create an ImageWrite "
                "publish instance."
            )
        selected_node = selected_nodes[0]
        output_port = selected_node.getOutputPort("out")
        if output_port is None:
            output_ports = compat.get_output_ports(selected_node)
            output_port = output_ports[0] if output_ports else None
        if output_port is None:
            raise CreatorError(
                f"Selected node {selected_node.getName()!r} has no output port."
            )
        return output_port

    def create(
        self,
        product_name: str,
        instance_data: dict[str, Any],
        pre_create_data: dict[str, Any],
    ):
        """Create and connect an ``ImageWrite`` node."""
        use_selection = bool(pre_create_data.get("use_selection", True))
        source_port = self._selected_output_port() if use_selection else None
        frame_start, _frame_end = self._current_frame_range()
        frame = int(pre_create_data.get("frame", frame_start))
        single_frame = bool(pre_create_data.get("single_frame", False))
        extension = (
            (pre_create_data.get("extension") or self.default_extension)
            .lower()
            .lstrip(".")
        )
        output_path = pre_create_data.get("output_path") or self._default_output_path(
            product_name,
            extension,
            single_frame=single_frame,
            frame=frame,
        )
        render_target = pre_create_data.get("render_target", self.default_render_target)
        if render_target not in {"farm", "local", "local_no_render"}:
            raise CreatorError(f"Unsupported image render target: {render_target!r}.")
        review = bool(pre_create_data.get("review", self.default_review))
        colorspace = pre_create_data.get("colorspace") or self.default_colorspace

        creator_attributes = instance_data.setdefault("creator_attributes", {})
        creator_attributes.update(
            {
                "render_target": render_target,
                "review": review,
            }
        )
        instance_data["node_type"] = "ImageWrite"
        instance_data["farm"] = render_target == "farm"
        families = instance_data.setdefault("families", [])
        for family in ("image", "katana.image"):
            if family not in families:
                families.append(family)
        if instance_data["farm"] and "render.farm" not in families:
            families.append("render.farm")
        if not instance_data["farm"] and "render.farm" in families:
            families.remove("render.farm")

        created_instance = None
        image_write_node = None
        try:
            created_instance = super().create(
                product_name,
                instance_data,
                pre_create_data,
            )
            image_write_node = created_instance.transient_data["node"]
            configure_image_write(
                image_write_node,
                output_path=output_path,
                file_format=extension,
                colorspace=colorspace,
                single_frame=single_frame,
                frame=frame,
            )
            if source_port is not None:
                input_port = image_write_node.getInputPort("in")
                if input_port is None:
                    raise RuntimeError("ImageWrite has no 'in' port.")
                source_port.connect(input_port)

            return created_instance
        except Exception:
            if image_write_node is not None:
                with suppress(Exception):
                    image_write_node.delete()
            if created_instance is not None:
                with suppress(Exception):
                    self._remove_instance_from_context(created_instance)
            raise

    def get_pre_create_attr_defs(self):
        """Return pre-create ImageWrite settings."""
        frame_start, _frame_end = self._current_frame_range()
        return [
            BoolDef(
                "use_selection",
                label="Connect selected node",
                default=not self.create_context.headless,
            ),
            EnumDef(
                "render_target",
                label="Render target",
                default=self.default_render_target,
                items={
                    "local": "Local",
                    "farm": "Farm",
                    "local_no_render": "Use existing frames",
                },
            ),
            BoolDef("review", label="Review", default=self.default_review),
            BoolDef("single_frame", label="Single frame", default=False),
            NumberDef(
                "frame",
                label="Single frame",
                default=frame_start,
                decimals=0,
            ),
            TextDef(
                "output_path",
                label="Output path",
                default="",
                placeholder="Leave empty for a workfile-relative image sequence",
            ),
            EnumDef(
                "extension",
                label="Extension",
                default=self.default_extension,
                items=["exr", "png", "tif", "jpg", "dpx", "cin"],
            ),
            TextDef(
                "colorspace",
                label="Output colorspace",
                default=self.default_colorspace,
                placeholder="Required when Review is enabled",
            ),
        ]

    def get_instance_attr_defs(self):
        """Return instance publish settings."""
        return [
            EnumDef(
                "render_target",
                label="Render target",
                default=self.default_render_target,
                items={
                    "local": "Local",
                    "farm": "Farm",
                    "local_no_render": "Use existing frames",
                },
            ),
            BoolDef("review", label="Review", default=self.default_review),
        ]
