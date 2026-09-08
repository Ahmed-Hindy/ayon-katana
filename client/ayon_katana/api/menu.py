"""AYON menu integration for Katana's graphical interface."""

import logging
from typing import Callable

from ayon_core.tools.utils import host_tools
from Katana import UI4
from qtpy import QtWidgets

log = logging.getLogger("ayon_katana.menu")

_MENU_TITLE = "AYON"
_main_window = None
_menu_bar = None
_menu = None


def get_main_window():
    """Return Katana's main window when running in UI mode."""
    return UI4.App.MainWindow.GetMainWindow()


def _add_action(menu, label: str, callback: Callable[[], None]):
    """Add a menu action without exposing Qt's checked argument."""
    action = menu.addAction(label)
    action.triggered.connect(lambda _checked=False: callback())
    return action


def _version_up_workfile() -> None:
    """Save the next workfile version through AYON Core."""
    from ayon_core.pipeline.workfile import save_next_version

    save_next_version()


def _version_up_enabled() -> bool:
    """Return the Core AYON-menu setting for workfile versioning."""
    try:
        from ayon_core.pipeline.context_tools import get_current_project_settings

        settings = get_current_project_settings()
        return bool(
            settings.get("core", {})
            .get("tools", {})
            .get("ayon_menu", {})
            .get("version_up_current_workfile", False)
        )
    except Exception:
        log.debug(
            "Version Up Workfile is unavailable without project settings.",
            exc_info=True,
        )
        return False


def _set_frame_range() -> None:
    """Apply the current AYON task frame range to Katana."""
    from .context import apply_current_frame_range

    apply_current_frame_range()


def _clear_usd_resolver_cache() -> None:
    """Clear the optional AYON USD resolver and flush native stages."""
    from .usd import clear_resolver_cache

    clear_resolver_cache()


def _normalized_action_text(action) -> str:
    """Return a menu action label without mnemonic markers."""
    return action.text().replace("&", "").strip()


def get_menu_bar(main_window=None):
    """Return Katana's existing native menu bar.

    Katana does not register its visible menu bar through
    ``QMainWindow.setMenuBar``. Calling ``QMainWindow.menuBar`` therefore
    creates a second menu bar above Katana's own menu row.
    """
    main_window = main_window or get_main_window()
    if main_window is None:
        return None

    required_actions = {"File", "Edit", "Help"}
    for menu_bar in main_window.findChildren(QtWidgets.QMenuBar):
        action_labels = {
            _normalized_action_text(action) for action in menu_bar.actions()
        }
        if required_actions.issubset(action_labels):
            return menu_bar
    return None


def _find_menu_action(menu_bar, label: str):
    """Return a top-level menu action by its visible label."""
    for action in menu_bar.actions():
        if _normalized_action_text(action) == label:
            return action
    return None


def _find_existing_menu(menu_bar):
    """Return an existing AYON menu from a Qt menu bar."""
    action = _find_menu_action(menu_bar, _MENU_TITLE)
    return action.menu() if action is not None else None


def install_menu() -> bool:
    """Install the AYON menu in Katana.

    Returns:
        ``True`` when the menu is available, otherwise ``False``.
    """
    global _main_window, _menu_bar, _menu

    main_window = get_main_window()
    if main_window is None:
        log.debug("Katana main window is unavailable; skipping AYON menu.")
        return False

    menu_bar = get_menu_bar(main_window)
    if menu_bar is None:
        log.debug("Katana native menu bar is unavailable; skipping AYON menu.")
        return False

    _main_window = main_window
    _menu_bar = menu_bar
    existing_menu = _find_existing_menu(menu_bar)
    if existing_menu is not None:
        _menu = existing_menu
        return True

    menu = QtWidgets.QMenu(_MENU_TITLE, menu_bar)
    help_action = _find_menu_action(menu_bar, "Help")
    if help_action is not None:
        menu_bar.insertMenu(help_action, menu)
    else:
        menu_bar.addMenu(menu)
    _add_action(
        menu,
        "Create...",
        lambda: host_tools.show_publisher(parent=main_window, tab="create"),
    )
    _add_action(
        menu,
        "Load...",
        lambda: host_tools.show_loader(parent=main_window, use_context=True),
    )
    _add_action(
        menu,
        "Publish...",
        lambda: host_tools.show_publisher(parent=main_window, tab="publish"),
    )
    _add_action(
        menu,
        "Manage...",
        lambda: host_tools.show_scene_inventory(parent=main_window),
    )

    menu.addSeparator()
    _add_action(
        menu,
        "Workfiles...",
        lambda: host_tools.show_workfiles(parent=main_window),
    )
    version_up_action = _add_action(
        menu,
        "Version Up Workfile",
        _version_up_workfile,
    )
    version_up_action.setEnabled(_version_up_enabled())
    _add_action(menu, "Set Frame Range", _set_frame_range)
    _add_action(menu, "Clear USD Resolver Cache", _clear_usd_resolver_cache)

    menu.addSeparator()
    _add_action(
        menu,
        "Experimental Tools...",
        lambda: host_tools.show_experimental_tools_dialog(parent=main_window),
    )

    from . import workfile_template_builder

    builder_menu = menu.addMenu("Workfile Builder")
    _add_action(
        builder_menu,
        "Build Template",
        workfile_template_builder.build_workfile_template,
    )
    _add_action(
        builder_menu,
        "Update Template",
        workfile_template_builder.update_workfile_template,
    )
    builder_menu.addSeparator()
    _add_action(
        builder_menu,
        "Open Template",
        workfile_template_builder.open_workfile_template,
    )
    _add_action(
        builder_menu,
        "Create Placeholder...",
        workfile_template_builder.create_placeholder,
    )
    _add_action(
        builder_menu,
        "Update Selected Placeholder...",
        workfile_template_builder.update_placeholder,
    )

    _menu = menu
    log.info("Installed AYON menu in Katana.")
    return True


def uninstall_menu() -> None:
    """Remove the AYON menu from Katana when present."""
    global _main_window, _menu_bar, _menu

    main_window = _main_window or get_main_window()
    menu_bar = _menu_bar or get_menu_bar(main_window)
    menu = _menu or (_find_existing_menu(menu_bar) if menu_bar is not None else None)
    if menu is None:
        _main_window = None
        _menu_bar = None
        return

    try:
        if menu_bar is not None:
            menu_bar.removeAction(menu.menuAction())
        menu.deleteLater()
    except RuntimeError:
        log.debug("Katana already deleted the AYON menu during UI teardown.")
    _menu = None
    _menu_bar = None
    _main_window = None
