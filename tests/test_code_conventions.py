"""Regression checks for public Katana Python naming and documentation."""

from __future__ import annotations

import ast
import re
from pathlib import Path

ROOT = Path(__file__).parents[1]
SOURCE_ROOTS = (ROOT / "client" / "ayon_katana", ROOT / "server")
SNAKE_CASE = re.compile(r"^_*[a-z][a-z0-9_]*$|^__init__$")
PASCAL_CASE = re.compile(r"^_*[A-Z][A-Za-z0-9]*$")


def _source_files() -> list[Path]:
    """Return all addon-owned client and server Python files."""
    return sorted(path for root in SOURCE_ROOTS for path in root.rglob("*.py"))


def test_source_names_follow_python_conventions() -> None:
    """Python files, functions, and classes use one naming convention."""
    failures = []
    for path in _source_files():
        if not SNAKE_CASE.fullmatch(path.stem):
            failures.append(f"file: {path.relative_to(ROOT)}")
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef) and not PASCAL_CASE.fullmatch(node.name):
                failures.append(
                    f"class: {path.relative_to(ROOT)}:{node.lineno}:{node.name}"
                )
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and not (
                SNAKE_CASE.fullmatch(node.name)
            ):
                failures.append(
                    f"function: {path.relative_to(ROOT)}:{node.lineno}:{node.name}"
                )

    assert failures == []


def test_public_source_has_docstrings() -> None:
    """Every module, class, and public function has a concise API description."""
    failures = []
    for path in _source_files():
        tree = ast.parse(path.read_text(encoding="utf-8"))
        if ast.get_docstring(tree) is None:
            failures.append(f"module: {path.relative_to(ROOT)}")
        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef) and ast.get_docstring(node) is None:
                failures.append(
                    f"class: {path.relative_to(ROOT)}:{node.lineno}:{node.name}"
                )
            if (
                isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
                and not node.name.startswith("_")
                and ast.get_docstring(node) is None
            ):
                failures.append(
                    f"function: {path.relative_to(ROOT)}:{node.lineno}:{node.name}"
                )

    assert failures == []
