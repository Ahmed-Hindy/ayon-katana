"""Focused contracts for Katana ImageIO settings and Core file-rule fallback."""

from __future__ import annotations

import ast
import importlib.util
import sys
import types
from pathlib import Path

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
    context_tools = types.ModuleType("ayon_core.pipeline.context_tools")

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
    context_tools.get_current_project_settings = lambda: calls["settings"]

    ayon_core.pipeline = pipeline
    monkeypatch.setitem(sys.modules, "ayon_core", ayon_core)
    monkeypatch.setitem(sys.modules, "ayon_core.pipeline", pipeline)
    monkeypatch.setitem(sys.modules, "ayon_core.pipeline.colorspace", core_colorspace)
    monkeypatch.setitem(sys.modules, "ayon_core.pipeline.context_tools", context_tools)

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
