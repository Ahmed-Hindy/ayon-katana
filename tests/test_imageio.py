"""Focused contracts for Katana ImageIO settings and Core file-rule fallback."""

from __future__ import annotations

import ast
import importlib.util
import re
import sys
import types
from pathlib import Path

import pytest

ROOT = Path(__file__).parents[1]


def _load_colorspace_api(monkeypatch, calls: dict):
    """Load Katana colorspace helpers with a controlled AYON Core API."""
    attr_module = types.ModuleType("attr")
    attr_module.s = lambda cls: cls
    attr_module.ib = lambda *args, **kwargs: None
    monkeypatch.setitem(sys.modules, "attr", attr_module)

    ayon_core = types.ModuleType("ayon_core")
    ayon_core.__path__ = []
    pipeline = types.ModuleType("ayon_core.pipeline")
    pipeline.__path__ = []
    core_colorspace = types.ModuleType("ayon_core.pipeline.colorspace")
    core_settings = types.ModuleType("ayon_core.settings")

    core_colorspace.get_ocio_config_colorspaces = lambda _path: {"roles": {}}

    def get_config(
        project_name,
        folder_path,
        task_name,
        host_name,
        app_name,
        *,
        project_settings,
    ):
        calls["config"] = {
            "project_name": project_name,
            "folder_path": folder_path,
            "task_name": task_name,
            "host_name": host_name,
            "app_name": app_name,
            "project_settings": project_settings,
        }
        return {"path": "C:/ocio/config.ocio", "template": "{root}/config.ocio"}

    def get_rules(project_name, host_name, project_settings):
        calls["rules"] = (project_name, host_name, project_settings)
        return [
            {
                "name": "plates",
                "pattern": "plate",
                "ext": ".exr",
                "colorspace": "ACEScg",
            }
        ]

    def match_rule(
        filepath,
        host_name,
        project_name,
        config_data,
        *,
        file_rules,
        project_settings,
    ):
        calls["match"] = {
            "filepath": filepath,
            "host_name": host_name,
            "project_name": project_name,
            "config_data": config_data,
            "file_rules": file_rules,
            "project_settings": project_settings,
        }
        return "ACEScg"

    core_colorspace.get_imageio_config_preset = get_config
    core_colorspace.get_imageio_file_rules = get_rules
    core_colorspace.get_imageio_file_rules_colorspace_from_filepath = match_rule

    def get_project_settings(project_name):
        calls["settings_project"] = project_name
        return calls["settings"]

    core_settings.get_project_settings = get_project_settings

    ayon_core.pipeline = pipeline
    monkeypatch.setitem(sys.modules, "ayon_core", ayon_core)
    monkeypatch.setitem(sys.modules, "ayon_core.pipeline", pipeline)
    monkeypatch.setitem(sys.modules, "ayon_core.pipeline.colorspace", core_colorspace)
    monkeypatch.setitem(sys.modules, "ayon_core.settings", core_settings)

    path = ROOT / "client" / "ayon_katana" / "api" / "colorspace.py"
    spec = importlib.util.spec_from_file_location("ayon_katana_imageio_test", path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_core_file_rule_fallback_uses_katana_context(monkeypatch) -> None:
    """Katana asks Core 1.9.9 for host/global rules without a local rule engine."""
    settings = {
        "katana": {
            "imageio": {
                "activate_host_color_management": True,
                "file_rules": {"activate_host_rules": False, "rules": []},
            }
        },
        "core": {"imageio": {"activate_global_color_management": True}},
    }
    calls = {"settings": settings}
    module = _load_colorspace_api(monkeypatch, calls)
    monkeypatch.setenv("AYON_APP_NAME", "katana/9.0")
    context = {
        "project": {"name": "Demo"},
        "folder": {"path": "/assets/hero"},
        "task": {"name": "lookdev"},
    }

    result = module.get_imageio_file_rule_colorspace(
        "G:/plates/hero_plate.1001.exr",
        context,
    )

    assert result == "ACEScg"
    assert calls["config"] == {
        "project_name": "Demo",
        "folder_path": "/assets/hero",
        "task_name": "lookdev",
        "host_name": "katana",
        "app_name": "katana/9.0",
        "project_settings": settings,
    }
    assert calls["rules"] == ("Demo", "katana", settings)
    assert calls["match"]["filepath"] == "G:/plates/hero_plate.1001.exr"
    assert calls["match"]["host_name"] == "katana"
    assert calls["match"]["file_rules"][0]["colorspace"] == "ACEScg"


def test_cross_project_load_queries_settings_for_loaded_project(monkeypatch) -> None:
    """A project B image uses project B settings while Katana is in project A."""
    settings_b = {"katana": {"imageio": {"activate_host_color_management": True}}}
    calls = {"settings": settings_b}
    module = _load_colorspace_api(monkeypatch, calls)
    monkeypatch.setenv("AYON_PROJECT_NAME", "ProjectA")

    module.get_imageio_file_rule_colorspace(
        "plate.exr", {"project": {"name": "ProjectB"}}
    )

    assert calls["settings_project"] == "ProjectB"
    assert calls["config"]["project_name"] == "ProjectB"
    assert calls["config"]["project_settings"] is settings_b
    assert calls["match"]["project_settings"] is settings_b


@pytest.mark.parametrize("explicit", [False, True])
def test_supplied_project_settings_do_not_trigger_another_lookup(monkeypatch, explicit):
    """Explicit settings take precedence over context settings and Core lookup."""
    calls = {}
    module = _load_colorspace_api(monkeypatch, calls)
    context_settings = {"from": "context"}
    explicit_settings = {"from": "argument"}
    context = {"project": {"name": "Demo"}, "project_settings": context_settings}

    module.get_imageio_file_rule_colorspace(
        "plate.exr", context, explicit_settings if explicit else None
    )

    assert "settings_project" not in calls
    assert calls["config"]["project_settings"] is (
        explicit_settings if explicit else context_settings
    )


@pytest.mark.parametrize(
    ("module_name", "function_name", "error"),
    [
        ("ayon_core.settings", "get_project_settings", RuntimeError("settings failed")),
        (
            "ayon_core.pipeline.colorspace",
            "get_imageio_config_preset",
            FileExistsError("configured config is missing"),
        ),
        (
            "ayon_core.pipeline.colorspace",
            "get_imageio_file_rules",
            KeyError("broken contract"),
        ),
        (
            "ayon_core.pipeline.colorspace",
            "get_imageio_file_rules_colorspace_from_filepath",
            re.error("invalid rule"),
        ),
        (
            "ayon_core.pipeline.colorspace",
            "get_imageio_file_rules_colorspace_from_filepath",
            TypeError("wrong arguments"),
        ),
    ],
)
def test_file_rule_errors_propagate(monkeypatch, module_name, function_name, error):
    """Configuration and programming failures cannot become unmatched rules."""
    module = _load_colorspace_api(monkeypatch, {"settings": {}})

    def fail(*args, **kwargs):
        raise error

    monkeypatch.setattr(sys.modules[module_name], function_name, fail)
    with pytest.raises(type(error)) as caught:
        module.get_imageio_file_rule_colorspace(
            "plate.exr", {"project": {"name": "Demo"}}
        )
    assert caught.value is error


@pytest.mark.parametrize(
    "condition", ["missing_context", "disabled_config", "unmatched_rule"]
)
def test_optional_file_rule_states_return_empty(monkeypatch, condition):
    """Absent context, disabled config, and no matching rule remain valid states."""
    calls = {"settings": {}}
    module = _load_colorspace_api(monkeypatch, calls)
    core = sys.modules["ayon_core.pipeline.colorspace"]
    if condition == "disabled_config":
        monkeypatch.setattr(core, "get_imageio_config_preset", lambda *a, **kw: {})
    elif condition == "unmatched_rule":
        monkeypatch.setattr(
            core,
            "get_imageio_file_rules_colorspace_from_filepath",
            lambda *a, **kw: None,
        )

    result = module.get_imageio_file_rule_colorspace(
        "plate.exr",
        {} if condition == "missing_context" else {"project": {"name": "Demo"}},
    )

    assert result == ""
    if condition == "missing_context":
        assert "settings_project" not in calls
    if condition == "disabled_config":
        assert "rules" not in calls


def test_scene_linear_distinguishes_unset_and_invalid_config(monkeypatch, tmp_path):
    """An unset OCIO config is optional, but an explicit missing path is an error."""
    module = _load_colorspace_api(monkeypatch, {})
    monkeypatch.delenv("OCIO", raising=False)
    assert module.get_scene_linear_colorspace() == ""
    monkeypatch.setenv("OCIO", str(tmp_path / "missing.ocio"))
    with pytest.raises(FileNotFoundError, match="OCIO config does not exist"):
        module.get_scene_linear_colorspace()


def test_scene_linear_propagates_parser_errors_and_invalid_core_data(
    monkeypatch, tmp_path
):
    """A parser failure or broken Core result must not erase the colorspace."""
    module = _load_colorspace_api(monkeypatch, {})
    config = tmp_path / "config.ocio"
    config.touch()
    monkeypatch.setenv("OCIO", str(config))

    def fail(path):
        raise RuntimeError("invalid OCIO")

    monkeypatch.setattr(module, "get_ocio_config_colorspaces", fail)
    with pytest.raises(RuntimeError, match="invalid OCIO"):
        module.get_scene_linear_colorspace()
    monkeypatch.setattr(module, "get_ocio_config_colorspaces", lambda path: {})
    with pytest.raises(KeyError, match="roles"):
        module.get_scene_linear_colorspace()
    monkeypatch.setattr(
        module, "get_ocio_config_colorspaces", lambda path: {"roles": {}}
    )
    assert module.get_scene_linear_colorspace() == ""
    monkeypatch.setattr(
        module,
        "get_ocio_config_colorspaces",
        lambda path: {"roles": {"scene_linear": {"colorspace": "ACEScg"}}},
    )
    assert module.get_scene_linear_colorspace() == "ACEScg"


def test_core_file_rule_fallback_respects_disabled_host_management(monkeypatch) -> None:
    """Disabling Katana host management bypasses Core rule evaluation."""
    settings = {
        "katana": {
            "imageio": {
                "activate_host_color_management": False,
                "file_rules": {"activate_host_rules": False, "rules": []},
            }
        }
    }
    calls = {"settings": settings}
    module = _load_colorspace_api(monkeypatch, calls)

    result = module.get_imageio_file_rule_colorspace(
        "G:/plates/hero_plate.1001.exr",
        {"project": {"name": "Demo"}},
    )

    assert result == ""
    assert "config" not in calls
    assert "rules" not in calls
    assert "match" not in calls


def test_server_defaults_expose_core_compatible_imageio_shape() -> None:
    """Katana defaults match the Core-compatible ImageIO contract."""
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
    defaults = ast.literal_eval(assignment.value)

    assert defaults["imageio"] == {
        "activate_host_color_management": True,
        "file_rules": {
            "activate_host_rules": False,
            "rules": [],
        },
        "workfile": {
            "enabled": False,
            "default_display": "",
            "default_view": "",
            "review_color_space": "",
        },
    }
