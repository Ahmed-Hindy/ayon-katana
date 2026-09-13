"""Real Katana UI probe for AYON menu lifecycle acceptance."""

from Katana import Callbacks


def _run_probe() -> None:
    """Validate the lifecycle-installed AYON menu in Katana's real UI."""
    import json
    import os
    import traceback
    from pathlib import Path

    def labels(actions):
        return [action.text().replace("&", "").strip() for action in actions]

    result_path = Path(os.environ["AYON_KATANA_LIVE_RESULT"])
    checks = [
        "AYON lifecycle installs one top-level menu in Katana UI",
        "repeated AYON menu installation remains idempotent",
        "expected AYON menu actions are available",
        "Workfile Builder submenu actions are available",
    ]
    coverage_gaps = [
        "Menu action dialogs are enumerated but not interactively exercised.",
    ]
    payload = {
        "success": False,
        "checks": checks,
        "coverage_gaps": coverage_gaps,
    }
    try:
        from ayon_katana.api import menu as ayon_menu

        main_window = ayon_menu.get_main_window()
        menu_bar = ayon_menu.get_menu_bar(main_window)
        if main_window is None or menu_bar is None:
            raise RuntimeError("Katana main window/native menu bar is unavailable.")

        before = labels(menu_bar.actions())
        before_count = before.count("AYON")
        if before_count != 1:
            raise RuntimeError(
                "Expected AYON lifecycle to install exactly one top-level menu "
                f"before the UI probe, found {before_count}."
            )

        first_install = ayon_menu.install_menu()
        second_install = ayon_menu.install_menu()
        after = labels(menu_bar.actions())
        ayon_actions = [
            action
            for action in menu_bar.actions()
            if action.text().replace("&", "").strip() == "AYON"
        ]
        if len(ayon_actions) != 1:
            raise RuntimeError(
                "Expected one AYON top-level menu after reinstall, found "
                f"{len(ayon_actions)}."
            )

        menu = ayon_actions[0].menu()
        if menu is None:
            raise RuntimeError("AYON top-level action has no menu.")
        menu_labels = labels(
            action for action in menu.actions() if not action.isSeparator()
        )
        expected = {
            "Create...",
            "Load...",
            "Publish...",
            "Manage...",
            "Workfiles...",
            "Version Up Workfile",
            "Set Frame Range",
            "Clear USD Resolver Cache",
            "Experimental Tools...",
            "Workfile Builder",
        }
        missing = sorted(expected.difference(menu_labels))
        if missing:
            raise RuntimeError(f"AYON menu is missing expected actions: {missing}")

        builder_action = next(
            action
            for action in menu.actions()
            if action.text().replace("&", "").strip() == "Workfile Builder"
        )
        builder_menu = builder_action.menu()
        if builder_menu is None:
            raise RuntimeError("Workfile Builder action has no submenu.")
        builder_labels = labels(
            action for action in builder_menu.actions() if not action.isSeparator()
        )
        expected_builder = {
            "Build Template",
            "Update Template",
            "Open Template",
            "Create Placeholder...",
            "Update Selected Placeholder...",
        }
        missing_builder = sorted(expected_builder.difference(builder_labels))
        if missing_builder:
            raise RuntimeError(
                f"Workfile Builder menu is missing expected actions: {missing_builder}"
            )

        payload.update(
            {
                "success": True,
                "observations": {
                    "ayon_menu_count_before": before_count,
                    "ayon_menu_count_after": after.count("AYON"),
                    "first_install": bool(first_install),
                    "second_install": bool(second_install),
                    "menu_labels": menu_labels,
                    "builder_labels": builder_labels,
                },
            }
        )
    except Exception as exc:
        payload.update(
            {
                "error_type": type(exc).__name__,
                "error": str(exc),
                "traceback": traceback.format_exc(),
            }
        )
    finally:
        result_path.parent.mkdir(parents=True, exist_ok=True)
        result_path.write_text(
            json.dumps(payload, indent=2, sort_keys=True),
            encoding="utf-8",
        )


def _on_startup_complete(*_args, _run=_run_probe, **_kwargs) -> None:
    """Inspect the UI after AYON's two-second deferred menu installation."""
    from qtpy import QtCore, QtWidgets

    app = QtWidgets.QApplication.instance()
    if app is None:
        _run()
        return
    timer = QtCore.QTimer(app)
    timer.setObjectName("AYONLiveUiProbeTimer")
    timer.setSingleShot(True)
    timer.timeout.connect(_run)
    timer.start(3000)


Callbacks.addCallback(Callbacks.Type.onStartupComplete, _on_startup_complete)
