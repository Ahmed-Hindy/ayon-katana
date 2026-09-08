"""Focused tests for portable Katana USD look validation."""

from __future__ import annotations

import ast
import importlib.util
import sys
import types
from pathlib import Path

import pytest

ROOT = Path(__file__).parents[1]


class FakePath(str):
    """Minimal Sdf.Path-compatible prim path."""

    def IsPrimPath(self) -> bool:
        return True


class FakeSchemaType:
    """Small Tf.Type stand-in with derived schema types."""

    def __init__(self, name: str, derived=()) -> None:
        self.name = name
        self.derived = list(derived)

    def GetAllDerivedTypes(self):
        return list(self.derived)


class FakePrim:
    """Composed USD prim with schema membership and material bindings."""

    def __init__(
        self,
        path: str,
        *,
        schemas=(),
        bound_purposes=(),
        subsets=(),
        valid: bool = True,
    ) -> None:
        self.path = FakePath(path)
        self.schemas = set(schemas)
        self.bound_purposes = set(bound_purposes)
        self.subsets = list(subsets)
        self.valid = valid

    def IsA(self, schema) -> bool:
        return schema in self.schemas

    def GetPath(self):
        return self.path

    def IsValid(self) -> bool:
        return self.valid


class FakeSubset:
    """Material-binding subset wrapper."""

    def __init__(self, prim: FakePrim) -> None:
        self.prim = prim

    def GetPrim(self):
        return self.prim


class FakeMaterial:
    """Bound material object exposing a valid prim."""

    def __init__(self, valid: bool) -> None:
        self.prim = FakePrim("/Looks/Material", valid=valid)

    def GetPrim(self):
        return self.prim


class FakeStage:
    """Composed stage used by assignment and material-definition tests."""

    def __init__(self, prims) -> None:
        self.prims = list(prims)
        self.by_path = {str(prim.GetPath()): prim for prim in self.prims}

    def Traverse(self):
        return list(self.prims)

    def GetPrimAtPath(self, path):
        return self.by_path.get(str(path))


class FakeListProxy:
    """Reference/payload list editor exposing applied items."""

    def __init__(self, items=()) -> None:
        self.items = list(items)

    def GetAppliedItems(self):
        return list(self.items)


class FakeArc:
    """Reference or payload item."""

    def __init__(self, asset_path: str) -> None:
        self.assetPath = asset_path


class FakePrimSpec:
    """Authored Sdf prim specification."""

    def __init__(
        self,
        type_name: str = "",
        specifier="def",
        *,
        references=(),
        payloads=(),
    ) -> None:
        self.typeName = type_name
        self.specifier = specifier
        self.referenceList = FakeListProxy(references)
        self.payloadList = FakeListProxy(payloads)


class FakeLayer:
    """Authored USD layer with deterministic traversal."""

    def __init__(self, specs: dict[str, FakePrimSpec]) -> None:
        self.specs = dict(specs)

    def Traverse(self, _root, callback) -> None:
        for path in sorted(self.specs):
            callback(FakePath(path))

    def GetPrimAtPath(self, path):
        return self.specs.get(str(path))


class FakeOptionalMixin:
    """Optional plug-in activation behavior for isolated tests."""

    def is_active(self, data: dict) -> bool:
        return bool(data.get("active", True))


class FakeInstancePlugin:
    """Minimal Katana publish base."""


class FakeValidationError(RuntimeError):
    """Publish validation error accepting AYON's title keyword."""

    def __init__(self, message: str, *, title: str | None = None) -> None:
        super().__init__(message)
        self.title = title


def _install_pxr(monkeypatch):
    """Install a compact pxr API with schema inheritance and material binding."""
    usd_geom = types.ModuleType("pxr.UsdGeom")
    usd_shade = types.ModuleType("pxr.UsdShade")
    sdf = types.ModuleType("pxr.Sdf")
    tf = types.ModuleType("pxr.Tf")
    usd = types.ModuleType("pxr.Usd")

    usd_geom.Gprim = object()
    usd_shade.Material = object()
    usd_shade.Tokens = types.SimpleNamespace(
        full="full",
        preview="preview",
        allPurpose="",
    )

    class MaterialBindingAPI:
        def __init__(self, prim) -> None:
            self.prim = prim

        def GetMaterialBindSubsets(self):
            return [FakeSubset(prim) for prim in self.prim.subsets]

        @staticmethod
        def ComputeBoundMaterials(prims, purpose):
            materials = [FakeMaterial(purpose in prim.bound_purposes) for prim in prims]
            return materials, [object() for _prim in prims]

    usd_shade.MaterialBindingAPI = MaterialBindingAPI

    sdf.SpecifierDef = "def"
    sdf.SpecifierOver = "over"
    sdf.SpecifierClass = "class"
    sdf.Layer = types.SimpleNamespace(FindOrOpen=lambda _path: None)

    concrete = {
        "UsdGeomBoundable": ["Mesh", "BasisCurves", "SphereLight"],
        "UsdRenderSettingsBase": ["RenderSettings"],
        "UsdRenderVar": ["RenderVar"],
        "UsdGeomCamera": ["Camera"],
        "UsdShadeMaterial": ["Material"],
    }
    type_map = {}
    for root_name, derived_names in concrete.items():
        derived = [FakeSchemaType(name) for name in derived_names]
        type_map[root_name] = FakeSchemaType(root_name, derived)

    unknown = FakeSchemaType("Unknown")
    type_api = types.SimpleNamespace(
        Unknown=unknown,
        FindByName=lambda name: type_map.get(name, unknown),
    )
    tf.Type = type_api
    usd.SchemaRegistry = types.SimpleNamespace(
        GetTypeFromSchemaTypeName=lambda name: type_map.get(name, unknown),
        GetSchemaTypeName=lambda type_: type_.name,
    )

    pxr = types.ModuleType("pxr")
    pxr.Sdf = sdf
    pxr.Tf = tf
    pxr.Usd = usd
    pxr.UsdGeom = usd_geom
    pxr.UsdShade = usd_shade
    monkeypatch.setitem(sys.modules, "pxr", pxr)
    monkeypatch.setitem(sys.modules, "pxr.Sdf", sdf)
    monkeypatch.setitem(sys.modules, "pxr.Tf", tf)
    monkeypatch.setitem(sys.modules, "pxr.Usd", usd)
    monkeypatch.setitem(sys.modules, "pxr.UsdGeom", usd_geom)
    monkeypatch.setitem(sys.modules, "pxr.UsdShade", usd_shade)
    return types.SimpleNamespace(
        Sdf=sdf,
        UsdGeom=usd_geom,
        UsdShade=usd_shade,
    )


def _load_usd_look(monkeypatch):
    """Load look helpers with a compact Katana API package."""
    package = types.ModuleType("ayon_katana")
    package.__path__ = []
    api = types.ModuleType("ayon_katana.api")
    api.__path__ = []
    usd = types.ModuleType("ayon_katana.api.usd")
    usd.get_composed_usd_stage = lambda node: node.stage
    usd.get_extracted_usd_layer_path = lambda data: Path(data["layer_path"])
    monkeypatch.setitem(sys.modules, "ayon_katana", package)
    monkeypatch.setitem(sys.modules, "ayon_katana.api", api)
    monkeypatch.setitem(sys.modules, "ayon_katana.api.usd", usd)

    path = ROOT / "client" / "ayon_katana" / "api" / "usd_look.py"
    spec = importlib.util.spec_from_file_location("ayon_katana.api.usd_look", path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    monkeypatch.setitem(sys.modules, "ayon_katana.api.usd_look", module)
    spec.loader.exec_module(module)
    api.usd_look = module
    return module


def _load_validator(monkeypatch, filename: str, look_module):
    """Load one look validator with focused Pyblish/Core stubs."""
    pyblish_api = types.ModuleType("pyblish.api")
    pyblish_api.ExtractorOrder = 2.0
    pyblish = types.ModuleType("pyblish")
    pyblish.api = pyblish_api
    monkeypatch.setitem(sys.modules, "pyblish", pyblish)
    monkeypatch.setitem(sys.modules, "pyblish.api", pyblish_api)

    core = types.ModuleType("ayon_core")
    pipeline = types.ModuleType("ayon_core.pipeline")
    publish = types.ModuleType("ayon_core.pipeline.publish")
    pipeline.OptionalPyblishPluginMixin = FakeOptionalMixin
    publish.PublishValidationError = FakeValidationError
    core.pipeline = pipeline
    monkeypatch.setitem(sys.modules, "ayon_core", core)
    monkeypatch.setitem(sys.modules, "ayon_core.pipeline", pipeline)
    monkeypatch.setitem(sys.modules, "ayon_core.pipeline.publish", publish)

    api = sys.modules["ayon_katana.api"]
    api.plugin = types.SimpleNamespace(KatanaInstancePlugin=FakeInstancePlugin)
    api.usd_look = look_module
    monkeypatch.setitem(
        sys.modules,
        "ayon_katana.api.plugin",
        api.plugin,
    )

    path = ROOT / "client" / "ayon_katana" / "plugins" / "publish" / filename
    module_name = f"ayon_katana.plugins.publish.{path.stem}"
    spec = importlib.util.spec_from_file_location(module_name, path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    monkeypatch.setitem(sys.modules, module_name, module)
    spec.loader.exec_module(module)
    return module


def test_assignment_validation_accepts_direct_and_subset_bindings(monkeypatch) -> None:
    """Full/preview/all-purpose bindings on prims or subsets satisfy look coverage."""
    pxr = _install_pxr(monkeypatch)
    look = _load_usd_look(monkeypatch)
    direct = FakePrim(
        "/Asset/Direct",
        schemas={pxr.UsdGeom.Gprim},
        bound_purposes={"full"},
    )
    subset = FakePrim("/Asset/Subset", bound_purposes={"preview"})
    parent = FakePrim(
        "/Asset/Parent",
        schemas={pxr.UsdGeom.Gprim},
        subsets=[subset],
    )

    assert look.collect_unbound_geometry_paths(FakeStage([direct, parent])) == []


def test_assignment_validation_reports_unbound_geometry(monkeypatch) -> None:
    """Unbound geometry is reported by composed prim path."""
    pxr = _install_pxr(monkeypatch)
    look = _load_usd_look(monkeypatch)
    unbound = FakePrim("/Asset/Body", schemas={pxr.UsdGeom.Gprim})

    assert look.collect_unbound_geometry_paths(FakeStage([unbound])) == ["/Asset/Body"]


def test_disallowed_authored_types_references_and_payloads(monkeypatch) -> None:
    """Derived geometry/render/camera types and composition arcs are rejected."""
    _install_pxr(monkeypatch)
    look = _load_usd_look(monkeypatch)
    layer = FakeLayer(
        {
            "/Asset/Geo": FakePrimSpec("Mesh"),
            "/Asset/Cam": FakePrimSpec("Camera"),
            "/Asset/Render": FakePrimSpec("RenderSettings"),
            "/Asset/Ref": FakePrimSpec(references=[FakeArc("model.usd")]),
            "/Asset/Payload": FakePrimSpec(payloads=[FakeArc("payload.usd")]),
            "/Looks/Material": FakePrimSpec("Material"),
        }
    )

    invalid = look.collect_disallowed_authored_look_items(layer)

    assert set(invalid) == {
        "/Asset/Cam",
        "/Asset/Geo",
        "/Asset/Payload",
        "/Asset/Ref",
        "/Asset/Render",
    }
    assert "model.usd" in invalid["/Asset/Ref"][0]
    assert "payload.usd" in invalid["/Asset/Payload"][0]


def test_upstream_geometry_is_not_classified_as_authored_look_geometry(
    monkeypatch,
) -> None:
    """Geometry visible only in the composed source stage does not fail layer checks."""
    _install_pxr(monkeypatch)
    look = _load_usd_look(monkeypatch)
    layer = FakeLayer({"/Looks/Material": FakePrimSpec("Material")})

    assert look.collect_disallowed_authored_look_items(layer) == {}


def test_material_definitions_reject_typed_and_typeless_overs(monkeypatch) -> None:
    """Material overs are detected from authored type or composed-stage type."""
    pxr = _install_pxr(monkeypatch)
    look = _load_usd_look(monkeypatch)
    typed_over = FakePrim("/Looks/Typed", schemas={pxr.UsdShade.Material})
    typeless_over = FakePrim("/Looks/Typeless", schemas={pxr.UsdShade.Material})
    stage = FakeStage([typed_over, typeless_over])
    layer = FakeLayer(
        {
            "/Looks/Good": FakePrimSpec("Material", pxr.Sdf.SpecifierDef),
            "/Looks/Typed": FakePrimSpec("Material", pxr.Sdf.SpecifierOver),
            "/Looks/Typeless": FakePrimSpec("", pxr.Sdf.SpecifierClass),
        }
    )

    assert look.collect_invalid_material_definitions(layer, stage) == {
        "/Looks/Typed": "over",
        "/Looks/Typeless": "class",
    }


def test_optional_validators_skip_when_disabled_and_generic_usd_is_unrestricted(
    monkeypatch,
) -> None:
    """Optional checks can be disabled and non-look USD bypasses all look semantics."""
    _install_pxr(monkeypatch)
    look = _load_usd_look(monkeypatch)
    assignments = _load_validator(
        monkeypatch,
        "validate_usd_look_assignments.py",
        look,
    )
    materials = _load_validator(
        monkeypatch,
        "validate_usd_look_material_definitions.py",
        look,
    )
    disallowed = _load_validator(
        monkeypatch,
        "validate_usd_look_disallowed_types.py",
        look,
    )

    assignments.get_composed_source_stage = lambda _data: (_ for _ in ()).throw(
        AssertionError("disabled validator inspected stage")
    )
    materials.get_composed_source_stage = assignments.get_composed_source_stage
    instance = types.SimpleNamespace(
        data={"productType": "look", "active": False},
    )
    assignments.ValidateUsdLookAssignments().process(instance)
    materials.ValidateUsdLookMaterialDefinitions().process(instance)

    generic = types.SimpleNamespace(data={"productType": "camera"})
    assignments.ValidateUsdLookAssignments().process(generic)
    materials.ValidateUsdLookMaterialDefinitions().process(generic)
    disallowed.ValidateUsdLookDisallowedTypes().process(generic)

    assert assignments.ValidateUsdLookAssignments.order == pytest.approx(1.502)
    assert materials.ValidateUsdLookMaterialDefinitions.optional is True
    assert disallowed.ValidateUsdLookDisallowedTypes.optional is False


def test_server_settings_register_look_validators() -> None:
    """Look checks use the intended optional validation contract."""
    source = (ROOT / "server" / "settings" / "main.py").read_text(encoding="utf-8")
    tree = ast.parse(source)
    assignment = next(
        node
        for node in tree.body
        if isinstance(node, ast.Assign)
        and any(
            isinstance(target, ast.Name) and target.id == "DEFAULT_VALUES"
            for target in node.targets
        )
    )
    defaults = ast.literal_eval(assignment.value)["publish"]

    assert defaults["ValidateUsdLookAssignments"] == {
        "enabled": True,
        "optional": True,
        "active": True,
    }
    assert defaults["ValidateUsdLookDisallowedTypes"] == {"enabled": True}
    assert defaults["ValidateUsdLookMaterialDefinitions"] == {
        "enabled": True,
        "optional": True,
        "active": True,
    }
