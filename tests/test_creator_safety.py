"""Regression tests for transactional Katana creator cleanup."""

from __future__ import annotations

import importlib.util
import sys
import types
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).parents[1]


class FakeNode:
    """Minimal Katana node that can be deleted from its parent."""

    def __init__(self, parent=None) -> None:
        self.parent = parent
        self.name = ""
        self.deleted = False
        if parent is not None:
            parent.children.append(self)
        self.children = []

    def setName(self, name: str) -> None:
        """Set the fake node name."""
        self.name = name

    def getName(self) -> str:
        """Return the current native node name."""
        return self.name

    def delete(self) -> None:
        """Delete this node from its parent."""
        if self.parent is not None:
            self.parent.children.remove(self)
        self.deleted = True


class FakeNodegraphAPI:
    """Minimal NodegraphAPI used by the Katana creator base."""

    def __init__(self) -> None:
        self.root = FakeNode()

    def GetRootNode(self):
        """Return the fake project root."""
        return self.root

    def CreateNode(self, _node_type: str, parent):
        """Create one child node."""
        return FakeNode(parent)


class FakeCreatedInstance(dict):
    """Small Core CreatedInstance substitute."""

    def __init__(
        self,
        product_base_type: str,
        product_type: str,
        product_name: str,
        data: dict,
        creator,
    ) -> None:
        super().__init__(data)
        self.product_base_type = product_base_type
        self.product_type = product_type
        self.product_name = product_name
        self.creator = creator
        self.transient_data = {}

    def data_to_store(self) -> dict:
        """Return serializable creator data."""
        return dict(self)

    @classmethod
    def from_existing(cls, data, creator):
        """Reconstruct a creator instance from persisted metadata."""
        return cls(
            creator.product_base_type,
            data["productType"],
            data["productName"],
            data,
            creator,
        )


class FakeCreator:
    """Minimal Core Creator context registration behavior."""

    def _add_instance_to_context(self, instance) -> None:
        """Register a created instance."""
        self.context_instances.append(instance)

    def _remove_instance_from_context(self, instance) -> None:
        """Unregister a created instance."""
        self.context_instances.remove(instance)

    def apply_staging_dir(self, _instance) -> None:
        """No-op staging setup for the isolated test."""


def _load_plugin_module(monkeypatch: pytest.MonkeyPatch):
    """Load the creator base with only its direct runtime dependencies."""
    graph = FakeNodegraphAPI()
    katana_module = types.ModuleType("Katana")
    katana_module.NodegraphAPI = graph
    monkeypatch.setitem(sys.modules, "Katana", katana_module)

    pyblish_api = types.ModuleType("pyblish.api")
    pyblish_api.InstancePlugin = object
    pyblish_api.ContextPlugin = object
    pyblish_module = types.ModuleType("pyblish")
    pyblish_module.api = pyblish_api
    monkeypatch.setitem(sys.modules, "pyblish", pyblish_module)
    monkeypatch.setitem(sys.modules, "pyblish.api", pyblish_api)

    ayon_core = types.ModuleType("ayon_core")
    pipeline = types.ModuleType("ayon_core.pipeline")
    pipeline.CreatedInstance = FakeCreatedInstance
    pipeline.Creator = FakeCreator
    pipeline.CreatorError = RuntimeError
    pipeline.load = types.SimpleNamespace(LoaderPlugin=object)
    pipeline.publish = types.SimpleNamespace(Extractor=object)
    ayon_core.pipeline = pipeline
    monkeypatch.setitem(sys.modules, "ayon_core", ayon_core)
    monkeypatch.setitem(sys.modules, "ayon_core.pipeline", pipeline)

    package_module = types.ModuleType("ayon_katana")
    package_module.__path__ = []
    api_module = types.ModuleType("ayon_katana.api")
    api_module.__path__ = []
    instances_module = types.ModuleType("ayon_katana.api.instances")
    instances_module.iter_instances = lambda: []
    instances_module.imprint = lambda *_args: (_ for _ in ()).throw(
        RuntimeError("imprint failed")
    )
    monkeypatch.setitem(sys.modules, "ayon_katana", package_module)
    monkeypatch.setitem(sys.modules, "ayon_katana.api", api_module)
    monkeypatch.setitem(sys.modules, "ayon_katana.api.instances", instances_module)

    module_path = PROJECT_ROOT / "client" / "ayon_katana" / "api" / "plugin.py"
    module_spec = importlib.util.spec_from_file_location(
        "ayon_katana.api.plugin",
        module_path,
    )
    assert module_spec is not None
    assert module_spec.loader is not None
    module = importlib.util.module_from_spec(module_spec)
    monkeypatch.setitem(sys.modules, "ayon_katana.api.plugin", module)
    module_spec.loader.exec_module(module)
    return module, graph


def test_base_creator_unregisters_instance_when_imprinting_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A metadata failure cannot leave a ghost CreatedInstance in Publisher."""
    module, graph = _load_plugin_module(monkeypatch)
    creator = object.__new__(module.KatanaCreator)
    creator.product_base_type = "test"
    creator.node_type = "Group"
    creator.context_instances = []

    with pytest.raises(RuntimeError, match="Creator error"):
        creator.create("testMain", {"productType": "test"}, {})

    assert creator.context_instances == []
    assert graph.root.children == []


def test_base_creator_persists_native_name_before_first_imprint(monkeypatch) -> None:
    """Katana's resolved name is persisted even when it differs from the request."""
    module, graph = _load_plugin_module(monkeypatch)
    creator = object.__new__(module.KatanaCreator)
    creator.product_base_type = "image"
    creator.context_instances = []
    imprinted = []
    monkeypatch.setattr(
        module.instances, "imprint", lambda node, data: imprinted.append(dict(data))
    )
    monkeypatch.setattr(
        FakeNode, "setName", lambda node, name: setattr(node, "name", "comp1")
    )

    created = creator.create("imageMain", {}, {})

    assert created["instance_node"] == graph.root.children[0].getName() == "comp1"
    assert imprinted == [created.data_to_store()]


@pytest.mark.parametrize("product_type", ["render", "image", "usd", "nodegraph"])
def test_recollection_refreshes_renamed_node_without_overwriting_source(
    monkeypatch, product_type
) -> None:
    """Stored names cannot point publishing at an old-name replacement node."""
    module, graph = _load_plugin_module(monkeypatch)
    creator = object.__new__(module.KatanaCreator)
    creator.product_base_type = product_type
    creator.identifier = "test.creator"
    creator.context_instances = []
    creator.collection_shared_data = {}
    node = graph.CreateNode("Group", graph.root)
    node.setName("Renamed")
    replacement = graph.CreateNode("Group", graph.root)
    replacement.setName("Original")
    stored = {
        "creator_identifier": creator.identifier,
        "productType": product_type,
        "productName": "testMain",
        "instance_node": "Original",
        "nodegraph_node": "ArtistSource",
        "render_node": "NestedRender",
    }
    monkeypatch.setattr(module.instances, "iter_instances", lambda: [(node, stored)])

    creator.collect_instances()

    collected = creator.context_instances[0]
    assert collected["instance_node"] == "Renamed"
    assert collected.transient_data["node"] is node
    assert collected["nodegraph_node"] == "ArtistSource"
    assert collected["render_node"] == "NestedRender"
    assert stored["instance_node"] == "Original"


@pytest.mark.parametrize("rename_product", [False, True])
def test_update_persists_current_native_name(monkeypatch, rename_product) -> None:
    """An update stores the live name after either artist or product-name edits."""
    module, graph = _load_plugin_module(monkeypatch)
    creator = object.__new__(module.KatanaCreator)
    creator.product_base_type = "test"
    creator.context_instances = []
    imprinted = []
    monkeypatch.setattr(
        module.instances, "imprint", lambda node, data: imprinted.append(dict(data))
    )
    created = creator.create("testMain", {}, {})
    node = created.transient_data["node"]
    node.setName("ArtistRename")

    class Changes(dict):
        changed_keys = {"productName"} if rename_product else set()

    changes = Changes(productName=types.SimpleNamespace(new_value="ProductRename"))
    creator.update_instances([(created, changes)])

    expected = "ProductRename" if rename_product else "ArtistRename"
    assert imprinted[-1]["instance_node"] == node.getName() == expected


@pytest.mark.parametrize("fail_imprint", [False, True])
def test_nodegraph_creation_uses_one_transaction_and_retains_source(
    monkeypatch, fail_imprint
) -> None:
    """The real base owns the only imprint and rolls back only its new node."""
    module, graph = _load_plugin_module(monkeypatch)
    source = graph.CreateNode("Group", graph.root)
    source.setName("ArtistSource")
    api = sys.modules["ayon_katana.api"]
    api.plugin = module
    api.compat = types.SimpleNamespace()
    api.containers = types.SimpleNamespace()
    path = PROJECT_ROOT / "client/ayon_katana/plugins/create/create_nodegraph.py"
    spec = importlib.util.spec_from_file_location("nodegraph_transaction_test", path)
    nodegraph = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(nodegraph)
    creator = object.__new__(nodegraph.CreateNodegraph)
    creator.context_instances = []
    creator._selected_group = lambda: source
    imprinted = []

    def imprint(node, data):
        imprinted.append((node, dict(data)))
        if fail_imprint:
            raise RuntimeError("imprint failed")

    monkeypatch.setattr(module.instances, "imprint", imprint)
    if fail_imprint:
        with pytest.raises(RuntimeError, match="imprint failed"):
            creator.create("nodegraphMain", {}, {})
        assert creator.context_instances == []
        assert graph.root.children == [source]
    else:
        created = creator.create("nodegraphMain", {}, {})
        assert creator.context_instances == [created]
    assert len(imprinted) == 1
    assert imprinted[0][1]["instance_node"] == "nodegraphMain"
    assert imprinted[0][1]["nodegraph_node"] == "ArtistSource"
    assert source.deleted is False
