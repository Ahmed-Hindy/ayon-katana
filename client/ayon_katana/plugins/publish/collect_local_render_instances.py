"""Collect integration instances for local Katana outputs."""

import pyblish.api
from ayon_core.pipeline.farm.pyblish_functions import (
    create_instances_for_aov,
    create_skeleton_instance,
)

from ayon_katana.api import plugin


class CollectLocalRenderInstances(plugin.KatanaInstancePlugin):
    """Create integration instances for local outputs."""

    label = "Collect Local Output Instances"
    order = pyblish.api.CollectorOrder + 0.430
    families = ["render", "katana.render", "image", "katana.image"]

    def process(self, instance):
        """Create integration instances from local outputs."""
        if instance.data.get("farm"):
            self.log.debug("Katana output is configured for farm processing.")
            return

        expected_files = instance.data.get("expectedFiles") or []
        if not expected_files or not expected_files[0]:
            raise RuntimeError("Local output has no expected files.")

        skeleton = create_skeleton_instance(
            instance,
            families_transfer=[],
            instance_transfer={},
        )
        for key in ("creator_attributes", "publish_attributes"):
            if key in instance.data:
                skeleton[key] = instance.data[key]

        review = bool((instance.data.get("creator_attributes") or {}).get("review"))
        aov_instances = create_instances_for_aov(
            instance=instance,
            skeleton=skeleton,
            aov_filter={},
            skip_integration_repre_list=[],
            do_not_add_review=True,
        )

        source_families = set(instance.data.get("families") or [])
        is_image = bool({"image", "katana.image"} & source_families)
        context = instance.context
        anatomy = context.data["anatomy"]
        for instance_data in aov_instances:
            is_review = (
                review and instance_data["productName"] == skeleton["productName"]
            )
            for representation in instance_data["representations"]:
                representation["stagingDir"] = anatomy.fill_root(
                    representation["stagingDir"]
                )
                if is_review:
                    tags = representation.setdefault("tags", [])
                    if "review" not in tags:
                        tags.append("review")

            aov_instance = context.create_instance(instance_data["productName"])
            aov_instance.data.update(instance_data)
            families = ["image.local.katana" if is_image else "render.local.katana"]
            if is_review:
                families.append("review")
            aov_instance.data["families"] = families

        instance.data["integrate"] = False
