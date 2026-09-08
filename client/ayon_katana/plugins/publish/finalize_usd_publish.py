"""Finalize staged USD outputs."""

from __future__ import annotations

import os

import pyblish.api
from ayon_core.pipeline.publish import PublishError

from ayon_katana.api import plugin
from ayon_katana.api.usd import get_extracted_usd_layer_path
from ayon_katana.api.usd_look import get_composed_source_stage, is_look_instance
from ayon_katana.api.usd_publish import build_publish_path_map, rewrite_staged_usd_layer
from ayon_katana.api.usd_resources import plan_look_resources


class FinalizeUsdPublish(plugin.KatanaContextPlugin):
    """Finalize staged paths and look resources."""

    label = "Finalize USD"
    order = pyblish.api.ExtractorOrder - 0.495

    def process(self, context) -> None:
        """Finalize active USD instances."""
        try:
            publish_mapping = build_publish_path_map(context)
        except Exception as exc:
            raise PublishError(f"Failed to build USD publish path map: {exc}") from exc

        for instance in context:
            if not instance.data.get("active", True) or not instance.data.get(
                "publish", True
            ):
                continue
            families = set(instance.data.get("families") or [])
            if "katana.usd" not in families:
                continue

            try:
                staged_path = get_extracted_usd_layer_path(instance.data)
                source_stage = get_composed_source_stage(instance.data)
                asset_remap = dict(instance.data.get("assetRemap") or {})

                if is_look_instance(instance.data):
                    from pxr import Sdf

                    layer = Sdf.Layer.FindOrOpen(staged_path.as_posix())
                    if layer is None:
                        raise RuntimeError(
                            f"Failed to open staged USD look layer: {staged_path}"
                        )
                    resources_dir = instance.data.get("resourcesDir")
                    if not resources_dir:
                        raise RuntimeError("USD look instance has no resourcesDir.")
                    plan = plan_look_resources(layer, resources_dir, source_stage)
                    self._merge_resource_plan(instance, plan)
                    asset_remap.update(plan["assetRemap"])

                rewrite_staged_usd_layer(
                    staged_path,
                    publish_mapping=publish_mapping,
                    asset_remap=asset_remap,
                    source_stage=source_stage,
                )
            except Exception as exc:
                product_name = instance.data.get("productName") or instance.name
                raise PublishError(
                    f"Failed to finalize USD product {product_name!r}: {exc}"
                ) from exc

    @staticmethod
    def _merge_resource_plan(instance, plan: dict) -> None:
        resources = instance.data.setdefault("resources", [])
        existing_keys = {
            (
                resource.get("attribute"),
                resource.get("source"),
                tuple(resource.get("files") or []),
                resource.get("color_space"),
            )
            for resource in resources
        }
        for resource in plan["resources"]:
            key = (
                resource.get("attribute"),
                resource.get("source"),
                tuple(resource.get("files") or []),
                resource.get("color_space"),
            )
            if key not in existing_keys:
                resources.append(resource)
                existing_keys.add(key)

        remap = instance.data.setdefault("assetRemap", {})
        for source, destination in plan["assetRemap"].items():
            existing = remap.get(source)
            if existing is not None and existing != destination:
                raise ValueError(
                    f"Conflicting USD asset remap for {source!r}: "
                    f"{existing!r} vs {destination!r}."
                )
            remap[source] = destination

        transfers = instance.data.setdefault("transfers", [])
        destination_sources = {}
        for existing_transfer in transfers:
            if len(existing_transfer) != 2:
                continue
            source, destination = existing_transfer
            destination_sources[FinalizeUsdPublish._transfer_path_key(destination)] = (
                FinalizeUsdPublish._transfer_path_key(source)
            )

        for source, destination in plan["transfers"]:
            source_key = FinalizeUsdPublish._transfer_path_key(source)
            destination_key = FinalizeUsdPublish._transfer_path_key(destination)
            existing_source = destination_sources.get(destination_key)
            if existing_source is not None:
                if existing_source != source_key:
                    raise ValueError(
                        "Conflicting USD resource transfer destination "
                        f"{destination!r}."
                    )
                continue
            transfers.append((source, destination))
            destination_sources[destination_key] = source_key

    @staticmethod
    def _transfer_path_key(path: str) -> str:
        return os.path.normcase(os.path.normpath(str(path)))
