"""Administrator-authored Python placeholder for Katana Workfile Builder."""

from __future__ import annotations

from ayon_core.lib import NumberDef, TextDef
from ayon_core.lib.events import weakref_partial
from ayon_core.pipeline.workfile.workfile_template_builder import PlaceholderItem
from Katana import NodegraphAPI

from ayon_katana.api.workfile_template_builder import KatanaPlaceholderPlugin

EXAMPLE_SCRIPT = """
# This code is trusted administrator-authored Python and is not sandboxed.
placeholder_node = NodegraphAPI.GetNode(placeholder.scene_identifier)

if event is None:
    print(f"Populating {placeholder}")
elif event.topic == "template.depth_processed":
    print(f"Processed depth: {event.get('depth')}")
elif event.topic == "template.finished":
    print("Build finished.")
""".strip()


class KatanaPlaceholderScriptPlugin(KatanaPlaceholderPlugin):
    """Execute trusted Python during selected Workfile Builder phases.

    Scripts are configured by AYON administrators and execute with the same
    permissions as Katana. They are intentionally not a security sandbox and
    must never contain untrusted project or artist-provided code.
    """

    identifier = "katana.runscript"
    label = "Run Python Script (Unsandboxed)"

    def get_placeholder_options(self, options=None):
        """Return the script phase and ordering controls shown by Core."""
        options = options or {}
        return [
            NumberDef(
                "order",
                label="Order",
                default=options.get("order") or 0,
                decimals=0,
                minimum=0,
                maximum=999,
                tooltip=("Execution order from 0 to 999. Lower values run first."),
            ),
            TextDef(
                "prepare_script",
                label="Run at\nprepare",
                tooltip=("Trusted, unsandboxed Python executed before population."),
                multiline=True,
                default=options.get("prepare_script", ""),
            ),
            TextDef(
                "populate_script",
                label="Run at\npopulate",
                tooltip=("Trusted, unsandboxed Python executed at placeholder order."),
                multiline=True,
                default=options.get("populate_script", EXAMPLE_SCRIPT),
            ),
            TextDef(
                "depth_processed_script",
                label="Run after\ndepth\niteration",
                tooltip=(
                    "Trusted, unsandboxed Python executed after every build depth."
                ),
                multiline=True,
                default=options.get("depth_processed_script", ""),
            ),
            TextDef(
                "finished_script",
                label="Run after\nbuild",
                tooltip=(
                    "Trusted, unsandboxed Python executed after the build, even "
                    "when another placeholder reported an error."
                ),
                multiline=True,
                default=options.get("finished_script", ""),
            ),
        ]

    def collect_placeholders(self):
        """Collect only Group nodes carrying this plugin identifier."""
        output = []
        for node in self.collect_scene_placeholders():
            data = self._read(node)
            if not data or data.get("plugin_identifier") != self.identifier:
                continue
            output.append(PlaceholderItem(node.getName(), data, self))
        return output

    def prepare_placeholders(self, placeholders):
        """Execute each configured prepare script in placeholder order."""
        super().prepare_placeholders(placeholders)
        for placeholder in placeholders:
            script = placeholder.data.get("prepare_script")
            if script:
                self.run_script(placeholder, script)

    def populate_placeholder(self, placeholder):
        """Execute populate code and register deferred phase callbacks."""
        populate_script = placeholder.data.get("populate_script")
        depth_script = placeholder.data.get("depth_processed_script")
        finished_script = placeholder.data.get("finished_script")
        order = int(placeholder.order)

        if populate_script:
            self.run_script(placeholder, populate_script)

        if depth_script:
            callback = weakref_partial(self.run_script, placeholder, depth_script)
            self.builder.add_on_depth_processed_callback(callback, order=order)
        if finished_script:
            callback = weakref_partial(
                self.run_script,
                placeholder,
                finished_script,
            )
            self.builder.add_on_finished_callback(callback, order=order)

        keep_placeholder = placeholder.data.get("keep_placeholder", True)
        if keep_placeholder:
            return
        if depth_script or finished_script:
            callback = weakref_partial(self._delete_after_finish, placeholder)
            self.builder.add_on_finished_callback(callback, order=order + 1)
        else:
            self.delete_placeholder(placeholder)

    def _delete_after_finish(self, placeholder, event=None) -> None:
        """Delete after build completion while accepting Core's event callback."""
        self.delete_placeholder(placeholder)

    def run_script(self, placeholder, script, event=None):
        """Execute trusted administrator Python with placeholder context.

        Args:
            placeholder: Workfile Builder placeholder item.
            script: Trusted administrator-authored Python source.
            event: Optional Core depth or finished event.

        Returns:
            The execution namespace, useful for diagnostics and tests.

        Warning:
            This method is deliberately unsandboxed. The source can import
            modules, access the network, and modify files as the Katana user.
        """
        self.log.debug("Running unsandboxed Workfile Builder script: %s", event)
        namespace = {
            "NodegraphAPI": NodegraphAPI,
            "event": event,
            "placeholder": placeholder,
            "plugin": self,
        }
        code = compile(script, "<AYON Katana Workfile Builder script>", "exec")
        exec(code, namespace, namespace)
        return namespace
