"""Focused contracts for Katana workfile reference validation and repair."""

from __future__ import annotations

import ast
import importlib.util
import logging
import sys
import types
from pathlib import Path

import pytest

ROOT = Path(__file__).parents[1]


class FakeParameter:
    """Small Katana string parameter with optional expression state."""

    def __init__(
        self,
        value: str,
        expression: str | None = None,
        values_by_time: dict[float, str] | None = None,
    ) -> None:
        self.value = value
        self.expression = expression
        self.values_by_time = dict(values_by_time or {})

    def getValue(self, time: float):
        """Return the evaluated parameter value at one timeline time."""
        return self.values_by_time.get(time, self.value)

    def setValue(self, value: str, _time: float) -> None:
        """Author a literal value and clear expression state."""
        self.value = value
        self.expression = None

    def isExpression(self) -> bool:
        """Return whether this parameter is expression-driven."""
        return self.expression is not None

    def getExpression(self) -> str:
        """Return the expression source."""
        return self.expression or ""


class FakeNode:
    """Katana node stand-in exposing a small parameter map."""

    def __init__(self, name: str, node_type: str, parameters: dict[str, FakeParameter]):
        self.name = name
        self.node_type = node_type
        self.parameters = parameters

    def getName(self) -> str:
        """Return the node name."""
        return self.name

    def getType(self) -> str:
        """Return the node type."""
        return self.node_type

    def getParameter(self, name: str):
        """Return one named parameter."""
        return self.parameters.get(name)


class FakeOptionalMixin:
    """Minimal optional-plugin activation contract."""

    def is_active(self, data: dict) -> bool:
        """Read the focused-test activation flag."""
        return data.get("_workfile_paths_active", True)


class FakeInstancePlugin:
    """Minimal Katana instance plugin base."""

    log = logging.getLogger("test_workfile_paths")


class FakeValidationError(RuntimeError):
    """Publish validation error preserving an optional title."""

    def __init__(self, message: str, *, title: str | None = None) -> None:
        super().__init__(message)
        self.title = title


class FakeAction:
    """Minimal Pyblish action base."""


class FakeRepairAction(FakeAction):
    """Minimal AYON repair action marker."""


class FakeUndoStack:
    """Record Katana undo group calls."""

    opened: list[str] = []
    closed = 0

    @classmethod
    def reset(cls) -> None:
        """Clear recorded calls."""
        cls.opened = []
        cls.closed = 0

    @classmethod
    def OpenGroup(cls, label: str) -> None:
        """Record an opened undo group."""
        cls.opened.append(label)

    @classmethod
    def CloseGroup(cls) -> None:
        """Record a closed undo group."""
        cls.closed += 1


def _load_source(monkeypatch, name: str, path: Path):
    """Load one repository module under a controlled module name."""
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    monkeypatch.setitem(sys.modules, name, module)
    spec.loader.exec_module(module)
    return module


def _install_runtime(monkeypatch, tmp_path: Path, nodes: list[FakeNode]):
    """Install compact Katana, AYON, and Pyblish modules for focused tests."""
    selected = []
    compat = types.ModuleType("ayon_katana.api.compat")
    compat.iter_nodes = lambda: iter(nodes)
    compat.set_selected_nodes = lambda values: selected.extend(values)

    workio = types.ModuleType("ayon_katana.api.workio")
    workio.get_current_workfile = lambda: str(tmp_path / "scene.katana")

    package = types.ModuleType("ayon_katana")
    package.__path__ = []
    api = types.ModuleType("ayon_katana.api")
    api.__path__ = []
    plugins = types.ModuleType("ayon_katana.plugins")
    plugins.__path__ = []
    publish_pkg = types.ModuleType("ayon_katana.plugins.publish")
    publish_pkg.__path__ = []
    monkeypatch.setitem(sys.modules, "ayon_katana", package)
    monkeypatch.setitem(sys.modules, "ayon_katana.api", api)
    monkeypatch.setitem(sys.modules, "ayon_katana.api.compat", compat)
    monkeypatch.setitem(sys.modules, "ayon_katana.api.workio", workio)
    monkeypatch.setitem(sys.modules, "ayon_katana.plugins", plugins)
    monkeypatch.setitem(sys.modules, "ayon_katana.plugins.publish", publish_pkg)
    api.compat = compat
    api.workio = workio

    dependencies = _load_source(
        monkeypatch,
        "ayon_katana.api.dependencies",
        ROOT / "client" / "ayon_katana" / "api" / "dependencies.py",
    )
    api.dependencies = dependencies

    plugin = types.ModuleType("ayon_katana.api.plugin")
    plugin.KatanaInstancePlugin = FakeInstancePlugin
    api.plugin = plugin
    monkeypatch.setitem(sys.modules, "ayon_katana.api.plugin", plugin)

    pyblish_api = types.ModuleType("pyblish.api")
    pyblish_api.Action = FakeAction
    pyblish_api.ValidatorOrder = 2.0
    pyblish = types.ModuleType("pyblish")
    pyblish.api = pyblish_api
    monkeypatch.setitem(sys.modules, "pyblish", pyblish)
    monkeypatch.setitem(sys.modules, "pyblish.api", pyblish_api)

    pipeline = types.ModuleType("ayon_core.pipeline")
    pipeline.OptionalPyblishPluginMixin = FakeOptionalMixin
    publish = types.ModuleType("ayon_core.pipeline.publish")
    publish.PublishValidationError = FakeValidationError
    publish.RepairAction = FakeRepairAction
    publish.get_errored_instances_from_context = lambda context, plugin=None: list(
        context.errored_instances
    )
    core = types.ModuleType("ayon_core")
    core.pipeline = pipeline
    monkeypatch.setitem(sys.modules, "ayon_core", core)
    monkeypatch.setitem(sys.modules, "ayon_core.pipeline", pipeline)
    monkeypatch.setitem(sys.modules, "ayon_core.pipeline.publish", publish)

    katana = types.ModuleType("Katana")
    katana.Utils = types.SimpleNamespace(UndoStack=FakeUndoStack)
    monkeypatch.setitem(sys.modules, "Katana", katana)

    validator = _load_source(
        monkeypatch,
        "ayon_katana.plugins.publish.validate_workfile_paths",
        ROOT
        / "client"
        / "ayon_katana"
        / "plugins"
        / "publish"
        / "validate_workfile_paths.py",
    )
    return dependencies, validator, selected


def _instance(**data):
    """Return a compact workfile publish instance."""
    defaults = {
        "frameStart": 1001,
        "frameEnd": 1003,
        "handleStart": 0,
        "handleEnd": 0,
    }
    defaults.update(data)
    context = types.SimpleNamespace(data=dict(defaults))
    return types.SimpleNamespace(data=defaults, context=context, name="workfileMain")


def test_collect_workfile_references_uses_explicit_registry(
    monkeypatch,
    tmp_path: Path,
) -> None:
    """Only the planned input node/parameter registry is inspected."""
    relative = FakeParameter("assets/model.usd")
    expression = FakeParameter(
        str(tmp_path / "cache.abc"),
        expression="projectPath + '/cache.abc'",
    )
    nodes = [
        FakeNode("Usd", "UsdIn", {"fileName": relative}),
        FakeNode("Abc", "Alembic_In", {"abcAsset": expression}),
        FakeNode("Output", "RenderOutputDefine", {"file": FakeParameter("bad.exr")}),
        FakeNode("Other", "Group", {"fileName": FakeParameter("ignored.usd")}),
    ]
    dependencies, _validator, _selected = _install_runtime(monkeypatch, tmp_path, nodes)

    references = dependencies.collect_workfile_references()

    assert [reference.label for reference in references] == [
        "Usd.fileName",
        "Abc.abcAsset",
    ]
    assert references[0].authored_value == "assets/model.usd"
    assert references[0].resolved_value == str(tmp_path / "assets" / "model.usd")
    assert references[0].is_expression is False
    assert references[1].authored_value == "projectPath + '/cache.abc'"
    assert references[1].resolved_value == str(tmp_path / "cache.abc")
    assert references[1].is_expression is True


def test_sequence_expansion_preserves_supported_tokens(
    monkeypatch,
    tmp_path: Path,
) -> None:
    """Hash, printf, and ``$F`` frame tokens expand deterministically."""
    dependencies, _validator, _selected = _install_runtime(monkeypatch, tmp_path, [])

    assert dependencies.expand_sequence_path("plate.####.exr", 12) == "plate.0012.exr"
    assert dependencies.expand_sequence_path("plate.%04d.exr", 12) == "plate.0012.exr"
    assert dependencies.expand_sequence_path("plate.$F4.exr", 12) == "plate.0012.exr"


def test_animated_expression_uses_required_frames_instead_of_frame_zero(
    monkeypatch,
    tmp_path: Path,
) -> None:
    """A complete animated dependency passes even when its frame-0 value is absent."""
    plates = tmp_path / "plates"
    plates.mkdir()
    frame_paths = {}
    for frame in (1001, 1002, 1003):
        path = plates / f"plate.{frame:04d}.exr"
        path.write_bytes(b"image")
        frame_paths[float(frame)] = str(path)
    parameter = FakeParameter(
        str(plates / "plate.0000.exr"),
        expression="getFramePath(frame)",
        values_by_time=frame_paths,
    )
    nodes = [FakeNode("Plate", "ImageRead", {"file": parameter})]
    dependencies, validator, _selected = _install_runtime(monkeypatch, tmp_path, nodes)
    reference = dependencies.collect_workfile_references()[0]

    assert not Path(reference.resolved_value).exists()
    assert dependencies.required_reference_paths(
        reference,
        frame_start=1001,
        frame_end=1003,
    ) == [frame_paths[1001.0], frame_paths[1002.0], frame_paths[1003.0]]
    validator.ValidateWorkfilePaths().process(_instance())


def test_animated_expression_rejects_missing_required_frame_even_when_frame_zero_exists(
    monkeypatch,
    tmp_path: Path,
) -> None:
    """A valid frame-0 value cannot hide a missing file in the publish range."""
    plates = tmp_path / "plates"
    plates.mkdir()
    frame_zero = plates / "plate.0000.exr"
    frame_zero.write_bytes(b"image")
    frame_paths = {}
    for frame in (1001, 1003):
        path = plates / f"plate.{frame:04d}.exr"
        path.write_bytes(b"image")
        frame_paths[float(frame)] = str(path)
    missing = plates / "plate.1002.exr"
    frame_paths[1002.0] = str(missing)
    parameter = FakeParameter(
        str(frame_zero),
        expression="getFramePath(frame)",
        values_by_time=frame_paths,
    )
    nodes = [FakeNode("Plate", "ImageRead", {"file": parameter})]
    _dependencies, validator, _selected = _install_runtime(monkeypatch, tmp_path, nodes)

    with pytest.raises(FakeValidationError, match="plate.1002.exr"):
        validator.ValidateWorkfilePaths().process(_instance())


def test_validator_accepts_existing_absolute_inputs(
    monkeypatch,
    tmp_path: Path,
) -> None:
    """Existing absolute registered inputs pass unchanged."""
    source = tmp_path / "asset.usd"
    source.write_text("#usda 1.0\n", encoding="utf-8")
    parameter = FakeParameter(str(source))
    nodes = [FakeNode("Usd", "UsdIn", {"fileName": parameter})]
    _dependencies, validator, _selected = _install_runtime(monkeypatch, tmp_path, nodes)

    validator.ValidateWorkfilePaths().process(_instance())

    assert parameter.value == str(source)


def test_relative_literal_is_repaired_only_after_source_verification(
    monkeypatch,
    tmp_path: Path,
) -> None:
    """A verified relative literal becomes absolute inside one undo group."""
    source = tmp_path / "assets" / "asset.usd"
    source.parent.mkdir()
    source.write_text("#usda 1.0\n", encoding="utf-8")
    parameter = FakeParameter("assets/asset.usd")
    nodes = [FakeNode("Usd", "UsdIn", {"fileName": parameter})]
    _dependencies, validator, _selected = _install_runtime(monkeypatch, tmp_path, nodes)
    FakeUndoStack.reset()
    instance = _instance()

    with pytest.raises(FakeValidationError, match="relative to the current workfile"):
        validator.ValidateWorkfilePaths().process(instance)

    validator.ValidateWorkfilePaths.repair(instance)

    assert Path(parameter.value) == source
    assert FakeUndoStack.opened == ["Repair AYON workfile paths"]
    assert FakeUndoStack.closed == 1


def test_sequence_validates_every_required_frame_and_does_not_repair_missing_source(
    monkeypatch,
    tmp_path: Path,
) -> None:
    """A relative image sequence is not repaired when any required frame is absent."""
    plates = tmp_path / "plates"
    plates.mkdir()
    for frame in (1001, 1003):
        (plates / f"plate.{frame:04d}.exr").write_bytes(b"image")
    parameter = FakeParameter("plates/plate.####.exr")
    nodes = [FakeNode("Plate", "ImageRead", {"file": parameter})]
    _dependencies, validator, _selected = _install_runtime(monkeypatch, tmp_path, nodes)
    instance = _instance()

    with pytest.raises(FakeValidationError, match="plate.1002.exr"):
        validator.ValidateWorkfilePaths().process(instance)

    validator.ValidateWorkfilePaths.repair(instance)
    assert parameter.value == "plates/plate.####.exr"


@pytest.mark.parametrize(
    "parameter",
    [
        FakeParameter("", expression="getenv('SHOW') + '/asset.usd'"),
        FakeParameter("$MISSING_SHOW/asset.usd"),
        FakeParameter("ayon://representation/abc123"),
        FakeParameter(""),
    ],
)
def test_unresolved_special_values_fail_without_repair(
    monkeypatch,
    tmp_path: Path,
    parameter: FakeParameter,
) -> None:
    """Expressions, env references, entity URIs, and empties are never rewritten."""
    original_value = parameter.value
    original_expression = parameter.expression
    nodes = [FakeNode("Usd", "UsdIn", {"fileName": parameter})]
    _dependencies, validator, _selected = _install_runtime(monkeypatch, tmp_path, nodes)
    instance = _instance()

    with pytest.raises(FakeValidationError):
        validator.ValidateWorkfilePaths().process(instance)

    validator.ValidateWorkfilePaths.repair(instance)
    assert parameter.value == original_value
    assert parameter.expression == original_expression


def test_disabled_validator_skips_collection(monkeypatch, tmp_path: Path) -> None:
    """Optional deactivation leaves invalid workfile inputs untouched."""
    parameter = FakeParameter("missing.usd")
    nodes = [FakeNode("Usd", "UsdIn", {"fileName": parameter})]
    _dependencies, validator, _selected = _install_runtime(monkeypatch, tmp_path, nodes)

    validator.ValidateWorkfilePaths().process(_instance(_workfile_paths_active=False))


def test_select_invalid_action_selects_registered_invalid_nodes(
    monkeypatch,
    tmp_path: Path,
) -> None:
    """Select Invalid targets the concrete nodes containing bad references."""
    parameter = FakeParameter("missing.usd")
    node = FakeNode("Usd", "UsdIn", {"fileName": parameter})
    _dependencies, validator, selected = _install_runtime(monkeypatch, tmp_path, [node])
    instance = _instance()
    context = types.SimpleNamespace(errored_instances=[instance])

    validator.SelectInvalidWorkfileReferences().process(
        context,
        validator.ValidateWorkfilePaths,
    )

    assert selected == [node]


def test_server_settings_enable_optional_workfile_path_validation() -> None:
    """Server defaults expose the validator as optional and active."""
    tree = ast.parse(
        (ROOT / "server" / "settings" / "main.py").read_text(encoding="utf-8")
    )
    assignment = next(
        node
        for node in tree.body
        if isinstance(node, ast.Assign)
        and any(
            isinstance(target, ast.Name) and target.id == "DEFAULT_VALUES"
            for target in node.targets
        )
    )
    defaults = ast.literal_eval(assignment.value)

    assert defaults["publish"]["ValidateWorkfilePaths"] == {
        "enabled": True,
        "optional": True,
        "active": True,
    }
