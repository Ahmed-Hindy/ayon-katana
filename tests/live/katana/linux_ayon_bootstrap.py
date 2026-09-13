"""Launch official Linux AYON/Katana from authenticated Windows AYON.

Windows AYON resolves the user's existing AYON and Kitsu credentials from its
normal secure stores. The helper forwards those secrets to Docker only through
inherited environment variables. Linux then follows AYON's normal server-driven
bootstrap and distribution path for the active staging bundle.
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_IMAGE = "ayon-katana/katana9-rocky:ayon-1.6.0"
DEFAULT_LICENSE_SERVER = "4101@host.docker.internal"
DEFAULT_APPLICATION = "katana/9.0v1"
DEFAULT_SUITE = "native"
STATE_VOLUME = "ayon-katana-linux-ayon-official-state"
DEFAULT_OUTPUT_DIRECTORY = REPOSITORY_ROOT / ".artifacts" / "live-katana-linux"


def _required_env(name: str) -> str:
    """Return one required environment value without logging its contents."""
    value = os.environ.get(name, "").strip()
    if not value:
        raise RuntimeError(f"Required environment variable is not set: {name}")
    return value


def _container_server_url(value: str) -> str:
    """Map host loopback URLs to Docker Desktop's host gateway."""
    parsed = urlsplit(value)
    if parsed.hostname not in {"localhost", "127.0.0.1", "::1"}:
        return value

    host = "host.docker.internal"
    if parsed.port is not None:
        host = f"{host}:{parsed.port}"
    return urlunsplit((parsed.scheme, host, parsed.path, parsed.query, parsed.fragment))


def _load_kitsu_credentials() -> tuple[str, str]:
    """Read the user's existing Kitsu credentials from Windows AYON keyring."""
    from ayon_kitsu.credentials import load_credentials

    login, password = load_credentials()
    if not login or not password:
        raise RuntimeError(
            "Kitsu credentials are not available in the Windows AYON secure registry."
        )
    return str(login), str(password)


def _create_volume(name: str) -> None:
    """Ensure one persistent Docker volume exists."""
    subprocess.run(
        ["docker", "volume", "create", name],
        check=True,
        stdout=subprocess.DEVNULL,
    )


def main() -> None:
    """Run the live Katana runner through official Linux AYON distribution."""
    server_url = _container_server_url(_required_env("AYON_SERVER_URL"))
    _required_env("AYON_API_KEY")
    project_name = _required_env("AYON_KATANA_LIVE_PROJECT")
    folder_path = _required_env("AYON_KATANA_LIVE_FOLDER")
    task_name = _required_env("AYON_KATANA_LIVE_TASK")
    kitsu_login, kitsu_password = _load_kitsu_credentials()

    application = os.environ.get(
        "AYON_KATANA_LIVE_APPLICATIONS", DEFAULT_APPLICATION
    ).strip()
    suite = os.environ.get("AYON_KATANA_LIVE_SUITE", DEFAULT_SUITE).strip()
    image = os.environ.get("AYON_KATANA_LINUX_AYON_IMAGE", DEFAULT_IMAGE).strip()
    license_server = os.environ.get(
        "AYON_KATANA_LINUX_LICENSE_SERVER", DEFAULT_LICENSE_SERVER
    ).strip()

    _create_volume(STATE_VOLUME)
    output_value = os.environ.get("AYON_KATANA_LINUX_OUTPUT", "").strip()
    output_directory = (
        Path(output_value).resolve() if output_value else DEFAULT_OUTPUT_DIRECTORY
    )
    output_directory.mkdir(parents=True, exist_ok=True)

    container_env = os.environ.copy()
    container_env.update(
        {
            "AYON_SERVER_URL": server_url,
            "foundry_LICENSE": license_server,
            "KITSU_LOGIN": kitsu_login,
            "KITSU_PWD": kitsu_password,
            "PYTHON_KEYRING_BACKEND": "headless_keyring.EnvironmentKeyring",
            "PYTHONPATH": "/workspace/tests/live/katana",
            "AYON_KATANA_LIVE_PROJECT": project_name,
            "AYON_KATANA_LIVE_FOLDER": folder_path,
            "AYON_KATANA_LIVE_TASK": task_name,
            "AYON_KATANA_LIVE_APPLICATIONS": application,
            "AYON_KATANA_LIVE_SUITE": suite,
            "AYON_KATANA_LIVE_EXECUTABLE": "/opt/Katana9.0v1/bin/katanaBin",
            "AYON_KATANA_LIVE_OUTPUT": "/output",
        }
    )

    inherited_names = (
        "AYON_SERVER_URL",
        "AYON_API_KEY",
        "foundry_LICENSE",
        "KITSU_LOGIN",
        "KITSU_PWD",
        "PYTHON_KEYRING_BACKEND",
        "PYTHONPATH",
        "AYON_KATANA_LIVE_PROJECT",
        "AYON_KATANA_LIVE_FOLDER",
        "AYON_KATANA_LIVE_TASK",
        "AYON_KATANA_LIVE_APPLICATIONS",
        "AYON_KATANA_LIVE_SUITE",
        "AYON_KATANA_LIVE_EXECUTABLE",
        "AYON_KATANA_LIVE_OUTPUT",
    )
    command = [
        "docker",
        "run",
        "--rm",
        "--add-host",
        "host.docker.internal:host-gateway",
    ]
    for name in inherited_names:
        command.extend(("-e", name))
    command.extend(
        (
            "-e",
            "AYON_LAUNCHER_STORAGE_DIR=/state",
            "-e",
            "AYON_LAUNCHER_LOCAL_DIR=/state/local",
            "-v",
            f"{STATE_VOLUME}:/state",
            "-v",
            f"{output_directory}:/output",
            "-v",
            f"{REPOSITORY_ROOT}:/workspace:ro",
            image,
            "/opt/ayon/ayon",
            "--headless",
            "--use-staging",
            "run",
            "/workspace/tests/live/katana/run.py",
        )
    )
    completed = subprocess.run(command, env=container_env, check=False)
    raise SystemExit(completed.returncode)


if __name__ == "__main__":
    main()
