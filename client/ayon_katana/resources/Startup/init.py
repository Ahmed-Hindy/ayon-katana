"""AYON startup script for Katana."""


def _install_ayon() -> None:
    """Initialize Katana compatibility before installing the AYON host."""
    from ayon_katana.usd_bindings import install_usd_bindings

    install_usd_bindings()

    from ayon_core.pipeline import install_host

    from ayon_katana.api import KatanaHost

    print("Installing AYON for Katana...")
    install_host(KatanaHost())


_install_ayon()
