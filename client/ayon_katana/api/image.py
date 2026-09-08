"""Native Katana ImageWrite configuration and output helpers."""

from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Any

IMAGE_FILE_FORMATS = (
    "exr",
    "rla",
    "cin",
    "png",
    "tif",
    "tiff",
    "jpg",
    "jpeg",
    "dpx",
    "hist",
)

_FRAME_TOKEN = re.compile(r"(#+)")


def _get_parameter(node: Any, name: str) -> Any:
    """Return one required native ImageWrite parameter.

    Args:
        node: Katana node exposing ``getParameter``.
        name: Parameter path relative to the node.

    Returns:
        Katana parameter object.

    Raises:
        RuntimeError: The parameter does not exist.
    """
    parameter = node.getParameter(name)
    if parameter is None:
        node_name = getattr(node, "getName", lambda: "<unknown>")()
        raise RuntimeError(
            f"Katana node {node_name!r} has no required parameter {name!r}."
        )
    return parameter


def configure_image_write(
    node: Any,
    *,
    output_path: str | Path,
    file_format: str,
    colorspace: str = "",
    single_frame: bool = False,
    frame: int = 1,
) -> None:
    """Configure a native Katana ``ImageWrite`` node.

    Args:
        node: Native Katana ``ImageWrite`` node.
        output_path: Still or hash-tokenized sequence path.
        file_format: Native output format.
        colorspace: Optional output colorspace.
        single_frame: Whether the node writes only one frame.
        frame: Frame written when ``single_frame`` is enabled.

    Raises:
        ValueError: The format, path, or frame is invalid.
        RuntimeError: A required Katana parameter is unavailable.
    """
    normalized_format = str(file_format).lower().lstrip(".")
    if normalized_format not in IMAGE_FILE_FORMATS:
        raise ValueError(f"Unsupported image file format: {file_format!r}.")
    normalized_path = Path(output_path).as_posix()
    if not normalized_path:
        raise ValueError("ImageWrite output path cannot be empty.")
    path_extension = Path(normalized_path).suffix.lower().lstrip(".")
    if path_extension != normalized_format:
        raise ValueError(
            f"ImageWrite path extension {path_extension!r} does not match "
            f"format {normalized_format!r}."
        )

    _get_parameter(node, "inputs.in.file").setValue(normalized_path, 0.0)
    _get_parameter(node, "inputs.in.image.fileFormat").setValue(normalized_format, 0.0)
    _get_parameter(node, "inputs.in.image.colorspace").setValue(
        str(colorspace or ""), 0.0
    )
    _get_parameter(node, "singleFrame").setValue(int(bool(single_frame)), 0.0)
    _get_parameter(node, "frame").setValue(int(frame), 0.0)


def read_image_write_settings(node: Any) -> dict[str, Any]:
    """Read publish-relevant values from a native ``ImageWrite`` node.

    Args:
        node: Native Katana ``ImageWrite`` node.

    Returns:
        Output path, format, colorspace, and single-frame settings.
    """
    return {
        "output_path": str(_get_parameter(node, "inputs.in.file").getValue(0.0)),
        "file_format": str(
            _get_parameter(node, "inputs.in.image.fileFormat").getValue(0.0)
        )
        .lower()
        .lstrip("."),
        "colorspace": str(
            _get_parameter(node, "inputs.in.image.colorspace").getValue(0.0) or ""
        ),
        "single_frame": bool(_get_parameter(node, "singleFrame").getValue(0.0)),
        "frame": int(_get_parameter(node, "frame").getValue(0.0)),
    }


def expand_image_output_pattern(
    output_pattern: str,
    frame_start: int,
    frame_end: int,
    frame_step: int,
) -> list[str]:
    """Expand one ImageWrite hash pattern into concrete normalized paths.

    Args:
        output_pattern: Still path or path containing one hash group.
        frame_start: First output frame.
        frame_end: Last output frame.
        frame_step: Positive inclusive frame increment.

    Returns:
        Concrete normalized image paths.

    Raises:
        ValueError: Range is invalid or a sequence has no unambiguous token.
    """
    if frame_end < frame_start:
        raise ValueError(f"Invalid image frame range: {frame_start}-{frame_end}.")
    if frame_step < 1:
        raise ValueError(f"Invalid image frame step: {frame_step}.")
    matches = list(_FRAME_TOKEN.finditer(output_pattern))
    frame_count = len(range(frame_start, frame_end + 1, frame_step))
    if frame_count > 1 and len(matches) != 1:
        raise ValueError("ImageWrite sequences require exactly one hash frame token.")
    if len(matches) > 1:
        raise ValueError("ImageWrite output has multiple hash frame tokens.")
    if not matches:
        return [os.path.normpath(output_pattern)]

    padding = len(matches[0].group(1))
    return [
        os.path.normpath(
            _FRAME_TOKEN.sub(str(frame).zfill(padding), output_pattern, count=1)
        )
        for frame in range(frame_start, frame_end + 1, frame_step)
    ]
