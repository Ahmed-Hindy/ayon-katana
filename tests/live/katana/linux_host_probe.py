"""Minimal real-host probe for Katana inside a Linux container.

This script intentionally depends only on APIs bundled with Katana. It verifies
that the containerized Foundry runtime can acquire a license and exercise native
Katana/USD contracts before AYON-specific Linux acceptance is attempted.
"""

from __future__ import annotations

import json
import platform

from fnpxr import Sdf, Usd
from Katana import NodegraphAPI, RenderingAPI


def main() -> None:
    """Exercise core Katana and Foundry USD APIs and print structured results."""
    result = {
        "success": False,
        "platform": platform.platform(),
        "checks": [],
        "observations": {},
    }

    root = NodegraphAPI.GetRootNode()

    image_read = NodegraphAPI.CreateNode("ImageRead", root)
    image_read.setName("AYON_LinuxProbe_ImageRead")
    file_parameter = image_read.getParameter("file")
    assert file_parameter is not None
    file_parameter.setValue("/tmp/ayon-linux-probe.exr", 0.0)
    assert file_parameter.isExpression() is False
    assert file_parameter.getValue(0.0) == "/tmp/ayon-linux-probe.exr"
    assert image_read.getParent() is root
    assert isinstance(image_read.getOutputPorts(), list)
    result["checks"].append("Katana node and parameter contracts")

    usd_export = NodegraphAPI.CreateNode("UsdLayerExport", root)
    usd_export.setName("AYON_LinuxProbe_UsdLayerExport")
    assert usd_export.getParameter("usdFileFormat") is not None
    assert usd_export.getParameter("saveTo") is not None
    result["checks"].append("native UsdLayerExport node availability")

    layer = Sdf.Layer.CreateAnonymous("ayon_linux_probe.usda")
    Sdf.CreatePrimInLayer(layer, "/Root")
    stage = Usd.Stage.Open(layer)
    assert stage.GetPrimAtPath("/Root")
    result["checks"].append("Foundry Sdf/Usd contracts")

    renderer_names = list(RenderingAPI.RenderPlugins.GetRendererPluginNames())
    result["observations"]["renderers"] = renderer_names
    result["checks"].append("renderer registry API")

    result["success"] = True
    print("AYON_KATANA_LINUX_HOST_PROBE=" + json.dumps(result, sort_keys=True))


main()
