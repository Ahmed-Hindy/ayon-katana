"""Unit tests for pure configuration in the beta live Katana runner."""

from __future__ import annotations

import importlib.util
import os
import subprocess
import sys
from pathlib import Path

import pytest

RUNNER_PATH = Path(__file__).parent / "live" / "katana" / "run.py"
WORKFLOW_PATH = (
    Path(__file__).parent.parent / ".github" / "workflows" / "live-katana-beta.yml"
)
NORMAL_CI_PATH = Path(__file__).parent.parent / ".github" / "workflows" / "ci.yml"


def _load_runner():
    """Import the live runner without requiring AYON or Katana."""
    spec = importlib.util.spec_from_file_location(
        "ayon_katana_live_runner",
        RUNNER_PATH,
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_live_runner_strips_only_installed_katana_addon_paths() -> None:
    """Checkout injection must not discard unrelated AYON or host paths."""
    runner = _load_runner()
    value = os.pathsep.join(
        [
            r"C:\AYON\addons\core_1.9.9",
            r"C:\AYON\addons\katana_0.1.64\ayon_katana",
            r"C:\Program Files\Katana9.0v1\plugins",
        ]
    )

    result = runner.without_installed_katana_addon(value)

    assert "katana_0.1.64" not in result
    assert r"C:\AYON\addons\core_1.9.9" in result
    assert r"C:\Program Files\Katana9.0v1\plugins" in result


def test_live_runner_executable_override_keeps_ayon_environment(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """Linux can override only Katana discovery while preserving AYON launch env."""
    runner = _load_runner()
    executable = tmp_path / "Katana9.0v1" / "bin" / "katanaBin"
    executable.parent.mkdir(parents=True)
    executable.write_text("", encoding="utf-8")
    monkeypatch.setenv("AYON_KATANA_LIVE_EXECUTABLE", str(executable))

    class FakeApplication:
        def find_executable(self):
            raise AssertionError("Platform executable lookup must be bypassed.")

    class FakeApplicationsManager:
        applications = {"katana/9.0v1": FakeApplication()}

    class FakeApplicationsAddon:
        @staticmethod
        def get_app_environments_for_context(*_args):
            return {"KATANA_ROOT": "/wrong/platform/path", "AYON_TEST": "1"}

    config = runner.LiveConfig(
        project_name="ProjectA",
        folder_path="/assets/hero",
        task_name="lookdev",
        applications=("katana/9.0v1",),
        suites=("native",),
        output_root=tmp_path,
        existing_workfile=None,
        timeout_seconds=30,
    )

    resolved, base_env = runner._resolve_application_run(
        config,
        "katana/9.0v1",
        FakeApplicationsAddon(),
        FakeApplicationsManager(),
    )
    assert resolved == executable.resolve()
    assert base_env["AYON_TEST"] == "1"

    launch_env = runner.prepare_environment(
        base_env,
        "katana/9.0v1",
        tmp_path / "out",
        tmp_path / "result.json",
        None,
    )
    assert launch_env["KATANA_ROOT"] == str(executable.resolve().parent.parent)


def test_live_runner_loads_explicit_local_configuration(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """Environment configuration stays explicit and machine-independent."""
    runner = _load_runner()
    monkeypatch.setenv("AYON_KATANA_LIVE_PROJECT", "ProjectA")
    monkeypatch.setenv("AYON_KATANA_LIVE_FOLDER", "/assets/hero")
    monkeypatch.setenv("AYON_KATANA_LIVE_TASK", "lookdev")
    monkeypatch.setenv("AYON_KATANA_LIVE_APPLICATIONS", "katana/9.0v1")
    monkeypatch.setenv("AYON_KATANA_LIVE_SUITE", "native,integration,acceptance")
    monkeypatch.setenv("AYON_KATANA_LIVE_OUTPUT", str(tmp_path))
    monkeypatch.delenv("AYON_KATANA_LIVE_WORKFILE", raising=False)
    monkeypatch.delenv("AYON_KATANA_LIVE_TIMEOUT", raising=False)

    config = runner.load_config()

    assert config.project_name == "ProjectA"
    assert config.folder_path == "/assets/hero"
    assert config.task_name == "lookdev"
    assert config.applications == ("katana/9.0v1",)
    assert config.suites == ("native", "integration", "acceptance")
    assert config.output_root == tmp_path
    assert config.existing_workfile is None


def test_live_runner_rejects_filesystem_rewritten_folder_path(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """MSYS path rewriting fails before AYON prelaunch hooks are invoked."""
    runner = _load_runner()
    monkeypatch.setenv("AYON_KATANA_LIVE_PROJECT", "ProjectA")
    monkeypatch.setenv(
        "AYON_KATANA_LIVE_FOLDER",
        r"C:\Program Files\Git\sequences\sq01\sh010",
    )
    monkeypatch.setenv("AYON_KATANA_LIVE_TASK", "lookdev")

    with pytest.raises(RuntimeError, match="AYON folder path beginning with '/'"):
        runner.load_config()


def test_live_runner_automated_suite_excludes_private_workfile_case(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Automated coverage runs all disposable suites without a personal workfile."""
    runner = _load_runner()
    monkeypatch.setenv("AYON_KATANA_LIVE_PROJECT", "ProjectA")
    monkeypatch.setenv("AYON_KATANA_LIVE_FOLDER", "/assets/hero")
    monkeypatch.setenv("AYON_KATANA_LIVE_TASK", "lookdev")
    monkeypatch.setenv("AYON_KATANA_LIVE_SUITE", "automated")
    monkeypatch.delenv("AYON_KATANA_LIVE_WORKFILE", raising=False)
    monkeypatch.delenv("AYON_KATANA_LIVE_TIMEOUT", raising=False)

    config = runner.load_config()

    assert config.suites == ("native", "integration", "acceptance", "render")
    assert "ui" in runner.VALID_SUITES
    assert "ui" not in runner.AUTOMATED_SUITES
    assert config.existing_workfile is None
    assert runner._suite_script("acceptance").name == "acceptance_smoke.py"
    assert runner._suite_script("render").name == "render_smoke.py"


def test_live_runner_requires_workfile_only_for_existing_suite(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Existing-scene coverage is opt-in and never tied to a personal path."""
    runner = _load_runner()
    monkeypatch.setenv("AYON_KATANA_LIVE_PROJECT", "ProjectA")
    monkeypatch.setenv("AYON_KATANA_LIVE_FOLDER", "/assets/hero")
    monkeypatch.setenv("AYON_KATANA_LIVE_TASK", "lookdev")
    monkeypatch.setenv("AYON_KATANA_LIVE_SUITE", "existing")
    monkeypatch.delenv("AYON_KATANA_LIVE_WORKFILE", raising=False)

    with pytest.raises(RuntimeError, match="AYON_KATANA_LIVE_WORKFILE"):
        runner.load_config()


def test_live_runner_rejects_missing_existing_workfile(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """Existing-workfile suite fails before Katana when the fixture is absent."""
    runner = _load_runner()
    monkeypatch.setenv("AYON_KATANA_LIVE_PROJECT", "ProjectA")
    monkeypatch.setenv("AYON_KATANA_LIVE_FOLDER", "/assets/hero")
    monkeypatch.setenv("AYON_KATANA_LIVE_TASK", "lookdev")
    monkeypatch.setenv("AYON_KATANA_LIVE_SUITE", "existing")
    monkeypatch.setenv("AYON_KATANA_LIVE_WORKFILE", str(tmp_path / "missing.katana"))

    with pytest.raises(RuntimeError, match="does not exist"):
        runner.load_config()


def test_live_runner_rejects_invalid_timeout(monkeypatch: pytest.MonkeyPatch) -> None:
    """Invalid timeout values fail before a Katana process is started."""
    runner = _load_runner()
    monkeypatch.setenv("AYON_KATANA_LIVE_PROJECT", "ProjectA")
    monkeypatch.setenv("AYON_KATANA_LIVE_FOLDER", "/assets/hero")
    monkeypatch.setenv("AYON_KATANA_LIVE_TASK", "lookdev")
    monkeypatch.setenv("AYON_KATANA_LIVE_TIMEOUT", "forever")

    with pytest.raises(RuntimeError, match="must be a whole number"):
        runner.load_config()


def test_live_runner_timeout_is_structured_failure(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """Host timeouts return useful JSON state instead of crashing the runner."""
    runner = _load_runner()
    config = runner.LiveConfig(
        project_name="ProjectA",
        folder_path="/assets/hero",
        task_name="lookdev",
        applications=("katana/9.0v1",),
        suites=("native",),
        output_root=tmp_path,
        existing_workfile=None,
        timeout_seconds=1,
    )

    def time_out(*_args, **_kwargs):
        raise subprocess.TimeoutExpired(cmd="katanaBin.exe", timeout=1)

    monkeypatch.setattr(runner.subprocess, "run", time_out)
    result = runner._run_suite(
        Path("katanaBin.exe"),
        "katana/9.0v1",
        "native",
        {},
        config,
    )

    assert result["success"] is False
    assert result["return_code"] is None
    assert "exceeded 1 seconds" in result["error"]


def test_live_runner_ui_suite_terminates_disposable_process_after_result(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """UI smoke consumes its result and terminates the disposable Katana UI."""
    runner = _load_runner()
    config = runner.LiveConfig(
        project_name="ProjectA",
        folder_path="/assets/hero",
        task_name="lookdev",
        applications=("katana/9.0v1",),
        suites=("ui",),
        output_root=tmp_path,
        existing_workfile=None,
        timeout_seconds=30,
    )

    class FakeProcess:
        def __init__(self):
            self.terminated = False

        def poll(self):
            return 0 if self.terminated else None

        def terminate(self):
            self.terminated = True

        def wait(self, timeout):
            assert timeout == 10
            return 0

    captured = {}

    def fake_popen(_command, **kwargs):
        process = FakeProcess()
        captured["process"] = process
        captured["env"] = kwargs["env"]
        Path(kwargs["env"]["AYON_KATANA_LIVE_RESULT"]).write_text(
            '{"success": true, "checks": ["ui"], "coverage_gaps": []}',
            encoding="utf-8",
        )
        return process

    monkeypatch.setattr(runner.subprocess, "Popen", fake_popen)
    result = runner._run_ui_suite(
        Path("katanaBin.exe"),
        "katana/9.0v1",
        {},
        config,
    )

    assert result["success"] is True
    assert result["return_code"] == 0
    assert captured["process"].terminated is True
    assert captured["env"]["KATANA_RESOURCES"].split(os.pathsep)[0] == str(
        runner.UI_PROBE_RESOURCE
    )


def test_public_summary_strips_sensitive_live_details() -> None:
    """Public CI artifacts omit local paths, observations, and tracebacks."""
    runner = _load_runner()
    public = runner.build_public_summary(
        {
            "katana/9.0v1": {
                "integration": {
                    "success": False,
                    "return_code": 1,
                    "checks": ["creator smoke"],
                    "coverage_gaps": [],
                    "error_type": "RuntimeError",
                    "error": r"C:\Users\Artist\secret\scene.katana failed",
                    "log": r"C:\actions\_work\katana.log",
                    "observations": {"ocio": r"C:\studio\config.ocio"},
                }
            }
        }
    )

    result = public["katana/9.0v1"]["integration"]
    assert result == {
        "success": False,
        "return_code": 1,
        "checks": ["creator smoke"],
        "coverage_gaps": [],
        "error_type": "RuntimeError",
    }


def test_beta_live_workflow_stays_manual_local_first_and_private() -> None:
    """WIP live CI stays manual, non-required, and free of private artifacts."""
    workflow = WORKFLOW_PATH.read_text(encoding="utf-8")
    normal_ci = NORMAL_CI_PATH.read_text(encoding="utf-8")

    assert "[BETA/WIP]" in workflow
    assert "workflow_dispatch:" in workflow
    assert "persist-credentials: false" in workflow
    assert "pull_request:" not in workflow
    assert "push:" not in workflow
    assert "continue-on-error" not in workflow
    assert "AYON_KATANA_LIVE_WORKFILE" not in workflow
    assert "-QuietHostOutput" in workflow
    assert "-PublicOutput" in workflow
    assert "public-summary.json" in workflow
    assert "- acceptance" in workflow
    assert "- automated" in workflow
    assert "windows_ui:" in workflow
    assert "-Suite ui" in workflow
    assert ".artifacts/live-katana-ui/public-summary.json" in workflow
    assert "linux_probe:" in workflow
    assert "run-linux-probe.ps1" in workflow
    assert "inputs.linux_ayon" in workflow
    assert "run-linux-ayon.ps1" in workflow
    assert ".artifacts/live-katana-linux/public-summary.json" in workflow
    assert "build-linux-image.ps1" not in workflow
    assert "Katana9.0v1-linux-x86-release-64.tgz" not in workflow
    assert "path: .artifacts/live-katana\n" not in workflow
    assert "tests/live/katana" not in normal_ci


def test_application_setup_failures_are_safe_for_public_summary() -> None:
    """Missing app variants retain local diagnostics without leaking publicly."""
    runner = _load_runner()
    failure = runner._setup_failure(
        RuntimeError(r"Katana executable missing under C:\Users\Artist")
    )

    assert failure["error_type"] == "RuntimeError"
    assert "C:\\Users\\Artist" in failure["error"]
    public = runner.build_public_summary({"katana/missing": {"setup": failure}})
    assert public == {
        "katana/missing": {
            "setup": {
                "success": False,
                "return_code": None,
                "error_type": "RuntimeError",
            }
        }
    }


def test_live_runner_rejects_unknown_suite(monkeypatch: pytest.MonkeyPatch) -> None:
    """Typos fail before any Katana process or license is requested."""
    runner = _load_runner()
    monkeypatch.setenv("AYON_KATANA_LIVE_PROJECT", "ProjectA")
    monkeypatch.setenv("AYON_KATANA_LIVE_FOLDER", "/assets/hero")
    monkeypatch.setenv("AYON_KATANA_LIVE_TASK", "lookdev")
    monkeypatch.setenv("AYON_KATANA_LIVE_SUITE", "mock-everything")

    with pytest.raises(RuntimeError, match="Unknown live Katana suite"):
        runner.load_config()
