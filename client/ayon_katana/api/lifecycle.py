"""Host lifecycle operations for AYON Katana."""

import logging

from ayon_core.lib import emit_event
from ayon_core.pipeline.load import any_outdated_containers
from ayon_core.pipeline.workfile import should_open_workfiles_tool_on_launch

from . import context, startup, workfile_template_builder

log = logging.getLogger("ayon_katana.lifecycle")


def _get_main_window():
    """Return Katana's graphical main window when one is available."""
    from Katana import UI4

    return UI4.App.MainWindow.GetMainWindow()


def _defer_call(callback, delay=0):
    """Run a UI callback after Katana returns to its event loop."""
    from qtpy import QtCore

    QtCore.QTimer.singleShot(delay, callback)


def _install_menu():
    from .menu import install_menu

    return install_menu()


def _uninstall_menu():
    from .menu import uninstall_menu

    uninstall_menu()


def _prompt_context_change(main_window, source_context: dict, target_context: dict):
    """Ask which scene data should follow a cross-context Save As.

    Args:
        main_window: Katana's graphical main window.
        source_context: Context embedded before Save As.
        target_context: Context selected in AYON Workfiles.

    Returns:
        Selected option values, or ``None`` when the artist cancels.
    """
    from ayon_core.lib import BoolDef, UILabelDef
    from ayon_core.tools.attribute_defs.dialog import AttributeDefinitionsDialog

    source_label = "{} > {}".format(
        source_context.get("folder_path") or "<no folder>",
        source_context.get("task_name") or "<no task>",
    )
    target_label = "{} > {}".format(
        target_context.get("folder_path") or "<no folder>",
        target_context.get("task_name") or "<no task>",
    )
    definitions = [
        UILabelDef(
            label=(
                "This workfile is being saved into a different AYON context.\n\n"
                f"From: {source_label}\nTo: {target_label}\n\n"
                "Choose which Katana scene data should follow the new context."
            )
        ),
        BoolDef(
            "frame_range",
            label="Frame Range",
            tooltip="Reset the Katana project range from the target task.",
            default=True,
        ),
        BoolDef(
            "instances",
            label="Publish instances",
            tooltip="Update persisted instance Folder and Task metadata.",
            default=True,
        ),
    ]
    dialog = AttributeDefinitionsDialog(
        definitions,
        title="Saving to a different AYON context",
        submit_label="Update and Save",
        parent=main_window,
    )
    try:
        if not dialog.exec_():
            return None
        return dialog.get_values()
    finally:
        dialog.deleteLater()


class LifecycleController:
    """Apply AYON lifecycle behavior from Katana callbacks."""

    def __init__(self, host):
        self._host = host
        self._outdated_content_pending = False
        self._pending_workfile_save = None

    def install(self):
        """Install UI integration when Katana already has a main window."""
        if _get_main_window() is not None:
            self._defer_menu_install()

    def uninstall(self):
        """Remove the AYON menu owned by this host."""
        self._outdated_content_pending = False
        self._pending_workfile_save = None
        _uninstall_menu()

    def on_startup_complete(self):
        """Open the requested scene, then emit init after native startup."""
        had_requested_workfile = startup.has_requested_workfile()
        opened_workfile = startup.open_requested_workfile()
        emit_event("init")
        self._defer_menu_install()
        if not had_requested_workfile and opened_workfile is None:
            self._trigger_workfile_builder_on_app_launch()
        self._open_workfiles_on_startup()
        if self._outdated_content_pending:
            self._outdated_content_pending = False
            self._show_outdated_content_popup()

    def on_new(self):
        """Initialize embedded context and project timing for a new scene."""
        emit_event("new")
        context.apply_context_settings(self._host)

    def on_new_scene_loaded(self):
        """Evaluate the Core new-file trigger after Katana creates a scene."""
        self._trigger_workfile_builder_on_new_file()

    def _has_complete_context(self) -> bool:
        """Return whether Workfile Builder profile matching has enough context."""
        current_context = context.get_current_context_data(self._host)
        return all(
            current_context.get(key)
            for key in ("project_name", "folder_path", "task_name")
        )

    def _trigger_workfile_builder_on_app_launch(self) -> None:
        """Build a launch template only for an unselected blank workfile."""
        if not self._has_complete_context():
            log.debug(
                "Skipping Workfile Builder launch trigger without a complete "
                "AYON context."
            )
            return
        workfile_template_builder.trigger_on_app_launch()

    def _trigger_workfile_builder_on_new_file(self) -> None:
        """Build a new-scene template only when its separate setting allows it."""
        if not self._has_complete_context():
            log.debug(
                "Skipping Workfile Builder new-file trigger without a complete "
                "AYON context."
            )
            return
        workfile_template_builder.trigger_on_new_file()

    def on_open(self):
        """Handle an existing Katana project after it opens."""
        emit_event("open")
        current_context = context.get_current_context_data(self._host)
        if not all(
            current_context.get(key)
            for key in ("project_name", "folder_path", "task_name")
        ):
            log.debug("Skipping opened-scene checks without an AYON context.")
            return
        context.log_fps_limitation()
        self._report_outdated_containers()

    def before_save(self):
        """Embed the current AYON context before Katana saves."""
        self._pending_workfile_save = None
        context.update_embedded_context(self._host)
        emit_event("before.save")

    def on_save(self):
        """Emit the AYON save event after Katana saves."""
        self._pending_workfile_save = None
        emit_event("save")

    def on_workfile_save_before(self, event=None):
        """Remember AYON Workfiles Save As context until ``taskChanged``.

        Args:
            event: AYON event containing the target workfile context.
        """
        event_data = getattr(event, "data", event)
        if not isinstance(event_data, dict):
            event_data = {}
        self._pending_workfile_save = {
            "source": context.get_current_context_data(self._host),
            "target": dict(event_data),
        }

    def on_task_changed(self, event=None):
        """Handle AYON task changes and cross-context Save As updates."""
        event_data = getattr(event, "data", event)
        if not isinstance(event_data, dict):
            event_data = None

        pending_save = self._pending_workfile_save
        self._pending_workfile_save = None
        if pending_save is not None:
            target_context = context.get_current_context_data(
                self._host,
                event_data or pending_save["target"],
            )
            source_context = pending_save["source"]
            context.update_embedded_context(self._host, target_context)
            changed_keys = ("project_name", "folder_path", "task_name")
            changed = any(
                source_context.get(key) != target_context.get(key)
                for key in changed_keys
            )
            if not changed:
                return

            main_window = _get_main_window()
            if main_window is None:
                log.info("Skipping cross-context Save As prompt in headless Katana.")
                return

            options = _prompt_context_change(
                main_window,
                source_context,
                target_context,
            )
            if options is None:
                log.info("Cross-context Save As scene updates were cancelled.")
                return
            if options.get("frame_range"):
                context.apply_current_frame_range()
            if options.get("instances"):
                folder_path = target_context.get("folder_path")
                task_name = target_context.get("task_name")
                if folder_path and task_name:
                    updated = context.update_instance_context_metadata(
                        folder_path,
                        task_name,
                    )
                    log.info(
                        "Updated %s Katana publish instances for Save As.",
                        updated,
                    )
            return

        context.apply_context_settings(self._host, event_data)

    def _defer_menu_install(self):
        if _get_main_window() is None:
            return

        def _install_if_active():
            if not self._host._has_been_setup:
                return
            try:
                _install_menu()
            except Exception:
                log.exception("Could not install the AYON Katana menu.")

        _defer_call(_install_if_active, delay=2000)

    def _open_workfiles_on_startup(self):
        """Open Workfiles only when the maintained Core profile enables it."""
        current_context = context.get_current_context_data(self._host)
        project_name = current_context.get("project_name")
        task_name = current_context.get("task_name")
        if not project_name or not task_name:
            log.debug("Skipping Workfiles startup without a complete AYON context.")
            return

        try:
            task_type = context.get_current_task_type()
            should_open = should_open_workfiles_tool_on_launch(
                project_name,
                self._host.name,
                task_name,
                task_type,
            )
        except Exception:
            log.exception("Could not evaluate the AYON Workfiles startup profile.")
            return

        if should_open:
            self._run_in_ui(self._show_workfiles)

    def _report_outdated_containers(self):
        """Warn about outdated content and offer Scene Inventory in the UI."""
        try:
            has_outdated_containers = any_outdated_containers()
        except Exception:
            log.exception("Could not check Katana containers for outdated content.")
            return

        if not has_outdated_containers:
            return

        log.warning("Katana scene has outdated content.")
        if not self._show_outdated_content_popup():
            self._outdated_content_pending = True

    def _show_outdated_content_popup(self):
        """Defer the outdated-content popup until Katana has a main window."""
        return self._run_in_ui(self._show_outdated_popup)

    def _run_in_ui(self, callback):
        """Defer a UI action, or leave headless sessions untouched."""
        main_window = _get_main_window()
        if main_window is None:
            return False

        def _invoke():
            if self._host._has_been_setup:
                callback(main_window)

        _defer_call(_invoke)
        return True

    @staticmethod
    def _show_workfiles(main_window):
        from ayon_core.tools.utils import host_tools

        host_tools.show_workfiles(parent=main_window)

    @staticmethod
    def _show_outdated_popup(main_window):
        from ayon_core.tools.utils import SimplePopup, host_tools

        popup = SimplePopup(parent=main_window)
        popup.setWindowTitle("Katana scene has outdated content")
        popup.set_message("There are outdated containers in your Katana scene.")
        popup.set_button_text("Show Scene Inventory")
        popup.on_clicked.connect(
            lambda: host_tools.show_scene_inventory(parent=main_window)
        )
        popup.show()
