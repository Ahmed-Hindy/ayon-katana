"""Process Katana outputs locally during publishing."""

import os
import subprocess
import tempfile
from pathlib import Path

import pyblish.api
from ayon_core.pipeline import PublishError

from ayon_katana.api import plugin, render, workio


class ExtractLocalRender(plugin.KatanaExtractorPlugin):
    """Process a non-farm Render or ImageWrite through batch mode."""

    label = "Extract Local Output"
    order = pyblish.api.ExtractorOrder - 0.4
    families = ["render", "katana.render", "image", "katana.image"]

    def process(self, instance):
        """Run Katana in batch mode and verify expected files."""
        if instance.data.get("farm"):
            self.log.debug("Katana output is configured for farm processing.")
            return

        render_target = (instance.data.get("creator_attributes") or {}).get(
            "render_target",
            "farm",
        )
        expected_files = self._expected_files(instance)
        if render_target == "local_no_render":
            self._validate_output_files(
                expected_files,
                failure_message=(
                    "Katana existing-frame publish has missing, empty, unreadable, "
                    "or corrupt output files."
                ),
                logger=self.log,
            )
            self.log.info(
                "Validated %d existing Katana output files without rendering.",
                len(expected_files),
            )
            return
        if render_target != "local":
            self.log.debug("Katana output target is not local; skipping extraction.")
            return

        try:
            scene_path = workio.validate_workfile_path(
                instance.context.data.get("currentFile", ""),
                require_exists=True,
            )
        except ValueError as exc:
            raise PublishError(
                f"Katana local render has no valid scene: {exc}"
            ) from exc

        render_node = instance.data.get("render_node")
        if not render_node:
            raise PublishError(
                "Katana local output has no collected Render or ImageWrite node."
            )

        for filepath in expected_files:
            filepath.parent.mkdir(parents=True, exist_ok=True)

        executable = render.get_katana_executable()
        frame_start = int(instance.data["frameStartHandle"])
        frame_end = int(instance.data["frameEndHandle"])
        frame_step = int(instance.data["byFrameStep"])
        frame_range = self._format_frame_range(
            frame_start,
            frame_end,
            frame_step,
        )
        environment = os.environ.copy()
        environment.pop("AYON_KATANA_WORKFILE_PATH", None)
        command = [
            str(executable),
            "--batch",
            f"--katana-file={scene_path}",
            "-t",
            frame_range,
            f"--render-node={render_node}",
        ]
        self.log.info("Rendering Katana frames %s locally.", frame_range)
        with tempfile.TemporaryFile(
            mode="w+t",
            encoding="utf-8",
            errors="replace",
        ) as render_log:
            completed = subprocess.run(
                command,
                cwd=executable.parent,
                env=environment,
                check=False,
                stdout=render_log,
                stderr=subprocess.STDOUT,
                text=True,
            )
            if completed.returncode != 0:
                render_log.seek(0)
                log_tail = render_log.read()[-8000:]
                raise PublishError(
                    f"Katana local render failed for frames {frame_range} with "
                    f"exit code {completed.returncode}.",
                    detail=f"Katana batch output:\n{log_tail}",
                )

        self._validate_output_files(
            expected_files,
            failure_message=(
                "Katana local render did not produce all expected output files."
            ),
            logger=self.log,
        )

    @classmethod
    def _validate_output_files(
        cls,
        filepaths,
        *,
        failure_message: str,
        logger=None,
    ) -> None:
        invalid_files = []
        for filepath in filepaths:
            if not filepath.is_file():
                invalid_files.append((filepath, "missing"))
                continue
            try:
                with filepath.open("rb") as stream:
                    if not stream.read(1):
                        invalid_files.append((filepath, "empty"))
                        continue
            except OSError as exc:
                invalid_files.append((filepath, f"unreadable: {exc}"))
                continue

            try:
                cls._decode_output_file(filepath, logger=logger)
            except Exception as exc:
                invalid_files.append(
                    (
                        filepath,
                        f"OpenImageIO decode failed: {type(exc).__name__}: {exc}",
                    )
                )

        if invalid_files:
            formatted_files = "\n".join(
                f"- {path}: {reason}" for path, reason in invalid_files
            )
            raise PublishError(
                failure_message,
                detail=f"Invalid files:\n{formatted_files}",
            )

    @staticmethod
    def _decode_output_file(filepath: Path, *, logger=None) -> None:
        from ayon_core.lib import get_oiio_tool_args, run_subprocess

        arguments = get_oiio_tool_args(
            "oiiotool",
            "--hash",
            str(filepath),
        )
        run_subprocess(arguments, logger=logger)

    @staticmethod
    def _format_frame_range(frame_start, frame_end, frame_step):
        if frame_end < frame_start:
            raise PublishError(
                f"Invalid Katana render range: {frame_start}-{frame_end}."
            )
        if frame_step < 1:
            raise PublishError(f"Invalid Katana render frame step: {frame_step}.")
        if frame_start == frame_end:
            return str(frame_start)
        if frame_step == 1:
            return f"{frame_start}-{frame_end}"
        return ",".join(
            str(frame) for frame in range(frame_start, frame_end + 1, frame_step)
        )

    @staticmethod
    def _expected_files(instance):
        expected_files = instance.data.get("expectedFiles") or []
        if not expected_files:
            raise PublishError("Katana local output has no expected output files.")

        output = []
        for filepaths in expected_files[0].values():
            if isinstance(filepaths, str):
                output.append(Path(filepaths))
            else:
                output.extend(Path(filepath) for filepath in filepaths)
        if not output:
            raise PublishError("Katana local output has no expected output files.")
        return output
