"""Katana specific AYON/Pyblish plugin definitions."""

import os
from collections import defaultdict
from contextlib import suppress

import pyblish.api
from ayon_core.pipeline import (
    CreatedInstance,
    Creator,
    CreatorError,
    load,
    publish,
)
from Katana import NodegraphAPI

from . import instances

SETTINGS_CATEGORY = "katana"


class KatanaCreatorBase:
    """Share node-backed instance behavior across Katana creators."""

    @staticmethod
    def cache_instance_data(shared_data):
        """Cache instances for Creators to shared data.

        Create ``katana_cached_instances`` when needed in shared data and fill
        it with all collected node-backed instances under their respective
        creator identifiers.

        Args:
            shared_data: Shared collection data.

        Returns:
            Shared collection data.
        """
        if shared_data.get("katana_cached_instances") is None:
            cache = defaultdict(list)
            for node, instance_data in instances.iter_instances():
                creator_identifier = instance_data.get("creator_identifier")
                if creator_identifier:
                    cache[creator_identifier].append((node, instance_data))
            shared_data["katana_cached_instances"] = cache

        return shared_data

    @staticmethod
    def create_instance_node(node_type, node_name, parent=None):
        """Create node representing instance.

        Args:
            node_type: Type of the node.
            node_name: Name of the new node.
            parent: Optional parent node. Defaults to the root node.

        Returns:
            Newly created Katana instance node.
        """
        parent = parent or NodegraphAPI.GetRootNode()
        instance_node = NodegraphAPI.CreateNode(node_type, parent)
        instance_node.setName(node_name)
        return instance_node


class KatanaCreator(Creator, KatanaCreatorBase):
    """Base class for most of the Katana creator plugins."""

    settings_category = SETTINGS_CATEGORY
    node_type = "Group"

    def check_existing_product(self, product_name):
        """Validate that the product name is unique in the scene.

        Args:
            product_name: Product name to validate.

        Raises:
            CreatorError: A node-backed instance already uses the name.
        """
        for _node, instance_data in instances.iter_instances():
            if instance_data.get("productName") == product_name:
                raise CreatorError(
                    f"A Katana publish instance for {product_name!r} already exists."
                )

    def create(self, product_name, instance_data, pre_create_data):
        """Create and persist a node-backed publish instance."""
        self.check_existing_product(product_name)

        product_type = instance_data.get("productType") or self.product_base_type
        node_type = instance_data.pop("node_type", None)
        parent_node = instance_data.pop("parent_node", None)
        instance_node = None
        created_instance = None
        try:
            instance_node = self.create_instance_node(
                node_type or self.node_type,
                product_name,
                parent=parent_node,
            )
            created_instance = CreatedInstance(
                product_base_type=self.product_base_type,
                product_type=product_type,
                product_name=product_name,
                data=instance_data,
                creator=self,
            )
            self.apply_staging_dir(created_instance)
            created_instance.transient_data["node"] = instance_node
            self._add_instance_to_context(created_instance)
            instances.imprint(instance_node, created_instance.data_to_store())
            return created_instance
        except Exception as exc:
            if created_instance is not None:
                with suppress(Exception):
                    self._remove_instance_from_context(created_instance)
            if instance_node is not None:
                with suppress(Exception):
                    instance_node.delete()
            raise CreatorError(f"Creator error: {exc}") from exc

    def collect_instances(self):
        """Collect persisted node-backed instances into the create context."""
        self.cache_instance_data(self.collection_shared_data)
        cached_instances = self.collection_shared_data["katana_cached_instances"]
        for node, data in cached_instances.get(self.identifier, []):
            instance_data = self.prepare_collected_instance_data(data)
            created_instance = CreatedInstance.from_existing(instance_data, self)
            self.apply_staging_dir(created_instance)
            created_instance.transient_data["node"] = node
            self._add_instance_to_context(created_instance)

    def prepare_collected_instance_data(self, instance_data):
        """Prepare persisted data before wrapping it in ``CreatedInstance``.

        Args:
            instance_data: Raw data read from the Katana node.

        Returns:
            Data used for the collected AYON instance.
        """
        return instance_data

    def update_instances(self, update_list):
        """Apply creator-instance changes to their Katana nodes."""
        for created_inst, changes in update_list:
            instance_node = created_inst.transient_data.get("node")
            if instance_node is None:
                self._remove_instance_from_context(created_inst)
                continue

            try:
                instance_node.getName()
            except Exception:
                self._remove_instance_from_context(created_inst)
                continue

            if "productName" in changes.changed_keys:
                instance_node.setName(changes["productName"].new_value)
            instances.imprint(instance_node, created_inst.data_to_store())

    def remove_instances(self, instances):
        """Delete Katana nodes owned by removed creator instances."""
        for created_inst in instances:
            instance_node = created_inst.transient_data.get("node")
            if instance_node is not None:
                try:
                    instance_node.delete()
                except Exception:
                    self.log.warning(
                        "Failed to delete Katana instance node.",
                        exc_info=True,
                    )
            self._remove_instance_from_context(created_inst)


class KatanaLoader(load.LoaderPlugin):
    """Base class for Katana load plugins."""

    hosts = ["katana"]
    settings_category = SETTINGS_CATEGORY
    use_ayon_entity_uri = False

    @classmethod
    def filepath_from_context(cls, context):
        """Resolve a representation to a path or optional AYON entity URI."""
        if cls.use_ayon_entity_uri:
            from .usd import get_ayon_entity_uri_from_representation_context

            return get_ayon_entity_uri_from_representation_context(context)
        path = super().filepath_from_context(context)
        return os.path.normpath(path).replace("\\", "/")


class KatanaInstancePlugin(pyblish.api.InstancePlugin):
    """Base class for Katana instance publish plugins."""

    hosts = ["katana"]
    settings_category = SETTINGS_CATEGORY


class KatanaContextPlugin(pyblish.api.ContextPlugin):
    """Base class for Katana context publish plugins."""

    hosts = ["katana"]
    settings_category = SETTINGS_CATEGORY


class KatanaExtractorPlugin(publish.Extractor):
    """Base class for Katana extract plugins.

    Note:
        ``KatanaExtractorPlugin`` is a subclass of ``publish.Extractor``,
        which in turn is a subclass of ``pyblish.api.InstancePlugin``.
        If a context extractor is needed, it should incorporate the staging
        functionality provided by ``publish.Extractor``.
    """

    hosts = ["katana"]
    settings_category = SETTINGS_CATEGORY
