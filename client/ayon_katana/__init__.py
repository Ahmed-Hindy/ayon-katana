"""AYON integration for Foundry Katana."""

from .addon import KATANA_HOST_DIR, KatanaAddon
from .version import __version__

__all__ = (
    "__version__",
    "KATANA_HOST_DIR",
    "KatanaAddon",
)
