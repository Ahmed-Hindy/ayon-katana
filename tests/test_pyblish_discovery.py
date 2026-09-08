"""Tests for standalone Pyblish plugin discovery compatibility."""

from __future__ import annotations

import ast
from pathlib import Path

PROJECT_ROOT = Path(__file__).parents[1]
PYBLISH_PLUGIN_DIRECTORIES = (
    PROJECT_ROOT / "client" / "ayon_katana" / "plugins" / "publish",
    PROJECT_ROOT / "client" / "ayon_katana" / "plugins" / "deadline",
)


def test_pyblish_plugins_do_not_use_relative_imports() -> None:
    """Pyblish plugin files must import correctly as standalone modules."""
    relative_imports = []
    for plugin_directory in PYBLISH_PLUGIN_DIRECTORIES:
        for plugin_path in sorted(plugin_directory.glob("*.py")):
            module = ast.parse(plugin_path.read_text(encoding="utf-8"))
            for node in ast.walk(module):
                if isinstance(node, ast.ImportFrom) and node.level:
                    relative_imports.append(
                        f"{plugin_path.relative_to(PROJECT_ROOT)}:{node.lineno}"
                    )

    assert not relative_imports, (
        "Pyblish loads publish plugins as standalone modules, so relative "
        f"imports are unsupported: {', '.join(relative_imports)}"
    )
