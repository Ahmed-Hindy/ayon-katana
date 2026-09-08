"""Katana callback lifecycle for the AYON host."""

import logging

from Katana import Callbacks

log = logging.getLogger("ayon_katana")


class CallbackManager:
    """Install and remove Katana callbacks without duplicates."""

    def __init__(self, lifecycle):
        self._lifecycle = lifecycle
        self._registered_callbacks = []
        self._new_scene_pending = False

    def install(self):
        """Register each supported Katana callback once."""
        if self._registered_callbacks:
            return
        self._register_optional("onStartupComplete", self._on_startup_complete)
        self._register_optional("onSceneAboutToLoad", self._on_scene_about_to_load)
        self._register_optional("onSceneLoad", self._on_scene_load)
        self._register_optional("onSceneAboutToSave", self._on_scene_about_to_save)
        self._register_optional("onSceneSave", self._on_scene_save)
        self._register_optional("onNewScene", self._on_new_scene)

    def uninstall(self):
        """Remove all callbacks registered by this manager."""
        for callback_type, callback in reversed(self._registered_callbacks):
            try:
                Callbacks.delCallback(callback_type, callback)
            except (RuntimeError, ValueError):
                log.exception("Failed to remove Katana callback %r.", callback_type)
        self._registered_callbacks.clear()
        self._new_scene_pending = False

    def _register_optional(self, callback_type_name, callback):
        callback_type = getattr(Callbacks.Type, callback_type_name, None)
        if callback_type is None:
            log.debug("Katana callback type %s is unavailable.", callback_type_name)
            return
        Callbacks.addCallback(callback_type, callback)
        self._registered_callbacks.append((callback_type, callback))

    def _on_startup_complete(self, *_args, **_kwargs):
        self._lifecycle.on_startup_complete()

    def _on_scene_about_to_load(self, *_args, **_kwargs):
        self._new_scene_pending = False

    def _on_scene_load(self, *_args, **_kwargs):
        """Dispatch an open, except for the paired callback after ``New()``.

        Katana 8.0v1 and 9.0v1 both report the following sequences:

        - ``New()``: ``onSceneAboutToLoad``, ``onNewScene``, ``onSceneLoad``;
        - ``Load()``: ``onSceneAboutToLoad``, ``onSceneLoad``.

        The trailing load event after ``New()`` must not treat the new scene
        as an artist opening an existing workfile.
        """
        if self._new_scene_pending:
            self._new_scene_pending = False
            self._lifecycle.on_new_scene_loaded()
            return
        self._lifecycle.on_open()

    def _on_scene_about_to_save(self, *_args, **_kwargs):
        self._lifecycle.before_save()

    def _on_scene_save(self, *_args, **_kwargs):
        self._lifecycle.on_save()

    def _on_new_scene(self, *_args, **_kwargs):
        self._new_scene_pending = True
        self._lifecycle.on_new()
