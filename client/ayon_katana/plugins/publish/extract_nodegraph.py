"""Export selected Katana Groups as reusable node graph representations."""

from __future__ import annotations

from pathlib import Path

import pyblish.api
from ayon_core.pipeline.publish import PublishError
from Katana import KatanaFile

from ayon_katana.api import compat, plugin


class ExtractNodegraph(plugin.KatanaExtractorPlugin):
    """Extract the validated Katana node graph."""

    label = "Extract Node Graph"
    order = pyblish.api.ExtractorOrder
    families = ["nodegraph"]

    def process(self, instance) -> None:
        """Stage one selected Group without saving the active workfile."""
        source_name = instance.data.get("nodegraph_node")
        source_node = compat.get_node(str(source_name)) if source_name else None
        if source_node is None:
            raise PublishError(
                f"Katana node graph source does not exist: {source_name!r}"
            )

        product_name = instance.data.get("productName") or source_node.getName()
        filename = f"{product_name}.katana"
        staging_dir = Path(self.staging_dir(instance))
        staging_dir.mkdir(parents=True, exist_ok=True)
        destination_path = staging_dir / filename

        try:
            exported_path = KatanaFile.Export(
                destination_path.as_posix(),
                [source_node],
            )
        except Exception as exc:
            raise PublishError(
                f"Katana node graph export failed for {source_node.getName()!r}: {exc}"
            ) from exc

        if exported_path is None or not destination_path.is_file():
            raise PublishError(
                "Katana node graph export did not create "
                f"{destination_path.as_posix()!r}."
            )

        representation = {
            "name": "katana",
            "ext": "katana",
            "files": filename,
            "stagingDir": str(staging_dir),
        }
        instance.data.setdefault("representations", []).append(representation)
        instance.data["setMembers"] = [destination_path.as_posix()]
        self.log.info("Exported Katana node graph: %s", destination_path)
