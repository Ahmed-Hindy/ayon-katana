"""USD look inspection helpers for Katana publishing."""

from __future__ import annotations

import itertools
from typing import Any

from .usd import get_composed_usd_stage, get_extracted_usd_layer_path

DISALLOWED_LOOK_SCHEMA_TYPES = (
    "UsdGeomBoundable",
    "UsdRenderSettingsBase",
    "UsdRenderVar",
    "UsdGeomCamera",
)
MATERIAL_SCHEMA_TYPES = ("UsdShadeMaterial",)


def is_look_instance(instance_data: dict[str, Any]) -> bool:
    """Return whether instance data represents a USD look."""
    return (
        instance_data.get("productBaseType") == "look"
        or instance_data.get("productType") == "look"
    )


def get_usd_export_source_node(export_node: Any) -> Any:
    """Return the single native USD source connected to ``UsdLayerExport``.

    Args:
        export_node: Katana ``UsdLayerExport`` node.

    Returns:
        Connected native source node.

    Raises:
        ValueError: The export node is missing or does not have one source.
    """
    if export_node is None:
        raise ValueError("Katana USD look export node is missing.")
    input_port = export_node.getInputPort("in")
    connected_ports = (
        list(input_port.getConnectedPorts()) if input_port is not None else []
    )
    if len(connected_ports) != 1:
        raise ValueError(
            "UsdLayerExport requires exactly one native USD source on its 'in' port."
        )
    return connected_ports[0].getNode()


def get_composed_source_stage(instance_data: dict[str, Any]) -> Any:
    """Return the composed source stage for a USD publish instance."""
    from ayon_katana.api import compat

    node_name = instance_data["instance_node"]
    export_node = compat.get_node(node_name)
    if export_node is None:
        raise ValueError(f"Katana USD export node does not exist: {node_name!r}.")
    source_node = get_usd_export_source_node(export_node)
    return get_composed_usd_stage(source_node)


def open_extracted_look_layer(instance_data: dict[str, Any]) -> Any:
    """Open the staged USD look layer."""
    from pxr import Sdf

    layer_path = get_extracted_usd_layer_path(instance_data)
    layer = Sdf.Layer.FindOrOpen(layer_path.as_posix())
    if layer is None:
        raise RuntimeError(f"Failed to open extracted USD look layer: {layer_path}")
    return layer


def get_schema_type_names(type_name: str) -> set[str]:
    """Return a USD schema type name and all concrete derived schema names."""
    from pxr import Tf, Usd

    schema_registry = Usd.SchemaRegistry
    type_ = Tf.Type.FindByName(type_name)
    if type_ == Tf.Type.Unknown:
        type_ = schema_registry.GetTypeFromSchemaTypeName(type_name)
        if type_ == Tf.Type.Unknown:
            return set()

    output = set()
    for derived_type in itertools.chain([type_], type_.GetAllDerivedTypes()):
        schema_name = schema_registry.GetSchemaTypeName(derived_type)
        if schema_name:
            output.add(str(schema_name))
    return output


def has_material_binding(prim: Any) -> bool:
    """Return whether a geometry prim or one of its subsets has a material."""
    from pxr import UsdShade

    search_prims = [prim]
    binding_api = UsdShade.MaterialBindingAPI(prim)
    for subset in binding_api.GetMaterialBindSubsets():
        search_prims.append(subset.GetPrim())

    purposes = (
        UsdShade.Tokens.full,
        UsdShade.Tokens.preview,
        UsdShade.Tokens.allPurpose,
    )
    for purpose in purposes:
        materials, _relationships = UsdShade.MaterialBindingAPI.ComputeBoundMaterials(
            search_prims,
            purpose,
        )
        for material in materials:
            material_prim = material.GetPrim()
            if material_prim and material_prim.IsValid():
                return True
    return False


def collect_unbound_geometry_paths(stage: Any) -> list[str]:
    """Return composed geometry prims without a material binding."""
    from pxr import UsdGeom

    invalid = []
    for prim in stage.Traverse():
        if not prim.IsA(UsdGeom.Gprim):
            continue
        if not has_material_binding(prim):
            invalid.append(str(prim.GetPath()))
    return sorted(set(invalid))


def _get_applied_items(list_proxy: Any) -> list[Any]:
    """Return authored reference/payload list items across USD versions."""
    getter = getattr(list_proxy, "GetAppliedItems", None)
    if callable(getter):
        return list(getter())
    return list(list_proxy.ApplyEditsToList([]))


def collect_disallowed_authored_look_items(layer: Any) -> dict[str, list[str]]:
    """Return authored look prims with disallowed types or composition arcs."""
    disallowed_names = set()
    for schema_type in DISALLOWED_LOOK_SCHEMA_TYPES:
        disallowed_names.update(get_schema_type_names(schema_type))

    invalid: dict[str, list[str]] = {}

    def inspect(path: Any) -> None:
        """Record one disallowed authored prim path and its reasons."""
        if not path.IsPrimPath():
            return
        prim_spec = layer.GetPrimAtPath(path)
        if prim_spec is None:
            return
        path_string = str(path)
        reasons = invalid.setdefault(path_string, [])
        if prim_spec.typeName in disallowed_names:
            reasons.append(f"defines disallowed type {prim_spec.typeName!r}")

        references = _get_applied_items(prim_spec.referenceList)
        if references:
            assets = ", ".join(
                str(item.assetPath or "<internal>") for item in references
            )
            reasons.append(f"authors reference(s): {assets}")

        payloads = _get_applied_items(prim_spec.payloadList)
        if payloads:
            assets = ", ".join(str(item.assetPath or "<internal>") for item in payloads)
            reasons.append(f"authors payload(s): {assets}")

        if not reasons:
            invalid.pop(path_string, None)

    layer.Traverse("/", inspect)
    return dict(sorted(invalid.items()))


def collect_invalid_material_definitions(
    layer: Any,
    stage: Any,
) -> dict[str, str]:
    """Return authored Material prims that are overs/classes instead of defs."""
    from pxr import Sdf, UsdShade

    material_type_names = set()
    for schema_type in MATERIAL_SCHEMA_TYPES:
        material_type_names.update(get_schema_type_names(schema_type))

    specifier_names = {
        Sdf.SpecifierDef: "def",
        Sdf.SpecifierOver: "over",
        Sdf.SpecifierClass: "class",
    }
    invalid: dict[str, str] = {}

    def inspect(path: Any) -> None:
        """Record one authored Material that is not a definition."""
        if not path.IsPrimPath():
            return
        prim_spec = layer.GetPrimAtPath(path)
        if prim_spec is None:
            return

        is_material = prim_spec.typeName in material_type_names
        if not prim_spec.typeName:
            composed_prim = stage.GetPrimAtPath(path)
            is_material = bool(composed_prim and composed_prim.IsA(UsdShade.Material))
        if not is_material or prim_spec.specifier == Sdf.SpecifierDef:
            return

        invalid[str(path)] = specifier_names.get(
            prim_spec.specifier,
            str(prim_spec.specifier),
        )

    layer.Traverse("/", inspect)
    return dict(sorted(invalid.items()))
