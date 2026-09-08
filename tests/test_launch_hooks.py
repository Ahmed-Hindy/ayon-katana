"""Tests for Katana-specific AYON Applications launch hooks."""

from __future__ import annotations

import importlib.util
import sys
import types
from pathlib import Path

ROOT = Path(__file__).parents[1]
REQUESTED_WORKFILE_ENV = "AYON_KATANA_WORKFILE_PATH"


def _load_hook_module(monkeypatch, filename: str):
    """Load a Katana launch hook with a minimal Applications substitute."""
    applications_module = types.ModuleType("ayon_applications")
    applications_module.LaunchTypes = types.SimpleNamespace(local="local")

    class PreLaunchHook:
        """Minimal base class used only for hook inheritance."""

    applications_module.PreLaunchHook = PreLaunchHook
    monkeypatch.setitem(sys.modules, "ayon_applications", applications_module)

    module_path = ROOT / "client" / "ayon_katana" / "hooks" / filename
    module_spec = importlib.util.spec_from_file_location(
        f"ayon_katana_{module_path.stem}_test", module_path
    )
    assert module_spec is not None
    assert module_spec.loader is not None
    module = importlib.util.module_from_spec(module_spec)
    module_spec.loader.exec_module(module)
    return module


def _make_hook(module, class_name: str, data: dict, environment: dict[str, str]):
    """Create a configured hook instance without Applications internals."""
    hook = getattr(module, class_name)()
    hook.data = data
    hook.log = types.SimpleNamespace(
        info=lambda *_args: None,
        warning=lambda *_args: None,
    )
    hook.launch_context = types.SimpleNamespace(
        launch_args=["katanaBin.exe"],
        env=environment,
        kwargs={},
    )
    return hook


def _make_workfile_hook(monkeypatch, data: dict, environment: dict[str, str]):
    """Create the Katana startup-workfile hook."""
    module = _load_hook_module(monkeypatch, "pre_add_workfile_arg.py")
    return _make_hook(
        module,
        "PrepareKatanaWorkfileLaunch",
        data,
        environment,
    )


def test_selected_workfile_is_passed_through_environment(
    monkeypatch, tmp_path: Path
) -> None:
    """A selected workfile uses the post-install environment contract."""
    selected_path = tmp_path / "selected.katana"
    last_path = tmp_path / "last.katana"
    selected_path.write_text("katana", encoding="utf-8")
    last_path.write_text("katana", encoding="utf-8")
    hook = _make_workfile_hook(
        monkeypatch,
        {
            "workfile_path": str(selected_path),
            "last_workfile_path": str(last_path),
            "start_last_workfile": True,
        },
        {"AYON_WORKDIR": str(tmp_path)},
    )

    hook.execute()

    assert hook.launch_context.launch_args == ["katanaBin.exe"]
    assert hook.launch_context.env[REQUESTED_WORKFILE_ENV] == str(selected_path)
    assert hook.launch_context.kwargs == {}


def test_last_workfile_respects_the_start_workfile_flag(
    monkeypatch, tmp_path: Path
) -> None:
    """A configured last workfile is used only when explicitly enabled."""
    workfile_path = tmp_path / "last.katana"
    workfile_path.write_text("katana", encoding="utf-8")
    enabled_hook = _make_workfile_hook(
        monkeypatch,
        {
            "last_workfile_path": str(workfile_path),
            "start_last_workfile": True,
        },
        {},
    )
    disabled_hook = _make_workfile_hook(
        monkeypatch,
        {
            "last_workfile_path": str(workfile_path),
            "start_last_workfile": False,
        },
        {},
    )

    enabled_hook.execute()
    disabled_hook.execute()

    assert enabled_hook.launch_context.env[REQUESTED_WORKFILE_ENV] == str(workfile_path)
    assert REQUESTED_WORKFILE_ENV not in disabled_hook.launch_context.env


def test_script_arguments_are_not_reordered(monkeypatch, tmp_path: Path) -> None:
    """The hook does not rely on Katana positional workfile ordering."""
    workfile_path = tmp_path / "selected.katana"
    workfile_path.write_text("katana", encoding="utf-8")
    hook = _make_workfile_hook(
        monkeypatch,
        {"workfile_path": str(workfile_path)},
        {},
    )
    hook.launch_context.launch_args.extend(["--script", "startup.py"])

    hook.execute()

    assert hook.launch_context.launch_args == [
        "katanaBin.exe",
        "--script",
        "startup.py",
    ]
    assert hook.launch_context.env[REQUESTED_WORKFILE_ENV] == str(workfile_path)


def test_invalid_workfiles_are_rejected(monkeypatch, tmp_path: Path) -> None:
    """Missing files, URIs, and non-Katana paths never reach startup."""
    text_path = tmp_path / "scene.txt"
    text_path.write_text("not katana", encoding="utf-8")
    candidates = [
        str(tmp_path / "missing.katana"),
        "ayon://project/folder/workfile.katana",
        str(text_path),
    ]

    for candidate in candidates:
        hook = _make_workfile_hook(
            monkeypatch,
            {"workfile_path": candidate},
            {REQUESTED_WORKFILE_ENV: "stale"},
        )

        hook.execute()

        assert REQUESTED_WORKFILE_ENV not in hook.launch_context.env
        assert hook.launch_context.launch_args == ["katanaBin.exe"]


def test_workdir_is_applied_by_the_path_hook(monkeypatch, tmp_path: Path) -> None:
    """The Katana path hook owns the Katana process cwd."""
    module = _load_hook_module(monkeypatch, "set_paths.py")
    hook = _make_hook(
        module,
        "SetPath",
        {},
        {"AYON_WORKDIR": str(tmp_path)},
    )

    hook.execute()

    assert hook.launch_context.kwargs["cwd"] == str(tmp_path)
    assert REQUESTED_WORKFILE_ENV not in hook.launch_context.env


def test_missing_workdir_does_not_set_a_process_cwd(monkeypatch) -> None:
    """The path hook leaves cwd unset when Core did not prepare a workdir."""
    module = _load_hook_module(monkeypatch, "set_paths.py")
    hook = _make_hook(module, "SetPath", {}, {})

    hook.execute()

    assert hook.launch_context.kwargs == {}


def test_display_view_hook_prepends_unique_enabled_overrides(monkeypatch) -> None:
    """Configured displays and views are prepended once to existing OCIO values."""
    module = _load_hook_module(monkeypatch, "set_default_display_and_view.py")
    environment = {
        "OCIO": "C:/config/config.ocio",
        "OCIO_ACTIVE_DISPLAYS": "sRGB:ACES",
        "OCIO_ACTIVE_VIEWS": "Raw:Film",
    }
    hook = _make_hook(
        module,
        "SetDefaultDisplayView",
        {
            "project_settings": {
                "katana": {
                    "imageio": {
                        "activate_host_color_management": True,
                        "workfile": {
                            "enabled": True,
                            "default_display": "ACES:P3",
                            "default_view": "Film:Log",
                        },
                    }
                }
            }
        },
        environment,
    )

    hook.execute()

    assert environment["OCIO_ACTIVE_DISPLAYS"] == "ACES:P3:sRGB"
    assert environment["OCIO_ACTIVE_VIEWS"] == "Film:Log:Raw"


def test_display_view_hook_leaves_environment_untouched_when_disabled(
    monkeypatch,
) -> None:
    """Disabled host management, overrides, missing OCIO, and empty values are inert."""
    module = _load_hook_module(monkeypatch, "set_default_display_and_view.py")
    base_environment = {
        "OCIO": "C:/config/config.ocio",
        "OCIO_ACTIVE_DISPLAYS": "sRGB",
        "OCIO_ACTIVE_VIEWS": "Raw",
    }
    settings_cases = [
        {
            "activate_host_color_management": False,
            "workfile": {"enabled": True, "default_display": "ACES"},
        },
        {
            "activate_host_color_management": True,
            "workfile": {"enabled": False, "default_display": "ACES"},
        },
        {
            "activate_host_color_management": True,
            "workfile": {"enabled": True, "default_display": "", "default_view": ""},
        },
    ]
    for imageio_settings in settings_cases:
        environment = dict(base_environment)
        hook = _make_hook(
            module,
            "SetDefaultDisplayView",
            {"project_settings": {"katana": {"imageio": imageio_settings}}},
            environment,
        )
        hook.execute()
        assert environment == base_environment

    environment = {
        "OCIO_ACTIVE_DISPLAYS": "sRGB",
        "OCIO_ACTIVE_VIEWS": "Raw",
    }
    hook = _make_hook(
        module,
        "SetDefaultDisplayView",
        {
            "project_settings": {
                "katana": {
                    "imageio": {
                        "activate_host_color_management": True,
                        "workfile": {
                            "enabled": True,
                            "default_display": "ACES",
                            "default_view": "Film",
                        },
                    }
                }
            }
        },
        environment,
    )
    hook.execute()
    assert environment == {
        "OCIO_ACTIVE_DISPLAYS": "sRGB",
        "OCIO_ACTIVE_VIEWS": "Raw",
    }
