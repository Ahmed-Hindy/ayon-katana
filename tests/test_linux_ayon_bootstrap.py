"""Security and Docker-boundary tests for Linux AYON live bootstrap."""

from __future__ import annotations

import importlib.util
import sys
import types
from pathlib import Path

import pytest

BOOTSTRAP_PATH = Path(__file__).parent / "live" / "katana" / "linux_ayon_bootstrap.py"


def _load_bootstrap():
    """Import the bootstrap helper without requiring AYON or Docker."""
    spec = importlib.util.spec_from_file_location(
        "ayon_katana_linux_ayon_bootstrap_test",
        BOOTSTRAP_PATH,
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_loopback_server_url_maps_to_docker_host_gateway() -> None:
    """Host-local AYON URLs must remain reachable from Docker Desktop."""
    module = _load_bootstrap()

    assert module._container_server_url("http://127.0.0.1:5000/api") == (
        "http://host.docker.internal:5000/api"
    )
    assert module._container_server_url("http://localhost:5000") == (
        "http://host.docker.internal:5000"
    )
    assert module._container_server_url("https://ayon.example.com") == (
        "https://ayon.example.com"
    )


def test_bootstrap_keeps_authentication_secrets_out_of_docker_arguments(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """AYON and Kitsu secrets are inherited by Docker and never serialized."""
    module = _load_bootstrap()
    monkeypatch.setattr(module, "REPOSITORY_ROOT", tmp_path)
    monkeypatch.setattr(module, "_create_volume", lambda _name: None)
    monkeypatch.setattr(
        module,
        "_load_kitsu_credentials",
        lambda: ("artist@example.com", "kitsu-secret"),
    )
    monkeypatch.setenv("AYON_SERVER_URL", "http://127.0.0.1:5000")
    monkeypatch.setenv("AYON_API_KEY", "ayon-secret")
    monkeypatch.setenv("AYON_KATANA_LIVE_PROJECT", "ProjectA")
    monkeypatch.setenv("AYON_KATANA_LIVE_FOLDER", "/assets/hero")
    monkeypatch.setenv("AYON_KATANA_LIVE_TASK", "lookdev")
    monkeypatch.setenv("AYON_KATANA_LIVE_APPLICATIONS", "katana/9.0v1")
    monkeypatch.setenv("AYON_KATANA_LIVE_SUITE", "native")

    captured = {}

    def fake_run(command, *, env, check, **_kwargs):
        captured["command"] = command
        captured["env"] = env
        captured["check"] = check
        return types.SimpleNamespace(returncode=0)

    monkeypatch.setattr(module.subprocess, "run", fake_run)

    with pytest.raises(SystemExit) as exc_info:
        module.main()

    assert exc_info.value.code == 0
    command = captured["command"]
    serialized = " ".join(command)
    assert "ayon-secret" not in serialized
    assert "kitsu-secret" not in serialized
    assert "artist@example.com" not in serialized
    for name in ("AYON_API_KEY", "KITSU_LOGIN", "KITSU_PWD"):
        index = command.index(name)
        assert command[index - 1 : index + 1] == ["-e", name]

    env = captured["env"]
    assert env["AYON_API_KEY"] == "ayon-secret"
    assert env["AYON_SERVER_URL"] == "http://host.docker.internal:5000"
    assert env["KITSU_LOGIN"] == "artist@example.com"
    assert env["KITSU_PWD"] == "kitsu-secret"
    assert env["PYTHON_KEYRING_BACKEND"] == "headless_keyring.EnvironmentKeyring"
    assert env["PYTHONPATH"] == "/workspace/tests/live/katana"
    assert env["AYON_KATANA_LIVE_EXECUTABLE"] == ("/opt/Katana9.0v1/bin/katanaBin")
    assert captured["check"] is False


def test_bootstrap_requires_windows_kitsu_credentials(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Headless Linux launch must not silently bypass Kitsu readiness."""
    module = _load_bootstrap()
    fake_credentials = types.ModuleType("ayon_kitsu.credentials")
    fake_credentials.load_credentials = lambda: (None, None)
    fake_package = types.ModuleType("ayon_kitsu")
    monkeypatch.setitem(sys.modules, "ayon_kitsu", fake_package)
    monkeypatch.setitem(sys.modules, "ayon_kitsu.credentials", fake_credentials)

    with pytest.raises(RuntimeError, match="Kitsu credentials are not available"):
        module._load_kitsu_credentials()
