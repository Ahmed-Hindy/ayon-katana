"""Pipeline tools for AYON Katana integration."""

import importlib.util
import logging
import os

import pyblish.api
from ayon_core.host import HostBase, ILoadHost, IPublishHost, IWorkfileHost
from ayon_core.lib import register_event_callback
from ayon_core.pipeline import (
    deregister_creator_plugin_path,
    deregister_inventory_action_path,
    deregister_loader_plugin_path,
    deregister_workfile_build_plugin_path,
    register_creator_plugin_path,
    register_inventory_action_path,
    register_loader_plugin_path,
    register_workfile_build_plugin_path,
)

from ayon_katana import KATANA_HOST_DIR

from . import containers, lib, workio
from . import context as context_lib
from .callbacks import CallbackManager
from .lifecycle import LifecycleController

log = logging.getLogger("ayon_katana")

PLUGINS_DIR = os.path.join(KATANA_HOST_DIR, "plugins")
PUBLISH_PATH = os.path.join(PLUGINS_DIR, "publish")
LOAD_PATH = os.path.join(PLUGINS_DIR, "load")
CREATE_PATH = os.path.join(PLUGINS_DIR, "create")
INVENTORY_PATH = os.path.join(PLUGINS_DIR, "inventory")
WORKFILE_BUILD_PATH = os.path.join(PLUGINS_DIR, "workfile_build")
DEADLINE_PUBLISH_PATH = os.path.join(PLUGINS_DIR, "deadline")


class KatanaHost(HostBase, IWorkfileHost, ILoadHost, IPublishHost):
    """Implement AYON host interfaces for Katana."""

    name = "katana"

    def __init__(self):
        super().__init__()
        self._lifecycle = LifecycleController(self)
        self._callback_manager = CallbackManager(self._lifecycle)
        self._event_callbacks: list[object] = []
        self._deadline_plugins_registered = False
        self._has_been_setup = False

    def get_app_information(self):
        """Return the running Katana application's name and version."""
        import Katana
        from ayon_core.host import ApplicationInformation

        katana_version = getattr(Katana, "__version__", None)
        if not katana_version:
            katana_root = os.environ.get("KATANA_ROOT", "").rstrip("/\\")
            katana_root_name = katana_root.replace("\\", "/").rsplit("/", 1)[-1]
            if katana_root_name.startswith("Katana"):
                katana_version = katana_root_name.removeprefix("Katana")

        return ApplicationInformation(
            app_name="Katana",
            app_version=katana_version,
        )

    def maintained_selection(self):
        """Return a context manager that restores the Katana selection."""
        return lib.maintained_selection()

    def install(self):
        """Register Katana plugins, callbacks, and host services once."""
        if self._has_been_setup:
            return

        pyblish.api.register_host(self.name)
        pyblish.api.register_plugin_path(PUBLISH_PATH)
        if importlib.util.find_spec("ayon_deadline") is not None:
            pyblish.api.register_plugin_path(DEADLINE_PUBLISH_PATH)
            self._deadline_plugins_registered = True
        register_loader_plugin_path(LOAD_PATH)
        register_creator_plugin_path(CREATE_PATH)
        register_inventory_action_path(INVENTORY_PATH)
        register_workfile_build_plugin_path(WORKFILE_BUILD_PATH)
        self._lifecycle.install()
        self._callback_manager.install()
        self._event_callbacks.append(
            register_event_callback("taskChanged", self._lifecycle.on_task_changed)
        )
        self._event_callbacks.append(
            register_event_callback(
                "workfile.save.before",
                self._lifecycle.on_workfile_save_before,
            )
        )
        self._has_been_setup = True
        log.info("Installed AYON Katana host.")

    def uninstall(self):
        """Remove plugins, callbacks, and host services registered by AYON."""
        if not self._has_been_setup:
            return

        for event_callback in self._event_callbacks:
            event_callback.deregister()
        self._event_callbacks.clear()
        self._callback_manager.uninstall()
        self._lifecycle.uninstall()
        deregister_workfile_build_plugin_path(WORKFILE_BUILD_PATH)
        deregister_inventory_action_path(INVENTORY_PATH)
        deregister_creator_plugin_path(CREATE_PATH)
        deregister_loader_plugin_path(LOAD_PATH)
        if self._deadline_plugins_registered:
            pyblish.api.deregister_plugin_path(DEADLINE_PUBLISH_PATH)
            self._deadline_plugins_registered = False
        pyblish.api.deregister_plugin_path(PUBLISH_PATH)
        pyblish.api.deregister_host(self.name)
        self._has_been_setup = False
        log.info("Uninstalled AYON Katana host.")

    def workfile_has_unsaved_changes(self):
        """Return whether the current Katana project has unsaved changes."""
        return workio.workfile_has_unsaved_changes()

    def get_workfile_extensions(self):
        """Return workfile extensions supported by Katana."""
        return workio.get_workfile_extensions()

    def save_workfile(self, dst_path=None):
        """Save the current Katana project, optionally to a new path."""
        return workio.save_workfile(dst_path)

    def open_workfile(self, filepath):
        """Open a Katana project from a filesystem path."""
        return workio.open_workfile(filepath)

    def get_current_workfile(self):
        """Return the current Katana project path."""
        return workio.get_current_workfile()

    def get_containers(self):
        """Return containers found in the current Katana project."""
        return ls()

    def get_context_data(self):
        """Return AYON context data embedded in the current project."""
        return context_lib.get_context_data()

    def update_context_data(self, data, changes=None):
        """Persist AYON context data in the current Katana project."""
        context_lib.update_context_data(data, changes)


def containerise(name, namespace, context, loader=None, parent_node=None):
    """Bundle a Katana graph and imprint it with metadata.

    Containerisation enables tracking of version, author and origin for loaded
    products.

    Args:
        name: Name of the loaded product.
        namespace: Namespace under which to host the container.
        context: Loaded product context information.
        loader: Name of the loader used to produce the container.
        parent_node: Optional Katana parent node.

    Returns:
        Created Katana container Group.
    """
    return containers.containerise(
        name,
        namespace,
        context,
        loader=loader,
        parent_node=parent_node,
    )


def ls():
    """Yield AYON containers in the current Katana project."""
    return containers.ls()
