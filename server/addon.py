"""AYON Server addon definition for Katana."""

from typing import Type

from ayon_server.addons import BaseServerAddon

from .settings import DEFAULT_VALUES, KatanaSettings


class KatanaAddon(BaseServerAddon):
    """Expose Katana settings and client code to AYON Server."""

    settings_model: Type[KatanaSettings] = KatanaSettings

    async def get_default_settings(self):
        """Return validated default Katana settings."""
        settings_model = self.get_settings_model()
        return settings_model(**DEFAULT_VALUES)
