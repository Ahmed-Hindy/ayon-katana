"""Node-backed AYON publish instance persistence for Katana."""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any, Optional

from ayon_core.pipeline import AYON_INSTANCE_ID

from . import compat, lib

_INSTANCE_PARAMETER = "user.ayon.instance.data"


def imprint(node, data: dict[str, Any]) -> None:
    """Store AYON creator instance data on a Katana node.

    Args:
        node: Katana node representing a publish instance.
        data: Serialized ``CreatedInstance`` data.
    """
    instance_data = dict(data)
    instance_data.setdefault("id", AYON_INSTANCE_ID)
    lib.write_json_parameter(node, _INSTANCE_PARAMETER, instance_data)


def read(node) -> Optional[dict[str, Any]]:
    """Read AYON creator instance data from a Katana node.

    Args:
        node: Katana node to inspect.

    Returns:
        Parsed instance data, or ``None`` when the node is not an instance.
    """
    data = lib.read_json_parameter(node, _INSTANCE_PARAMETER)
    if not isinstance(data, dict) or data.get("id") != AYON_INSTANCE_ID:
        return None
    return data


def iter_nodes(parent_node=None) -> Iterator:
    """Yield every Katana node recursively below a parent.

    Args:
        parent_node: Parent node. Defaults to Katana's root node.

    Yields:
        Katana nodes in depth-first order.
    """
    yield from compat.iter_nodes(parent_node)


def iter_instances() -> Iterator[tuple[Any, dict[str, Any]]]:
    """Yield Katana nodes carrying AYON creator instance data."""
    for node in iter_nodes():
        data = read(node)
        if data is not None:
            yield node, data
