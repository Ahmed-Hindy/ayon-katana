"""Real Katana loader transaction cases for the live integration suite."""

from __future__ import annotations

import copy
import os
from pathlib import Path

import ayon_api
from Katana import KatanaFile, NodegraphAPI

from ayon_katana.api import containers
from ayon_katana.plugins.load.load_alembic import AbcLoader
from ayon_katana.plugins.load.load_image import ImageLoader
from ayon_katana.plugins.load.load_katana import KatanaImportLoader
from ayon_katana.plugins.load.load_usd import UsdLoader, UsdSublayerLoader

OUT = Path(os.environ["AYON_KATANA_LIVE_OUT"]).resolve()
PROJECT_NAME = os.environ["AYON_PROJECT_NAME"]
FOLDER_PATH = os.environ["AYON_FOLDER_PATH"]
TASK_NAME = os.environ["AYON_TASK_NAME"]


def root_names() -> set[str]:
    """Return names of direct root children."""
    return {node.getName() for node in NodegraphAPI.GetRootNode().getChildren()}


def representation_context(
    path: Path,
    representation_id: str,
    *,
    representation_name: str = "katana",
    product_name: str = "LiveKatanaGraph",
    product_type: str = "nodegraph",
    colorspace_name: str = "",
) -> dict:
    """Build a Core-compatible local representation context."""
    project = ayon_api.get_project(PROJECT_NAME)
    folder = ayon_api.get_folder_by_path(PROJECT_NAME, FOLDER_PATH)
    if project is None or folder is None:
        raise RuntimeError(
            "AYON live-test project/folder context could not be resolved."
        )
    task = ayon_api.get_task_by_name(PROJECT_NAME, folder["id"], TASK_NAME)
    representation = {
        "id": representation_id,
        "name": representation_name,
        "attrib": {"template": path.as_posix()},
        "context": {},
        "data": {},
    }
    if colorspace_name:
        representation["data"] = {"colorspaceData": {"colorspace": colorspace_name}}
    return {
        "project": project,
        "folder": folder,
        "task": task,
        "product": {"name": product_name, "productType": product_type},
        "version": {"id": f"version-{representation_id}", "version": 1},
        "representation": representation,
    }


def exercise_loader(
    loader,
    *,
    filepath_parameter: str,
    path_a: Path,
    path_b: Path,
    representation_name: str,
    product_type: str,
    product_name: str,
) -> None:
    """Exercise real load, rollback, update and remove for one native loader."""
    context_a = representation_context(
        path_a,
        f"{product_name}-a",
        representation_name=representation_name,
        product_name=product_name,
        product_type=product_type,
        colorspace_name="sRGB" if isinstance(loader, ImageLoader) else "",
    )
    context_b = representation_context(
        path_b,
        f"{product_name}-b",
        representation_name=representation_name,
        product_name=product_name,
        product_type=product_type,
        colorspace_name="ACEScg" if isinstance(loader, ImageLoader) else "",
    )

    before = root_names()
    invalid_load = copy.deepcopy(context_a)
    invalid_load["representation"].pop("attrib")
    try:
        loader.load(
            invalid_load,
            name=f"{product_name}Invalid",
            namespace="liveKatana",
        )
    except Exception:
        pass
    else:
        raise AssertionError("Invalid representation context unexpectedly loaded.")
    assert root_names() == before

    container_node = loader.load(
        context_a,
        name=product_name,
        namespace="liveKatana",
    )
    container_name = container_node.getName()
    container = containers.parse_container(container_node)
    assert container is not None
    source_node = containers.find_managed_node(container_node, containers.SOURCE_ROLE)
    assert source_node is not None
    parameter = source_node.getParameter(filepath_parameter)
    assert parameter is not None
    old_value = parameter.getValue(0.0)
    old_representation = container["representation"]

    rollback_context = copy.deepcopy(context_b)
    rollback_context["representation"].pop("id")
    try:
        loader.update(container, rollback_context)
    except Exception:
        pass
    else:
        raise AssertionError("Missing representation id unexpectedly updated loader.")
    assert parameter.getValue(0.0) == old_value
    rolled_back = containers.parse_container(container_node)
    assert rolled_back is not None
    assert rolled_back["representation"] == old_representation

    loader.update(container, context_b)
    updated = containers.parse_container(container_node)
    assert updated is not None
    assert updated["representation"] == context_b["representation"]["id"]
    assert parameter.getValue(0.0) != old_value

    loader.remove(updated)
    assert NodegraphAPI.GetNode(container_name) is None


def export_graph(path: Path, name: str, *, with_output: bool) -> None:
    """Export one real Katana Group fixture and remove its source node."""
    source = NodegraphAPI.CreateNode("Group", NodegraphAPI.GetRootNode())
    source.setName(name)
    if with_output:
        source.addOutputPort("out")
    exported = KatanaFile.Export(path.as_posix(), [source])
    assert exported is not False and path.is_file()
    source.delete()


def exercise_katana_import_loader() -> None:
    """Exercise initial and update transactions for Katana graph imports."""
    graph_a = OUT / "loader-graph-a.katana"
    graph_b = OUT / "loader-graph-b.katana"
    graph_invalid = OUT / "loader-graph-invalid.katana"
    export_graph(graph_a, "AYON_Live_LoadGraphA", with_output=True)
    export_graph(graph_b, "AYON_Live_LoadGraphB", with_output=True)
    export_graph(graph_invalid, "AYON_Live_LoadGraphInvalid", with_output=False)

    context_a = representation_context(
        graph_a,
        "katana-load-a",
        product_name="LiveKatanaLoad",
    )
    context_b = representation_context(
        graph_b,
        "katana-load-b",
        product_name="LiveKatanaLoad",
    )
    invalid_context = representation_context(
        graph_invalid,
        "katana-load-invalid",
        product_name="LiveKatanaLoadInvalid",
    )
    loader = KatanaImportLoader()

    before = root_names()
    try:
        loader.load(invalid_context, namespace="liveKatana")
    except RuntimeError as exc:
        assert "no usable terminal output port" in str(exc)
    else:
        raise AssertionError("Outputless Katana graph unexpectedly loaded.")
    assert root_names() == before

    container_node = loader.load(context_a, namespace="liveKatana")
    container = containers.parse_container(container_node)
    assert container is not None
    old_managed = containers.get_managed_group(container_node)
    try:
        loader.update(container, invalid_context)
    except RuntimeError as exc:
        assert "no usable terminal output port" in str(exc)
    else:
        raise AssertionError("Outputless Katana graph unexpectedly replaced container.")
    assert containers.get_managed_group(container_node) is old_managed
    current = containers.parse_container(container_node)
    assert current is not None and current["representation"] == "katana-load-a"

    original_update_container = containers.update_container

    def fail_after_metadata_write(node, data):
        original_update_container(node, data)
        if data.get("representation") == "katana-load-b":
            raise RuntimeError("live injected metadata write failure")

    containers.update_container = fail_after_metadata_write
    try:
        try:
            loader.update(container, context_b)
        except RuntimeError as exc:
            assert "live injected metadata write failure" in str(exc)
        else:
            raise AssertionError("Injected metadata failure unexpectedly succeeded.")
    finally:
        containers.update_container = original_update_container

    assert containers.get_managed_group(container_node) is old_managed
    current = containers.parse_container(container_node)
    assert current is not None and current["representation"] == "katana-load-a"

    loader.update(container, context_b)
    current = containers.parse_container(container_node)
    assert current is not None and current["representation"] == "katana-load-b"
    container_name = container_node.getName()
    loader.remove(current)
    assert NodegraphAPI.GetNode(container_name) is None


def exercise_loaders() -> None:
    """Exercise changed Image/Alembic/USD/Katana loader transactions natively."""
    image_a = OUT / "loader-image-a.exr"
    image_b = OUT / "loader-image-b.exr"
    alembic_a = OUT / "loader-a.abc"
    alembic_b = OUT / "loader-b.abc"
    for path in (image_a, image_b, alembic_a, alembic_b):
        path.write_bytes(b"live loader fixture")

    from pxr import Sdf

    usd_a = OUT / "loader-a.usda"
    usd_b = OUT / "loader-b.usda"
    for path, prim_name in ((usd_a, "A"), (usd_b, "B")):
        layer = Sdf.Layer.CreateNew(path.as_posix())
        Sdf.CreatePrimInLayer(layer, f"/{prim_name}")
        layer.Save()

    exercise_loader(
        ImageLoader(),
        filepath_parameter="file",
        path_a=image_a,
        path_b=image_b,
        representation_name="exr",
        product_type="image",
        product_name="LiveImageLoad",
    )
    exercise_loader(
        AbcLoader(),
        filepath_parameter="abcAsset",
        path_a=alembic_a,
        path_b=alembic_b,
        representation_name="abc",
        product_type="model",
        product_name="LiveAlembicLoad",
    )
    exercise_loader(
        UsdLoader(),
        filepath_parameter="fileName",
        path_a=usd_a,
        path_b=usd_b,
        representation_name="usd",
        product_type="usd",
        product_name="LiveUsdLoad",
    )
    exercise_loader(
        UsdSublayerLoader(),
        filepath_parameter="asset",
        path_a=usd_a,
        path_b=usd_b,
        representation_name="usd",
        product_type="usd",
        product_name="LiveUsdSublayerLoad",
    )
    exercise_katana_import_loader()
