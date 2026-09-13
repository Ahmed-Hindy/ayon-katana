"""Ephemeral keyring backend for headless live-test containers.

The backend exposes only the Kitsu credentials already injected into the
container environment by the authenticated Windows AYON launcher. It never
persists secrets to disk and intentionally rejects writes.
"""

from __future__ import annotations

import os

from keyring.backend import KeyringBackend
from keyring.errors import PasswordDeleteError, PasswordSetError


class EnvironmentKeyring(KeyringBackend):
    """Read Kitsu credentials from inherited environment variables only."""

    priority = 1

    def get_password(self, service: str, username: str) -> str | None:
        """Return one supported credential without persisting it."""
        if service != "AYON/kitsu_user":
            return None
        if username == "login":
            return os.environ.get("KITSU_LOGIN")
        if username == "password":
            return os.environ.get("KITSU_PWD")
        return None

    def set_password(self, service: str, username: str, password: str) -> None:
        """Reject writes because live-test credentials are inherited only."""
        raise PasswordSetError("Headless live-test keyring is read-only.")

    def delete_password(self, service: str, username: str) -> None:
        """Reject deletes because no credential is persisted in the container."""
        raise PasswordDeleteError("Headless live-test keyring is read-only.")
