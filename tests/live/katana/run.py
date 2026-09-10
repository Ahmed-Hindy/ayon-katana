"""BETA/WIP local runner for live AYON Katana contract tests.

This module is intentionally not a pytest test. Run it through AYON Console so
it can resolve the configured Applications addon environment, then it launches
real ``katanaBin`` processes with the current checkout injected ahead of any
installed Katana addon.
"""

from __future__ import annotations

import json
import os
import subprocess
from dataclasses import dataclass
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_APPLICATIONS = ("katana/9.0v1", "katana/8.0v1")
VALID_SUITES = ("native", "integration", "existing")


@dataclass(frozen=True)
class LiveConfig:
    """Environment-driven configuration for the local live runner."""

    project_name: str
    folder_path: str
    task_name: str
    applications: tuple[str, ...]
    suites: tuple[str, ...]
    output_root: Path
    existing_workfile: Path | None
    timeout_seconds: int


def _required_env(name: str) -> str:
    """Return one required non-empty environment value."""
    value = os.environ.get(name, "").strip()
    if not value:
        raise RuntimeError(f"Required environment variable is not set: {name}")
    return value


def _csv(value: str) -> tuple[str, ...]:
    """Split a comma-separated environment value into non-empty items."""
    return tuple(item.strip() for item in value.split(",") if item.strip())


def load_config() -> LiveConfig:
    """Build live-test configuration from environment variables."""
    folder_path = _required_env("AYON_KATANA_LIVE_FOLDER")
    if not folder_path.startswith("/"):
        raise RuntimeError(
            "AYON_KATANA_LIVE_FOLDER must be an AYON folder path beginning with '/'. "
            "On Windows, run the documented command from PowerShell so MSYS/Git-Bash "
            "does not rewrite it as a filesystem path."
        )

    applications = _csv(
        os.environ.get(
            "AYON_KATANA_LIVE_APPLICATIONS",
            ",".join(DEFAULT_APPLICATIONS),
        )
    )
    if not applications:
        raise RuntimeError("AYON_KATANA_LIVE_APPLICATIONS resolved to no applications.")

    suite_value = os.environ.get("AYON_KATANA_LIVE_SUITE", "native").strip().casefold()
    suites = VALID_SUITES if suite_value == "all" else _csv(suite_value)
    if not suites:
        raise RuntimeError("AYON_KATANA_LIVE_SUITE resolved to no suites.")
    unknown = sorted(set(suites) - set(VALID_SUITES))
    if unknown:
        raise RuntimeError(f"Unknown live Katana suite(s): {', '.join(unknown)}")

    workfile_value = os.environ.get("AYON_KATANA_LIVE_WORKFILE", "").strip()
    existing_workfile = Path(workfile_value).resolve() if workfile_value else None
    if "existing" in suites:
        if existing_workfile is None:
            raise RuntimeError(
                "AYON_KATANA_LIVE_WORKFILE is required for the existing-workfile suite."
            )
        if not existing_workfile.is_file():
            raise RuntimeError(
                f"AYON_KATANA_LIVE_WORKFILE does not exist: {existing_workfile}"
            )

    timeout_value = os.environ.get("AYON_KATANA_LIVE_TIMEOUT", "240").strip()
    try:
        timeout_seconds = int(timeout_value)
    except ValueError as exc:
        raise RuntimeError("AYON_KATANA_LIVE_TIMEOUT must be a whole number.") from exc
    if timeout_seconds < 1:
        raise RuntimeError("AYON_KATANA_LIVE_TIMEOUT must be greater than zero.")

    output_value = os.environ.get("AYON_KATANA_LIVE_OUTPUT", "").strip()
    output_root = (
        Path(output_value).resolve()
        if output_value
        else REPOSITORY_ROOT / ".artifacts" / "live-katana"
    )

    return LiveConfig(
        project_name=_required_env("AYON_KATANA_LIVE_PROJECT"),
        folder_path=folder_path,
        task_name=_required_env("AYON_KATANA_LIVE_TASK"),
        applications=applications,
        suites=suites,
        output_root=output_root,
        existing_workfile=existing_workfile,
        timeout_seconds=timeout_seconds,
    )


def without_installed_katana_addon(value: str) -> str:
    """Remove installed AYON Katana addon paths from one path-list value."""
    output = []
    for item in value.split(os.pathsep):
        normalized = item.replace("\\", "/").casefold()
        if "/addons/katana_" in normalized:
            continue
        if item:
            output.append(item)
    return os.pathsep.join(output)


def prepare_environment(
    base: dict[str, str],
    application_name: str,
    output_dir: Path,
    result_path: Path,
    existing_workfile: Path | None,
) -> dict[str, str]:
    """Inject the current checkout and live-test metadata into a launch env."""
    env = os.environ.copy()
    env.update(base)

    client_root = REPOSITORY_ROOT / "client"
    resources = client_root / "ayon_katana" / "resources"
    python_path = without_installed_katana_addon(env.get("PYTHONPATH", ""))
    katana_resources = without_installed_katana_addon(env.get("KATANA_RESOURCES", ""))
    env["PYTHONPATH"] = os.pathsep.join(
        item for item in (str(client_root), python_path) if item
    )
    env["KATANA_RESOURCES"] = os.pathsep.join(
        item for item in (str(resources), katana_resources) if item
    )
    env["AYON_KATANA_LIVE_ROOT"] = str(REPOSITORY_ROOT)
    env["AYON_KATANA_LIVE_APPLICATION"] = application_name
    env["AYON_KATANA_LIVE_OUT"] = str(output_dir)
    env["AYON_KATANA_LIVE_RESULT"] = str(result_path)
    if existing_workfile is not None:
        env["AYON_KATANA_LIVE_WORKFILE"] = str(existing_workfile)
    env.pop("SSLKEYLOGFILE", None)
    return env


def _suite_script(suite: str) -> Path:
    """Return the Katana-side script for one suite."""
    return Path(__file__).with_name(
        {
            "native": "native_contracts.py",
            "integration": "integration_smoke.py",
            "existing": "existing_workfile.py",
        }[suite]
    )


def _run_suite(
    executable: Path,
    application_name: str,
    suite: str,
    base_env: dict[str, str],
    config: LiveConfig,
) -> dict:
    """Run one suite in one real Katana process and return its JSON result."""
    version_name = application_name.split("/", 1)[-1]
    output_dir = config.output_root / version_name / suite
    output_dir.mkdir(parents=True, exist_ok=True)
    result_path = output_dir / "result.json"
    log_path = output_dir / "katana.log"
    result_path.unlink(missing_ok=True)

    env = prepare_environment(
        base_env,
        application_name,
        output_dir,
        result_path,
        config.existing_workfile,
    )
    try:
        with log_path.open("w", encoding="utf-8") as log:
            process = subprocess.run(
                [str(executable), "--script", str(_suite_script(suite))],
                cwd=REPOSITORY_ROOT,
                env=env,
                stdout=log,
                stderr=subprocess.STDOUT,
                timeout=config.timeout_seconds,
                check=False,
            )
    except subprocess.TimeoutExpired:
        return {
            "success": False,
            "error_type": "TimeoutExpired",
            "error": (
                f"Katana live suite exceeded {config.timeout_seconds} seconds and "
                "was terminated."
            ),
            "return_code": None,
            "log": log_path.relative_to(config.output_root).as_posix(),
        }

    if result_path.is_file():
        try:
            result = json.loads(result_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            result = {
                "success": False,
                "error_type": type(exc).__name__,
                "error": f"Could not read live-test result payload: {exc}",
            }
    else:
        result = {
            "success": False,
            "error_type": "MissingResult",
            "error": "Katana exited without writing a live-test result payload.",
        }
    result["return_code"] = process.returncode
    result["log"] = log_path.relative_to(config.output_root).as_posix()
    return result


def _application_managers():
    """Return the configured AYON Applications addon and manager."""
    from ayon_core.addon import AddonsManager

    applications_addon = AddonsManager()["applications"]
    return applications_addon, applications_addon.get_applications_manager()


def _resolve_application_run(
    config: LiveConfig,
    application_name: str,
    applications_addon,
    applications_manager,
) -> tuple[Path, dict]:
    """Resolve one configured Katana executable and AYON launch environment."""
    application = applications_manager.applications.get(application_name)
    if application is None:
        raise RuntimeError(f"AYON application is not configured: {application_name}")
    executable = application.find_executable()
    if executable is None:
        raise RuntimeError(f"Katana executable was not found: {application_name}")
    base_env = applications_addon.get_app_environments_for_context(
        config.project_name,
        config.folder_path,
        config.task_name,
        application_name,
    )
    return Path(str(executable)), base_env


def build_public_summary(
    overall: dict[str, dict[str, dict]],
) -> dict[str, dict[str, dict]]:
    """Return a path- and traceback-free summary suitable for public CI artifacts."""
    allowed_keys = {
        "success",
        "return_code",
        "checks",
        "coverage_gaps",
        "error_type",
    }
    return {
        application_name: {
            suite: {key: value for key, value in result.items() if key in allowed_keys}
            for suite, result in suite_results.items()
        }
        for application_name, suite_results in overall.items()
    }


def _setup_failure(exc: Exception) -> dict[str, object]:
    """Return one structured application-setup failure."""
    return {
        "success": False,
        "return_code": None,
        "error_type": type(exc).__name__,
        "error": str(exc),
    }


def main() -> None:
    """Run requested beta live suites and always emit aggregate summaries."""
    config = load_config()
    config.output_root.mkdir(parents=True, exist_ok=True)

    overall: dict[str, dict[str, dict]] = {}
    failed = False
    try:
        applications_addon, applications_manager = _application_managers()
    except Exception as exc:
        failed = True
        for application_name in config.applications:
            overall[application_name] = {"setup": _setup_failure(exc)}
    else:
        for application_name in config.applications:
            application_results = overall.setdefault(application_name, {})
            try:
                executable, base_env = _resolve_application_run(
                    config,
                    application_name,
                    applications_addon,
                    applications_manager,
                )
            except Exception as exc:
                application_results["setup"] = _setup_failure(exc)
                failed = True
                continue

            for suite in config.suites:
                result = _run_suite(
                    executable,
                    application_name,
                    suite,
                    base_env,
                    config,
                )
                application_results[suite] = result
                if result.get("return_code") != 0 or not result.get("success"):
                    failed = True

    summary = json.dumps(overall, indent=2, sort_keys=True)
    public_summary = json.dumps(
        build_public_summary(overall),
        indent=2,
        sort_keys=True,
    )
    (config.output_root / "summary.json").write_text(summary, encoding="utf-8")
    (config.output_root / "public-summary.json").write_text(
        public_summary,
        encoding="utf-8",
    )
    print(summary)
    raise SystemExit(1 if failed else 0)


if __name__ == "__main__":
    main()
