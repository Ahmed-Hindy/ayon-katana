"""Create Katana render publish instances."""

from __future__ import annotations

from contextlib import suppress
from pathlib import Path
from typing import Any, Optional

from ayon_core.lib import BoolDef, EnumDef, NumberDef, TextDef
from ayon_core.pipeline import CreatorError

from ayon_katana.api import compat, instances, plugin, render

_TASK_HANDLES_PUBLISH_PLUGIN = "CollectAssetHandles"


class CreateRender(plugin.KatanaCreator):
    """Create a Katana render graph and AYON publish instance."""

    identifier = "io.ayon.creators.katana.render"
    label = "Render"
    product_base_type = "render"
    product_type = product_base_type
    icon = "fa5.images"
    description = "Create a Katana render node graph"

    default_variant = "Main"
    default_renderer = ""
    default_render_target = "farm"
    default_extension = "exr"
    default_channel = "rgba"
    default_camera = "/root/world/cam/camera"
    default_frame_padding = 4

    def create_instance_node(
        self,
        node_type: str,
        node_name: str,
        parent=None,
    ):
        """Create a render instance Group with pass-through ports."""
        instance_node = super().create_instance_node(
            node_type,
            node_name,
            parent=parent,
        )
        instance_node.addInputPort("in")
        instance_node.addOutputPort("out")
        return instance_node

    def _current_frame_range(self) -> tuple[int, int]:
        try:
            folder_entity = self.create_context.get_current_folder_entity()
        except Exception:
            folder_entity = None
        attributes = (folder_entity or {}).get("attrib") or {}
        frame_start = attributes.get("frameStart")
        if frame_start is None:
            frame_start = 1001
        frame_end = attributes.get("frameEnd")
        if frame_end is None:
            frame_end = frame_start
        return int(frame_start), int(frame_end)

    def _current_task_handles(self) -> tuple[int, int]:
        """Return active task handles, falling back to folder attributes.

        The creator's frame inputs are cut frames. The Render range expands
        them when handles are enabled.
        """
        try:
            task_entity = self.create_context.get_current_task_entity()
        except Exception:
            task_entity = None
        try:
            folder_entity = self.create_context.get_current_folder_entity()
        except Exception:
            folder_entity = None
        task_attributes = (task_entity or {}).get("attrib") or {}
        folder_attributes = (folder_entity or {}).get("attrib") or {}

        def get_handle(name: str) -> int:
            """Return one task or folder handle."""
            value = task_attributes.get(name)
            if value is None:
                value = folder_attributes.get(name)
            if value is None:
                return 0
            try:
                return int(value)
            except (TypeError, ValueError) as exc:
                raise CreatorError(
                    f"AYON {name} handle is not a whole number: {value!r}"
                ) from exc

        return get_handle("handleStart"), get_handle("handleEnd")

    def _default_output_path(self, product_name: str, extension: str) -> str:
        current_workfile = self.create_context.host.get_current_workfile()
        base_directory = (
            Path(current_workfile).parent if current_workfile else Path.cwd()
        )
        padding = "#" * self.default_frame_padding
        return str(
            base_directory
            / "renders"
            / product_name
            / f"{product_name}.{padding}.{extension}"
        ).replace("\\", "/")

    def _get_required_renderer(self, configured_renderer: Optional[str]) -> str:
        renderer_name = configured_renderer or render.get_default_renderer(
            self.default_renderer
        )
        if not renderer_name:
            raise CreatorError(
                "The renderer is not configured. Set the CreateRender default "
                "renderer or DEFAULT_RENDERER to a registered renderer."
            )
        return renderer_name

    def create(
        self,
        product_name: str,
        instance_data: dict[str, Any],
        pre_create_data: dict[str, Any],
    ):
        """Create a render graph and publish instance."""
        frame_start_default, frame_end_default = self._current_frame_range()
        frame_start = int(pre_create_data.get("frame_start", frame_start_default))
        frame_end = int(pre_create_data.get("frame_end", frame_end_default))
        frame_step = int(pre_create_data.get("frame_step", 1))
        extension = pre_create_data.get("extension") or self.default_extension
        output_path = pre_create_data.get("output_path") or self._default_output_path(
            product_name, extension
        )
        renderer_name = self._get_required_renderer(pre_create_data.get("renderer"))
        creator_attributes = instance_data.setdefault("creator_attributes", {})
        use_handles = bool(pre_create_data.get("use_handles", True))
        render_target = pre_create_data.get(
            "render_target",
            self.default_render_target,
        )
        if render_target not in {"farm", "local", "local_no_render"}:
            raise CreatorError(f"Unsupported Katana render target: {render_target!r}.")
        creator_attributes.update(
            {
                "render_target": render_target,
                "review": bool(pre_create_data.get("review", True)),
            }
        )
        handle_publish_attributes = instance_data.setdefault(
            "publish_attributes", {}
        ).setdefault(_TASK_HANDLES_PUBLISH_PLUGIN, {})
        handle_publish_attributes["use_handles"] = use_handles
        families = instance_data.setdefault("families", [])
        for family in ("render", "katana.render"):
            if family not in families:
                families.append(family)
        if render_target == "farm" and "render.farm" not in families:
            families.append("render.farm")
        if render_target != "farm" and "render.farm" in families:
            families.remove("render.farm")
        instance_data["node_type"] = "Group"
        instance_data["farm"] = render_target == "farm"

        handle_start, handle_end = (
            self._current_task_handles() if use_handles else (0, 0)
        )
        render_start = frame_start - handle_start
        render_end = frame_end + handle_end
        created_instance = None
        instance_node = None
        try:
            created_instance = super().create(
                product_name,
                instance_data,
                pre_create_data,
            )
            instance_node = created_instance.transient_data["node"]
            render_node = render.create_render_graph(
                instance_node=instance_node,
                product_name=product_name,
                output_name=pre_create_data.get("output_name") or "primary",
                output_path=output_path,
                extension=extension,
                channel=pre_create_data.get("channel") or self.default_channel,
                renderer=renderer_name,
                camera=pre_create_data.get("camera") or self.default_camera,
                frame_start=render_start,
                frame_end=render_end,
                frame_step=frame_step,
                resolution=pre_create_data.get("resolution") or "",
            )
            created_instance["instance_node"] = instance_node.getName()
            created_instance["render_node"] = render_node.getName()
            settings_node = render.get_settings_node(instance_node)
            if settings_node is None:
                raise RuntimeError("Katana render graph has no RenderSettings node.")
            created_instance["render_settings_node"] = settings_node.getName()
            instances.imprint(instance_node, created_instance.data_to_store())

            if pre_create_data.get("use_selection", True):
                selected_nodes = compat.get_selected_nodes()
                if selected_nodes:
                    source_port = selected_nodes[0].getOutputPort("out")
                    target_port = instance_node.getInputPort("in")
                    if source_port is not None and target_port is not None:
                        source_port.connect(target_port)
            return created_instance
        except Exception as exc:
            if instance_node is not None:
                with suppress(Exception):
                    instance_node.delete()
            if created_instance is not None:
                with suppress(Exception):
                    self._remove_instance_from_context(created_instance)
            if isinstance(exc, CreatorError):
                raise
            raise CreatorError(f"Katana render creator failed: {exc}") from exc

    def update_instances(self, update_list) -> None:
        """Update persisted render instance identity after creator edits."""
        native_creator_keys = {
            "output_path",
            "output_name",
            "extension",
            "channel",
            "renderer",
            "camera",
            "frame_start",
            "frame_end",
            "frame_step",
            "resolution",
        }
        for created_instance, _changes in update_list:
            creator_attributes = created_instance.get("creator_attributes") or {}
            for key in native_creator_keys:
                creator_attributes.pop(key, None)
        super().update_instances(update_list)

        for created_instance, changes in update_list:
            if "productName" not in changes.changed_keys:
                continue
            instance_node = created_instance.transient_data.get("node")
            if instance_node is None:
                continue
            try:
                created_instance["instance_node"] = instance_node.getName()
            except Exception:
                continue
            try:
                render_node = render.get_render_node(instance_node)
            except Exception:
                render_node = None
            try:
                settings_node = render.get_settings_node(instance_node)
            except Exception:
                settings_node = None
            if render_node is not None:
                created_instance["render_node"] = render_node.getName()
            if settings_node is not None:
                created_instance["render_settings_node"] = settings_node.getName()
            instances.imprint(instance_node, created_instance.data_to_store())

    def _get_initial_render_attr_defs(self):
        frame_start, frame_end = self._current_frame_range()
        return [
            TextDef(
                "output_path",
                label="Output path",
                default="",
                placeholder="Leave empty for a workfile-relative EXR sequence",
            ),
            TextDef("output_name", label="Output name", default="primary"),
            EnumDef(
                "extension",
                label="Extension",
                default=self.default_extension,
                items=["exr", "png", "tif", "jpg"],
            ),
            TextDef("channel", label="Channel / AOV", default=self.default_channel),
            self._get_renderer_attr_def(),
            TextDef("camera", label="Camera path", default=self.default_camera),
            TextDef(
                "resolution",
                label="Resolution preset",
                default="",
                placeholder="Leave empty to use Katana project resolution",
            ),
            NumberDef(
                "frame_start",
                label="Frame start",
                default=frame_start,
                decimals=0,
            ),
            NumberDef(
                "frame_end",
                label="Frame end",
                default=frame_end,
                decimals=0,
            ),
            NumberDef(
                "frame_step",
                label="Frame step",
                default=1,
                minimum=1,
                decimals=0,
            ),
        ]

    def _get_renderer_attr_def(self):
        renderer_names = render.get_registered_renderers()
        default_renderer = render.get_default_renderer(self.default_renderer)
        if renderer_names:
            return EnumDef(
                "renderer",
                label="Renderer",
                default=default_renderer,
                items={name: name for name in renderer_names},
            )
        return TextDef(
            "renderer",
            label="Renderer",
            default=default_renderer,
            placeholder="No renderer plugins are registered",
        )

    def get_pre_create_attr_defs(self):
        """Return render controls shown before instance creation."""
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
                    "farm": "Farm",
                    "local": "Local",
                    "local_no_render": "Use existing frames",
                },
            ),
            BoolDef("review", label="Review", default=True),
            BoolDef("use_handles", label="Use task handles", default=True),
            *self._get_initial_render_attr_defs(),
        ]

    def get_instance_attr_defs(self):
        """Return render controls editable after instance creation."""
        return [
            EnumDef(
                "render_target",
                label="Render target",
                default=self.default_render_target,
                items={
                    "farm": "Farm",
                    "local": "Local",
                    "local_no_render": "Use existing frames",
                },
            ),
            BoolDef("review", label="Review", default=True),
        ]
