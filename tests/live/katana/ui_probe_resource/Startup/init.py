"""Real Katana UI probe for AYON menu lifecycle acceptance."""

from Katana import Callbacks


def _run_probe() -> None:
    """Validate the lifecycle-installed AYON menu in Katana's real UI."""
    import json
    import os
    import traceback
    from contextlib import suppress
    from pathlib import Path

    from qtpy import QtWidgets

    def labels(actions):
        return [action.text().replace("&", "").strip() for action in actions]

    result_path = Path(os.environ["AYON_KATANA_LIVE_RESULT"])
    checks = []
    coverage_gaps = [
        "Scene-mutating menu actions are not triggered by UI smoke.",
    ]
    payload = {
        "success": False,
        "checks": checks,
        "coverage_gaps": coverage_gaps,
    }
    tool_windows = []
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
        checks.append("AYON lifecycle installs one top-level menu in Katana UI")

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
        checks.append("repeated AYON menu installation remains idempotent")

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
        checks.append("expected AYON menu actions are available")

        version_up_action = next(
            action
            for action in menu.actions()
            if action.text().replace("&", "").strip() == "Version Up Workfile"
        )
        version_up_expected = ayon_menu._version_up_enabled()
        version_up_enabled = bool(version_up_action.isEnabled())
        if version_up_enabled != version_up_expected:
            raise RuntimeError(
                "Version Up Workfile enabled state does not match AYON settings."
            )
        checks.append("Version Up Workfile menu state matches AYON project settings")

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
        checks.append("Workfile Builder submenu actions are available")

        from ayon_core.tools.utils import host_tools

        def show_tool(name, callback):
            widget = callback()
            if widget is None:
                raise RuntimeError(f"AYON UI tool returned no widget: {name}")
            QtWidgets.QApplication.processEvents()
            if not widget.isVisible():
                raise RuntimeError(f"AYON UI tool is not visible after show: {name}")
            tool_windows.append(widget)
            return type(widget).__name__

        tool_classes = {
            "publisher_create": show_tool(
                "publisher create",
                lambda: host_tools.show_publisher(parent=main_window, tab="create"),
            ),
            "loader": show_tool(
                "loader",
                lambda: host_tools.show_loader(parent=main_window, use_context=True),
            ),
            "scene_inventory": show_tool(
                "scene inventory",
                lambda: host_tools.show_scene_inventory(parent=main_window),
            ),
            "workfiles": show_tool(
                "workfiles",
                lambda: host_tools.show_workfiles(parent=main_window),
            ),
            "experimental_tools": show_tool(
                "experimental tools",
                lambda: host_tools.show_experimental_tools_dialog(parent=main_window),
            ),
        }
        publisher_publish = host_tools.show_publisher(parent=main_window, tab="publish")
        if publisher_publish is None:
            raise RuntimeError("AYON Publisher returned no widget for publish tab.")
        QtWidgets.QApplication.processEvents()
        if not publisher_publish.isVisible():
            raise RuntimeError("AYON Publisher is not visible on publish tab.")
        tool_classes["publisher_publish"] = type(publisher_publish).__name__
        checks.append("safe AYON host-tool windows open successfully in Katana UI")

        from ayon_katana.api import thumbnail as thumbnail_api

        viewer_widget, viewer_reason = thumbnail_api.select_viewer_widget()
        viewer_capture = {
            "reason": viewer_reason,
            "captured": False,
        }
        if viewer_widget is None:
            coverage_gaps.append(
                f"Viewer thumbnail capture unavailable: {viewer_reason}."
            )
        else:
            thumbnail_path = thumbnail_api.capture_viewer_thumbnail(viewer_widget)
            try:
                thumbnail_file = Path(thumbnail_path)
                thumbnail_size = thumbnail_file.stat().st_size
                if thumbnail_size < 1:
                    raise RuntimeError(
                        "Viewer thumbnail capture produced an empty PNG."
                    )
                checks.append("visible Katana Viewer thumbnail capture produces a PNG")
                viewer_capture.update(
                    {
                        "captured": True,
                        "bytes": thumbnail_size,
                    }
                )
            finally:
                with suppress(OSError):
                    Path(thumbnail_path).unlink()

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
                    "version_up_enabled": version_up_enabled,
                    "tool_classes": tool_classes,
                    "viewer_capture": viewer_capture,
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
        for widget in reversed(tool_windows):
            with suppress(RuntimeError):
                widget.close()
        QtWidgets.QApplication.processEvents()
        result_path.parent.mkdir(parents=True, exist_ok=True)
        staging_path = result_path.with_name(f".{result_path.name}.tmp")
        staging_path.write_text(
            json.dumps(payload, indent=2, sort_keys=True),
            encoding="utf-8",
        )
        staging_path.replace(result_path)


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
