"""Create native Katana USD layer publish instances."""

from __future__ import annotations

from contextlib import suppress
from typing import Any

from ayon_core.lib import BoolDef, EnumDef, NumberDef
from ayon_core.pipeline import CreatorError

from ayon_katana.api import compat, instances, plugin
from ayon_katana.api.usd import configure_usd_layer_export, is_native_usd_node


class CreateUsdLayer(plugin.KatanaCreator):
    """Create a native ``UsdLayerExport`` publish instance."""

    identifier = "io.ayon.creators.katana.usd_layer"
    label = "USD Layer"
    product_base_type = "usd"
    product_type = product_base_type
    icon = "cubes"
    description = "Publish selected native USD graph output as one USD layer"

    default_usd_format = "usd"
    default_time_samples = "Current Frame"
    default_export_method = "Keep Composition Arcs"
    default_samples_per_frame = 1.0

    def _current_frame_range(self) -> tuple[int, int]:
        """Return cut-frame defaults from the current folder context."""
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

    @staticmethod
    def _selected_output_port():
        """Return the output port of exactly one selected Katana node.

        Returns:
            Selected native output port.

        Raises:
            CreatorError: Selection is missing, ambiguous, or has no output.
        """
        selected_nodes = compat.get_selected_nodes()
        if len(selected_nodes) != 1:
            raise CreatorError(
                "Select exactly one native USD node to create a USD layer "
                "publish instance."
            )
        selected_node = selected_nodes[0]
        if not is_native_usd_node(selected_node):
            raise CreatorError(
                f"Selected node {selected_node.getName()!r} is not a native USD "
                f"node (type: {selected_node.getType()!r}). Select a node with "
                "Katana's 'nativeusd' flavor."
            )
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
        """Create, configure, and optionally connect ``UsdLayerExport``."""
        use_selection = bool(pre_create_data.get("use_selection", True))
        source_port = self._selected_output_port() if use_selection else None
        frame_start_default, frame_end_default = self._current_frame_range()
        frame_start = float(pre_create_data.get("frame_start", frame_start_default))
        frame_end = float(pre_create_data.get("frame_end", frame_end_default))
        file_format = pre_create_data.get("usd_format") or self.default_usd_format
        time_samples = pre_create_data.get("time_samples") or self.default_time_samples
        samples_per_frame = float(
            pre_create_data.get(
                "samples_per_frame",
                self.default_samples_per_frame,
            )
        )
        export_method = (
            pre_create_data.get("export_method") or self.default_export_method
        )

        instance_data["node_type"] = "UsdLayerExport"
        families = instance_data.setdefault("families", [])
        for family in ("usd", "katana.usd"):
            if family not in families:
                families.append(family)

        created_instance = None
        export_node = None
        try:
            created_instance = super().create(
                product_name,
                instance_data,
                pre_create_data,
            )
            export_node = created_instance.transient_data["node"]
            configure_usd_layer_export(
                export_node,
                file_format=file_format,
                time_samples=time_samples,
                frame_start=frame_start,
                frame_end=frame_end,
                samples_per_frame=samples_per_frame,
                export_method=export_method,
            )
            if source_port is not None:
                input_port = export_node.getInputPort("in")
                if input_port is None:
                    raise RuntimeError(
                        "UsdLayerExport does not expose its native 'in' port."
                    )
                source_port.connect(input_port)

            created_instance["instance_node"] = export_node.getName()
            instances.imprint(export_node, created_instance.data_to_store())
            return created_instance
        except Exception as exc:
            if export_node is not None:
                with suppress(Exception):
                    export_node.delete()
            if created_instance is not None:
                with suppress(Exception):
                    self._remove_instance_from_context(created_instance)
            if isinstance(exc, CreatorError):
                raise
            raise CreatorError(f"Katana USD layer creator failed: {exc}") from exc

    def get_pre_create_attr_defs(self):
        """Return native USD export settings used during creation."""
        frame_start, frame_end = self._current_frame_range()
        return [
            BoolDef(
                "use_selection",
                label="Connect selected node",
                default=not self.create_context.headless,
            ),
            EnumDef(
                "usd_format",
                label="USD format",
                default=self.default_usd_format,
                items={
                    "usd": "USD",
                    "usda": "USD ASCII",
                    "usdc": "USD Crate",
                },
            ),
            EnumDef(
                "time_samples",
                label="Time samples",
                default=self.default_time_samples,
                items={
                    "Current Frame": "Current Frame",
                    "Frame Range": "Frame Range",
                    "Project Settings": "Project Settings",
                    "Defined Layer Metadata": "Defined Layer Metadata",
                },
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
                "samples_per_frame",
                label="Samples per frame",
                default=self.default_samples_per_frame,
                minimum=0.001,
                decimals=3,
            ),
            EnumDef(
                "export_method",
                label="Export method",
                default=self.default_export_method,
                items={
                    "Keep Composition Arcs": "Keep Composition Arcs",
                    "Flatten Sublayers, Keep References": (
                        "Flatten Sublayers, Keep References"
                    ),
                    "Flatten All": "Flatten All",
                },
            ),
        ]


class CreateUsdLook(CreateUsdLayer):
    """Publish a Katana-authored USD material and assignment layer."""

    identifier = "io.ayon.creators.katana.usd_look"
    label = "USD Look"
    product_base_type = "look"
    product_type = product_base_type
    icon = "paint-brush"
    description = "Publish native USD materials and assignments as an AYON look"


class CreateUsdCamera(CreateUsdLayer):
    """Publish Katana-authored USD camera data."""

    identifier = "io.ayon.creators.katana.usd_camera"
    label = "USD Camera"
    product_base_type = "camera"
    product_type = product_base_type
    icon = "camera"
    description = "Publish native USD camera definitions and animation"
    default_time_samples = "Frame Range"


class CreateUsdLayout(CreateUsdLayer):
    """Publish a Katana-authored USD shot layout layer."""

    identifier = "io.ayon.creators.katana.usd_layout"
    label = "USD Layout"
    product_base_type = "layout"
    product_type = product_base_type
    icon = "object-group"
    description = "Publish native USD shot composition and placement as layout"


class CreateUsdAssembly(CreateUsdLayer):
    """Publish a Katana-authored USD asset assembly layer."""

    identifier = "io.ayon.creators.katana.usd_assembly"
    label = "USD Assembly"
    product_base_type = "assembly"
    product_type = product_base_type
    icon = "cubes"
    description = "Publish referenced USD assets as an AYON assembly"
