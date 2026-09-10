"""Validate that Katana render products have unique output paths."""

from __future__ import annotations

import inspect
import os
from collections import defaultdict
from collections.abc import Iterable, Mapping

import pyblish.api
from ayon_core.pipeline import (
    OptionalPyblishPluginMixin,
    PublishValidationError,
)

from ayon_katana.api import compat, plugin, render
from ayon_katana.plugins.publish.actions import (
    SelectInvalidInstanceNodes,
    SelectInvalidOutputNodes,
)


def _is_windows() -> bool:
    """Return whether paths should use Windows case-insensitive semantics."""
    return os.name == "nt"


def _normalize_output_path(filepath: str) -> str:
    """Normalize one concrete expected output path for collision comparison."""
    normalized = os.path.normpath(str(filepath)).replace("\\", "/")
    if _is_windows():
        return normalized.casefold()
    return normalized


def _iter_filepaths(value) -> Iterable[str]:
    """Yield path strings from a generic expected-files value."""
    if isinstance(value, (str, os.PathLike)):
        yield str(value)
        return
    if isinstance(value, Iterable):
        for item in value:
            if isinstance(item, (str, os.PathLike)):
                yield str(item)


def get_instance_expected_files(instance) -> list[str]:
    """Get the expected source render files for the instance."""
    expected_files = instance.data.get("expectedFiles", [])
    filepaths = []
    if expected_files:
        for expected in expected_files:
            if isinstance(expected, Mapping):
                for sequence_files in expected.values():
                    filepaths.extend(_iter_filepaths(sequence_files))
                continue
            filepaths.extend(_iter_filepaths(expected))
    else:
        staging_dir = instance.data.get("stagingDir")
        frames = instance.data.get("frames")
        if frames is None or not staging_dir:
            return []
        if isinstance(frames, str):
            filepaths.append(f"{staging_dir}/{frames}")
        else:
            filepaths.extend(f"{staging_dir}/{frame}" for frame in frames)
    return filepaths


def _expected_files_by_aov(instance) -> dict[str, set[str]]:
    """Map each expected-files AOV key to its concrete normalized paths."""
    paths_by_aov = defaultdict(set)
    for expected in instance.data.get("expectedFiles") or []:
        if not isinstance(expected, Mapping):
            continue
        for aov_identifier, sequence_files in expected.items():
            for filepath in _iter_filepaths(sequence_files):
                paths_by_aov[aov_identifier].add(_normalize_output_path(filepath))
    return paths_by_aov


def _instance_node(instance):
    """Resolve an outer Katana render instance Group from published data."""
    node_name = instance.data.get("instance_node")
    if node_name is None:
        return None
    return compat.get_node(node_name)


def _node_key(node):
    """Return a stable identity for a Katana node inside one validation pass."""
    return None if node is None else node.getName()


class ValidateRenderProductPathsUnique(
    plugin.KatanaContextPlugin,
    OptionalPyblishPluginMixin,
):
    """Validate that render product paths are unique.

    This catches multiple render instances that would write to the same files
    before they overwrite each other at render time.
    """

    label = "Unique Render Product Paths"
    order = pyblish.api.ValidatorOrder
    families = ["render", "katana.render"]
    actions = [SelectInvalidInstanceNodes, SelectInvalidOutputNodes]
    optional = True

    def process(self, context):
        """Reject concrete output paths shared by render instances."""
        if not self.is_active(context.data):
            return

        collisions = self._get_collisions(context)
        if not collisions:
            return

        details = []
        for collision in collisions:
            instance_names = ", ".join(
                self._instance_label(instance) for instance in collision["instances"]
            )
            variants = sorted(collision["variants"], key=str.casefold)
            details.append(
                f"- {collision['path']} ({instance_names})"
                + (f"; variants: {', '.join(variants)}" if len(variants) > 1 else "")
            )
        raise PublishValidationError(
            "Multiple Katana render instances write to the same concrete "
            "output files:\n" + "\n".join(details),
            title=self.label,
            description=self.get_description(),
        )

    @classmethod
    def get_invalid(cls, context) -> list:
        """Return outer Katana instance Groups that own colliding outputs."""
        nodes = []
        for collision in cls._get_collisions(context):
            for instance in collision["instances"]:
                node = _instance_node(instance)
                if node is not None:
                    nodes.append(node)

        unique_nodes = []
        seen = set()
        for node in nodes:
            key = _node_key(node)
            if key in seen:
                continue
            seen.add(key)
            unique_nodes.append(node)
        return unique_nodes

    @classmethod
    def get_invalid_output_nodes(cls, context) -> list:
        """Return colliding output nodes when their expected-files AOV is known."""
        colliding_paths_by_instance = defaultdict(set)
        for collision in cls._get_collisions(context):
            for instance in collision["instances"]:
                colliding_paths_by_instance[id(instance)].add(collision["key"])

        output_nodes = []
        for instance in cls._render_instances(context):
            colliding_paths = colliding_paths_by_instance.get(id(instance))
            if not colliding_paths:
                continue
            instance_node = _instance_node(instance)
            if instance_node is None:
                continue

            colliding_aovs = {
                aov_identifier
                for aov_identifier, paths in _expected_files_by_aov(instance).items()
                if paths & colliding_paths
            }
            if not colliding_aovs:
                continue
            for output_definition in render.get_output_definitions(instance_node):
                if output_definition.aov_identifier not in colliding_aovs:
                    continue
                output_node = compat.get_node(output_definition.node_name)
                if output_node is not None:
                    output_nodes.append(output_node)

        unique_nodes = []
        seen = set()
        for node in output_nodes:
            key = _node_key(node)
            if key in seen:
                continue
            seen.add(key)
            unique_nodes.append(node)
        return unique_nodes

    @classmethod
    def _get_collisions(cls, context) -> list[dict]:
        """Return all concrete output paths owned by more than one instance."""
        instances_by_path = defaultdict(list)
        variants_by_path = defaultdict(set)
        for instance in cls._render_instances(context):
            if instance.data.get("integrate", True) is False:
                continue

            paths_for_instance = set()
            for filepath in get_instance_expected_files(instance):
                normalized_path = _normalize_output_path(filepath)
                if not normalized_path:
                    continue
                paths_for_instance.add(normalized_path)
                variants_by_path[normalized_path].add(str(filepath))
            for normalized_path in paths_for_instance:
                instances_by_path[normalized_path].append(instance)

        collisions = []
        for normalized_path, instances in instances_by_path.items():
            if len(instances) < 2:
                continue
            variants = variants_by_path[normalized_path]
            collisions.append(
                {
                    "key": normalized_path,
                    "path": sorted(variants, key=str.casefold)[0],
                    "variants": variants,
                    "instances": sorted(instances, key=cls._instance_label),
                }
            )
        return sorted(collisions, key=lambda collision: collision["key"])

    @classmethod
    def _render_instances(cls, context) -> list:
        """Return only instances matching this context validator's families."""
        return list(pyblish.api.instances_by_plugin(list(context), cls))

    def get_description(self):
        """Return the Publisher help text for output path collisions."""
        return inspect.cleandoc(
            """
            ### Render product paths are not unique

            Multiple render instances would write to the same output files.
            Ensure every enabled Katana render output resolves to a unique
            concrete path before submitting the render.
            """
        )

    @staticmethod
    def _instance_label(instance) -> str:
        """Return a deterministic human-readable name for one publish instance."""
        for key in ("productName", "name", "instance_node"):
            value = instance.data.get(key)
            if value:
                return str(value)
        return str(instance.id)
