"""Inspect filesystem references authored in a Katana workfile."""

from __future__ import annotations

import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional

from ayon_katana.api import compat, workio

REFERENCE_PARAMETERS = {
    "UsdIn": ("fileName",),
    "UsdSubLayerAdd": ("asset",),
    "Alembic_In": ("abcAsset",),
    "ImageRead": ("file",),
}

_URI_SCHEME_PATTERN = re.compile(r"^[a-z][a-z0-9+.-]*://", re.IGNORECASE)
_HASH_SEQUENCE_PATTERN = re.compile(r"(#+)")
_PRINTF_SEQUENCE_PATTERN = re.compile(r"%0?(\d*)d")
_DOLLAR_F_SEQUENCE_PATTERN = re.compile(r"\$F(\d*)")


@dataclass(frozen=True)
class WorkfileReference:
    """One registered file parameter discovered in the Katana node graph."""

    node: Any
    parameter: Any
    node_type: str
    parameter_name: str
    authored_value: str
    resolved_value: Optional[str]
    is_expression: bool
    workfile_dir: Optional[str] = None

    @property
    def node_name(self) -> str:
        """Return the node name."""
        return str(self.node.getName())

    @property
    def label(self) -> str:
        """Return the node and parameter label."""
        return f"{self.node_name}.{self.parameter_name}"

    @property
    def is_entity_uri(self) -> bool:
        """Return whether the value is a URI."""
        return bool(
            self.authored_value and _URI_SCHEME_PATTERN.match(self.authored_value)
        )

    @property
    def has_environment_tokens(self) -> bool:
        """Return whether the value contains environment tokens."""
        return has_environment_tokens(self.authored_value)

    @property
    def is_relative_literal(self) -> bool:
        """Return whether the value is a repairable relative path."""
        if (
            self.is_expression
            or self.is_entity_uri
            or self.has_environment_tokens
            or not self.authored_value
        ):
            return False
        return not os.path.isabs(self.authored_value)


def has_environment_tokens(value: str) -> bool:
    """Return whether shell-style environment expansion appears in a value."""
    return bool(value and ("$" in value or ("%" in value and value.count("%") >= 2)))


def has_sequence_token(value: str) -> bool:
    """Return whether a path contains a supported frame-sequence token."""
    if not value:
        return False
    return bool(
        _HASH_SEQUENCE_PATTERN.search(value)
        or _PRINTF_SEQUENCE_PATTERN.search(value)
        or _DOLLAR_F_SEQUENCE_PATTERN.search(value)
    )


def expand_sequence_path(value: str, frame: int) -> str:
    """Replace the first supported sequence token with a concrete frame."""
    hash_match = _HASH_SEQUENCE_PATTERN.search(value)
    if hash_match:
        padding = len(hash_match.group(1))
        return (
            value[: hash_match.start()]
            + f"{int(frame):0{padding}d}"
            + value[hash_match.end() :]
        )

    printf_match = _PRINTF_SEQUENCE_PATTERN.search(value)
    if printf_match:
        padding = int(printf_match.group(1) or 1)
        return (
            value[: printf_match.start()]
            + f"{int(frame):0{padding}d}"
            + value[printf_match.end() :]
        )

    dollar_f_match = _DOLLAR_F_SEQUENCE_PATTERN.search(value)
    if dollar_f_match:
        padding = int(dollar_f_match.group(1) or 1)
        return (
            value[: dollar_f_match.start()]
            + f"{int(frame):0{padding}d}"
            + value[dollar_f_match.end() :]
        )
    return value


def required_reference_paths(
    reference: WorkfileReference,
    *,
    frame_start: Optional[int] = None,
    frame_end: Optional[int] = None,
    frame_step: int = 1,
) -> list[str]:
    """Return concrete filesystem paths required by one reference.

    When a publish frame range is available, evaluate the Katana parameter at
    every required frame. This is necessary for expression-driven or animated
    string parameters whose value at frame 0 is unrelated to the published
    sequence.
    """
    if reference.is_entity_uri:
        return []

    if frame_start is None or frame_end is None:
        value = reference.resolved_value
        if not value or has_sequence_token(value):
            return []
        return [value]

    if int(frame_step) <= 0:
        raise ValueError("Reference frame step must be greater than zero.")
    if int(frame_end) < int(frame_start):
        raise ValueError(f"Invalid reference frame range: {frame_start}-{frame_end}.")

    workfile_dir = Path(reference.workfile_dir) if reference.workfile_dir else None
    output = []
    seen = set()
    for frame in range(int(frame_start), int(frame_end) + 1, int(frame_step)):
        evaluated = _parameter_value(reference.parameter, float(frame))
        if not evaluated:
            raise ValueError(f"path is empty at frame {frame}")
        if _URI_SCHEME_PATTERN.match(evaluated):
            raise ValueError(
                f"entity URI at frame {frame} cannot be filesystem-validated"
            )
        resolved = _resolve_literal_value(evaluated, workfile_dir)
        if not resolved:
            raise ValueError(
                f"path could not be resolved at frame {frame}: {evaluated}"
            )
        concrete = (
            expand_sequence_path(resolved, frame)
            if has_sequence_token(resolved)
            else resolved
        )
        key = os.path.normcase(os.path.normpath(concrete))
        if key in seen:
            continue
        seen.add(key)
        output.append(concrete)
    return output


def collect_workfile_references() -> list[WorkfileReference]:
    """Collect registered filesystem references from the current Katana graph."""
    workfile_path = workio.get_current_workfile()
    workfile_dir = Path(workfile_path).parent if workfile_path else None
    references = []
    for node in compat.iter_nodes():
        node_type = str(node.getType())
        parameter_names = REFERENCE_PARAMETERS.get(node_type)
        if not parameter_names:
            continue
        for parameter_name in parameter_names:
            parameter = node.getParameter(parameter_name)
            if parameter is None:
                continue
            references.append(
                _reference_from_parameter(
                    node,
                    node_type,
                    parameter,
                    parameter_name,
                    workfile_dir,
                )
            )
    return references


def _reference_from_parameter(
    node: Any,
    node_type: str,
    parameter: Any,
    parameter_name: str,
    workfile_dir: Optional[Path],
) -> WorkfileReference:
    """Build one dependency record from a Katana parameter."""
    expression = _parameter_is_expression(parameter)
    resolved_raw = _parameter_value(parameter)
    authored = _parameter_expression(parameter) if expression else resolved_raw
    if not authored:
        authored = resolved_raw
    resolved = _resolve_literal_value(resolved_raw, workfile_dir)
    if not expression:
        resolved = _resolve_literal_value(authored, workfile_dir)
    return WorkfileReference(
        node=node,
        parameter=parameter,
        node_type=node_type,
        parameter_name=parameter_name,
        authored_value=authored,
        resolved_value=resolved or None,
        is_expression=expression,
        workfile_dir=str(workfile_dir) if workfile_dir is not None else None,
    )


def _parameter_is_expression(parameter: Any) -> bool:
    return bool(parameter.isExpression())


def _parameter_expression(parameter: Any) -> str:
    return str(parameter.getExpression() or "")


def _parameter_value(parameter: Any, time: float = 0.0) -> str:
    value = parameter.getValue(float(time))
    return "" if value is None else str(value)


def unique_reference_nodes(references: list[WorkfileReference]) -> list[Any]:
    """Return referenced Katana nodes once, preserving discovery order."""
    nodes = []
    seen = set()
    for reference in references:
        key = reference.node_name
        if key in seen:
            continue
        seen.add(key)
        nodes.append(reference.node)
    return nodes


def _resolve_literal_value(value: str, workfile_dir: Optional[Path]) -> Optional[str]:
    if not value:
        return None
    if _URI_SCHEME_PATTERN.match(value):
        return value
    expanded = os.path.expandvars(value)
    if has_environment_tokens(value) and expanded == value:
        return None
    if os.path.isabs(expanded):
        return os.path.normpath(expanded)
    if workfile_dir is None:
        return None
    return os.path.normpath(os.path.join(str(workfile_dir), expanded))
