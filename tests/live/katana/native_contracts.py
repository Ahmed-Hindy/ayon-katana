"""BETA/WIP live contracts for APIs supplied by real Katana and Foundry USD."""

from __future__ import annotations

import json
import os
import traceback
from pathlib import Path

from fnpxr import Sdf, Usd
from Katana import NodegraphAPI, RenderingAPI

from ayon_katana.api import dependencies, image, render, usd

RESULT = Path(os.environ["AYON_KATANA_LIVE_RESULT"])
APPLICATION = os.environ["AYON_KATANA_LIVE_APPLICATION"]


def main() -> None:
    """Exercise native API assumptions that must not be represented by mocks."""
    result = {
        "success": False,
        "application": APPLICATION,
        "checks": [],
        "coverage_gaps": [],
        "observations": {},
    }
    try:
        root = NodegraphAPI.GetRootNode()

        image_write = NodegraphAPI.CreateNode("ImageWrite", root)
        image_write.setName("AYON_LiveContract_ImageWrite")
        image.configure_image_write(
            image_write,
            output_path="C:/tmp/ayon_live_contract.####.exr",
            file_format="exr",
            colorspace="",
            single_frame=False,
            frame=1001,
        )
        settings = image.read_image_write_settings(image_write)
        assert settings["file_format"] == "exr"
        assert settings["output_path"].endswith("ayon_live_contract.####.exr")

        image_read = NodegraphAPI.CreateNode("ImageRead", root)
        image_read.setName("AYON_LiveContract_ImageRead")
        file_parameter = image_read.getParameter("file")
        assert file_parameter is not None
        file_parameter.setValue("C:/tmp/source.exr", 0.0)
        assert file_parameter.isExpression() is False
        assert file_parameter.getValue(0.0) == "C:/tmp/source.exr"
        assert image_read.getParent() is root
        assert isinstance(image_read.getOutputPorts(), list)
        assert len(NodegraphAPI.GetNodePosition(image_read)) >= 2
        has_leaf_children_api = hasattr(image_read, "getChildren")
        assert not has_leaf_children_api
        result["observations"]["image_read_has_getChildren"] = has_leaf_children_api

        references = dependencies.collect_workfile_references()
        reference = next(item for item in references if item.node is image_read)
        assert reference.node_name == image_read.getName()
        assert reference.authored_value == "C:/tmp/source.exr"

        stale_node = NodegraphAPI.CreateNode("Group", root)
        stale_node.setName("AYON_LiveContract_Deleted")
        stale_node.delete()
        deleted_name = stale_node.getName()
        assert deleted_name.startswith("__XX_DELETED_")
        result["observations"]["deleted_node_name"] = deleted_name

        usd_export = NodegraphAPI.CreateNode("UsdLayerExport", root)
        usd_export.setName("AYON_LiveContract_UsdLayerExport")
        usd.configure_usd_layer_export(
            usd_export,
            file_format="usda",
            time_samples="Current Frame",
            frame_start=1001,
            frame_end=1001,
            samples_per_frame=1.0,
            export_method="Keep Composition Arcs",
        )
        usd_settings = usd.read_usd_layer_export_settings(usd_export)
        assert usd_settings["file_format"] == "usda"

        usd_source = NodegraphAPI.CreateNode("UsdLayerWrite", root)
        usd_source.setName("AYON_LiveContract_UsdLayerWrite")
        assert usd.is_native_usd_node(usd_source)
        assert usd.get_composed_usd_stage(usd_source) is not None

        renderer_names = RenderingAPI.RenderPlugins.GetRendererPluginNames()
        assert isinstance(renderer_names, (list, tuple))
        result["observations"]["renderers"] = list(renderer_names)
        if not renderer_names:
            result["coverage_gaps"].append(
                "No registered renderer plugins; renderer-dependent tests "
                "are unavailable."
            )

        layer = Sdf.Layer.CreateAnonymous("ayon_live_contract.usda")
        prim = Sdf.CreatePrimInLayer(layer, "/Root")
        asset_spec = Sdf.AttributeSpec(prim, "asset", Sdf.ValueTypeNames.Asset)
        asset_spec.default = Sdf.AssetPath("texture.exr")
        assert asset_spec.path.pathString == "/Root.asset"
        other_path = asset_spec.path.GetPrimPath().AppendProperty("other")
        assert other_path.pathString == "/Root.other"
        assert asset_spec.typeName == Sdf.ValueTypeNames.Asset
        assert asset_spec.layer is layer
        assert asset_spec.default.path == "texture.exr"
        assert asset_spec.default.resolvedPath == ""
        assert list(layer.subLayerPaths) == []
        assert layer.GetAttributeAtPath(asset_spec.path) is not None
        assert layer.ListTimeSamplesForPath(asset_spec.path) == []
        stage = Usd.Stage.Open(layer)
        assert any(
            item.identifier == layer.identifier for item in stage.GetLayerStack()
        )
        sdf_format = layer.GetFileFormat().formatId
        assert sdf_format in {"usda", "usdc"}
        result["observations"]["sdf_format"] = sdf_format

        missing = render.get_scenegraph_location_type
        assert callable(missing)
        result["checks"].extend(
            [
                "Katana node and parameter contracts",
                "deleted-node name behavior",
                "workfile dependency inspection",
                "native UsdLayerExport and native-USD stage access",
                "Foundry Sdf/Usd contracts",
                "renderer registry API",
            ]
        )
        result["success"] = True
    except Exception as exc:
        result["error_type"] = type(exc).__name__
        result["error"] = traceback.format_exc()

    RESULT.parent.mkdir(parents=True, exist_ok=True)
    RESULT.write_text(json.dumps(result, indent=2, sort_keys=True), encoding="utf-8")
    print(json.dumps(result, indent=2, sort_keys=True))
    raise SystemExit(0 if result["success"] else 1)


main()
