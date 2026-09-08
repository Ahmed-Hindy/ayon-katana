"""AYON container metadata and managed graph structure for Katana."""

from __future__ import annotations

from contextlib import suppress
from typing import Any, Optional

from ayon_core.pipeline import AYON_CONTAINER_ID
from Katana import NodegraphAPI

from . import lib

_CONTAINER_PARAMETER = "user.ayon.container.data"
_CONTAINER_SCHEMA = "ayon:container-3.0"
_NODE_ROLE_PARAMETER = "user.ayon.managed.role"
_MANAGED_ROLE = "managed"
_USER_ROLE = "user"

MANAGED_GROUP_NAME = "AYON_MANAGED"
USER_GROUP_NAME = "USER"
SOURCE_ROLE = "source"


def imprint(node, data: dict[str, Any]) -> None:
    """Write AYON container metadata onto a Katana node.

    Args:
        node: Katana container node.
        data: Container metadata to store.
    """
    container_data = dict(data)
    container_data.setdefault("schema", _CONTAINER_SCHEMA)
    container_data.setdefault("id", AYON_CONTAINER_ID)
    lib.write_json_parameter(node, _CONTAINER_PARAMETER, container_data)


def parse_container(node) -> Optional[dict[str, Any]]:
    """Parse AYON container metadata from a Katana node.

    Args:
        node: Katana node to inspect.

    Returns:
        Parsed container data including transient node information, or ``None``.
    """
    data = lib.read_json_parameter(node, _CONTAINER_PARAMETER)
    if data is None or data.get("id") != AYON_CONTAINER_ID:
        return None

    data.setdefault("schema", _CONTAINER_SCHEMA)
    data["objectName"] = node.getName()
    data["node"] = node
    return data


def _set_node_role(node, role: str) -> None:
    """Mark a node with its role in the managed container graph."""
    lib.set_string_parameter(node, _NODE_ROLE_PARAMETER, role)


def find_node_by_role(parent_node, role: str):
    """Find a direct child by its AYON managed-graph role."""
    for child in parent_node.getChildren():
        if lib.get_string_parameter(child, _NODE_ROLE_PARAMETER) == role:
            return child
    return None


def create_managed_group(
    container_node,
    name: str = MANAGED_GROUP_NAME,
    role: Optional[str] = _MANAGED_ROLE,
):
    """Create a loader-owned Group below an AYON container.

    Args:
        container_node: Outer AYON container Group node.
        name: Name for the managed Group.
        role: Optional AYON managed-graph role. Use ``None`` for a temporary
            update candidate until it has replaced the current managed group.

    Returns:
        Created managed Group node.
    """
    managed_group = NodegraphAPI.CreateNode("Group", container_node)
    managed_group.setName(name)
    managed_group.addOutputPort("out")
    if role is not None:
        _set_node_role(managed_group, role)
    return managed_group


def set_managed_group_role(managed_group) -> None:
    """Mark a container child as the active loader-owned Group."""
    _set_node_role(managed_group, _MANAGED_ROLE)


def set_user_group_role(user_group) -> None:
    """Mark a container child as the artist-editable Group."""
    _set_node_role(user_group, _USER_ROLE)


def disconnect_managed_group_from_user(managed_group, user_group) -> None:
    """Disconnect a managed Group from the artist-editable Group.

    Args:
        managed_group: Loader-owned Group currently feeding the user Group.
        user_group: Artist-editable Group within the same container.

    Raises:
        RuntimeError: Required graph ports are missing.
    """
    managed_output = managed_group.getOutputPort("out")
    user_input = user_group.getInputPort("in")
    if managed_output is None or user_input is None:
        raise RuntimeError("The AYON container has incomplete managed/user ports.")
    user_input.disconnect(managed_output)


def connect_managed_group_to_user(managed_group, user_group) -> None:
    """Connect a managed Group's output to the artist-editable Group.

    Args:
        managed_group: Loader-owned Group to connect.
        user_group: Artist-editable Group within the same container.

    Raises:
        RuntimeError: Required graph ports are missing.
    """
    managed_output = managed_group.getOutputPort("out")
    user_input = user_group.getInputPort("in")
    if managed_output is None or user_input is None:
        raise RuntimeError("The AYON container has incomplete managed/user ports.")
    managed_output.connect(user_input)


def containerise(
    name: str,
    namespace: str,
    context: dict[str, Any],
    loader=None,
    parent_node=None,
):
    """Bundle a Katana graph into an AYON container.

    Containerisation enables tracking of version, author and origin for loaded
    products. The container output flows through an artist-editable ``USER``
    group while loader updates remain inside ``AYON_MANAGED``.

    Args:
        name: Name of the loaded product.
        namespace: Namespace under which to host the container.
        context: Loaded product context information.
        loader: Name of the loader used to produce the container.
        parent_node: Optional Katana parent node. Defaults to the root node.

    Returns:
        Created Katana container Group.
    """
    parent_node = parent_node or NodegraphAPI.GetRootNode()
    container_node = None
    try:
        container_node = NodegraphAPI.CreateNode("Group", parent_node)
        container_node.setName(
            lib.sanitize_node_name(f"{namespace}_{name}_CON", "AYON_Container")
        )
        container_node.addOutputPort("out")

        managed_group = create_managed_group(container_node)

        user_group = NodegraphAPI.CreateNode("Group", container_node)
        user_group.setName(USER_GROUP_NAME)
        user_group.addInputPort("in")
        user_group.addOutputPort("out")
        set_user_group_role(user_group)

        user_group.getSendPort("in").connect(user_group.getReturnPort("out"))
        connect_managed_group_to_user(managed_group, user_group)
        user_group.getOutputPort("out").connect(container_node.getReturnPort("out"))

        representation = context["representation"]
        project = context.get("project") or {}
        imprint(
            container_node,
            {
                "schema": _CONTAINER_SCHEMA,
                "id": AYON_CONTAINER_ID,
                "name": name,
                "namespace": namespace,
                "loader": loader,
                "representation": representation["id"],
                "project_name": project.get("name"),
            },
        )
        return container_node
    except Exception:
        if container_node is not None:
            with suppress(Exception):
                container_node.delete()
        raise


def get_managed_group(container_node):
    """Return the loader-owned Group in a container."""
    return find_node_by_role(container_node, _MANAGED_ROLE)


def get_user_group(container_node):
    """Return the artist-owned Group in a container."""
    return find_node_by_role(container_node, _USER_ROLE)


def set_managed_node_role(node, role: str) -> None:
    """Assign a loader-specific role to a managed child node."""
    _set_node_role(node, role)


def find_managed_node(container_node, role: str):
    """Find a role-tagged node inside the managed group."""
    managed_group = get_managed_group(container_node)
    if managed_group is None:
        return None
    return find_node_by_role(managed_group, role)


def update_container(container_node, data: dict[str, Any]) -> None:
    """Update persistent metadata on an existing container."""
    current_data = parse_container(container_node) or {}
    current_data.pop("node", None)
    current_data.pop("objectName", None)
    current_data.update(data)
    imprint(container_node, current_data)


def ls():
    """Yield AYON containers in the current project."""
    for node in NodegraphAPI.GetAllNodesByType("Group"):
        container = parse_container(node)
        if container is not None:
            yield container
