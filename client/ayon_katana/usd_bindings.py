"""Expose Katana's USD bindings through the standard ``pxr`` namespace."""

from __future__ import annotations

import logging
import sys
from importlib import import_module

log = logging.getLogger("ayon_katana.usd_bindings")

USD_SUBMODULES = (
    "Ar",
    "Kind",
    "Sdf",
    "Usd",
    "UsdGeom",
    "UsdShade",
    "UsdUtils",
)


class UsdBindingConflictError(RuntimeError):
    """Raised when another USD build already owns the ``pxr`` namespace."""


def install_usd_bindings() -> str | None:
    """Expose Katana's bundled ``fnpxr`` binding as ``pxr``.

    Katana ships Foundry's namespaced ``fnpxr`` package, while AYON's shared
    USD publishing code follows the standard Pixar ``pxr`` import contract.
    This function imports Katana's required modules first and then publishes an
    atomic set of aliases in :mod:`sys.modules`. It never selects an external
    USD build.

    Binding import failures are intentionally non-fatal so Katana can still
    start and use non-USD AYON features. USD tools will report their native
    import error when invoked. A different binding already loaded as ``pxr``
    is a fatal configuration conflict because mixing USD builds in one Katana
    process is unsafe.

    Returns:
        ``"fnpxr"`` when the aliases were installed, or ``None`` when
        Katana's binding could not be initialized.

    Raises:
        UsdBindingConflictError: A different USD binding already owns one of
            the required ``pxr`` module names.
    """
    try:
        root_module = import_module("fnpxr")
        submodules = {name: import_module(f"fnpxr.{name}") for name in USD_SUBMODULES}
    except (ImportError, OSError) as exc:
        log.warning("Katana's fnpxr package could not be initialized: %s", exc)
        return None

    expected_modules = {"pxr": root_module}
    expected_modules.update(
        {f"pxr.{name}": module for name, module in submodules.items()}
    )
    conflicting_modules = [
        name
        for name, expected_module in expected_modules.items()
        if (loaded_module := sys.modules.get(name)) is not None
        and loaded_module is not expected_module
    ]
    if conflicting_modules:
        names = ", ".join(sorted(conflicting_modules))
        raise UsdBindingConflictError(
            "Katana cannot initialize its bundled fnpxr binding because a "
            f"different USD build already owns: {names}. Remove the external "
            "pxr package from Katana's environment."
        )

    sys.modules["pxr"] = root_module
    for name, module in submodules.items():
        setattr(root_module, name, module)
        sys.modules[f"pxr.{name}"] = module

    log.debug("Exposed Katana's fnpxr package as pxr.")
    return "fnpxr"
