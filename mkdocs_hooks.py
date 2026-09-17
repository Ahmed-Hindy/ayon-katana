import glob
import json
import logging
import os
from pathlib import Path
from shutil import rmtree

TMP_FILE = "./missing_init_files.json"
_CREATED_INIT_FILES: list[str] = []


class ColorFormatter(logging.Formatter):
    """Format MkDocs hook logs with simple terminal colors."""

    grey = "\x1b[38;20m"
    green = "\x1b[32;20m"
    yellow = "\x1b[33;20m"
    red = "\x1b[31;20m"
    bold_red = "\x1b[31;1m"
    reset = "\x1b[0m"
    fmt = (
        "%(asctime)s - %(name)s - %(levelname)s - %(message)s (%(filename)s:%(lineno)d)"
    )

    FORMATS = {
        logging.DEBUG: grey + fmt + reset,
        logging.INFO: green + fmt + reset,
        logging.WARNING: yellow + fmt + reset,
        logging.ERROR: red + fmt + reset,
        logging.CRITICAL: bold_red + fmt + reset,
    }

    def format(self, record: logging.LogRecord) -> str:
        """Format a log record.

        Args:
            record: Log record to format.

        Returns:
            Formatted log message.
        """
        formatter = logging.Formatter(self.FORMATS.get(record.levelno))
        return formatter.format(record)


_handler = logging.StreamHandler()
_handler.setFormatter(ColorFormatter())
logging.basicConfig(level=logging.INFO, handlers=[_handler])


def _create_init_file(dirpath: str, message: str) -> None:
    """Create a temporary package initializer.

    Args:
        dirpath: Directory that needs an ``__init__.py`` file.
        message: Log prefix.
    """
    init_file = f"{dirpath}/__init__.py"
    Path(init_file).touch()
    _CREATED_INIT_FILES.append(init_file)
    logging.info("%s: created '%s'", message, init_file)


def _create_parent_init_files(dirpath: str, rootpath: str, message: str) -> None:
    """Create missing package initializers up to a scan root.

    Args:
        dirpath: Directory containing a Python file.
        rootpath: Root directory of the scan.
        message: Log prefix.
    """
    parent_path = dirpath
    while parent_path != rootpath:
        parent_path = os.path.dirname(parent_path)
        parent_init = os.path.join(parent_path, "__init__.py")
        if os.path.exists(parent_init):
            break
        _create_init_file(parent_path, message)


def _add_missing_init_files(*roots: str, message: str = "") -> None:
    """Temporarily make Python source directories importable for AutoAPI.

    Args:
        *roots: Source roots to scan.
        message: Log prefix.
    """
    for root in roots:
        if not os.path.exists(root):
            continue

        rootpath = os.path.abspath(root)
        for dirpath, _dirs, files in os.walk(rootpath):
            if "__init__.py" in files:
                continue
            if "." in dirpath:
                continue
            if not glob.glob(os.path.join(dirpath, "*.py")):
                continue

            _create_init_file(dirpath, message)
            _create_parent_init_files(dirpath, rootpath, message)

    with open(TMP_FILE, "w", encoding="utf-8") as stream:
        json.dump(_CREATED_INIT_FILES, stream)


def _remove_missing_init_files(message: str = "") -> None:
    """Remove package initializers created for the documentation build.

    Args:
        message: Log prefix.
    """
    files = list(_CREATED_INIT_FILES)
    if os.path.exists(TMP_FILE):
        with open(TMP_FILE, encoding="utf-8") as stream:
            files = json.load(stream)

    for filepath in files:
        path = Path(filepath)
        if path.exists():
            path.unlink()
            logging.info("%s: removed %s", message, filepath)

    if os.path.exists(TMP_FILE):
        os.remove(TMP_FILE)
    _CREATED_INIT_FILES.clear()


def _remove_pycache_dirs(message: str = "") -> None:
    """Remove stale source bytecode directories before AutoAPI scans.

    Args:
        message: Log prefix.
    """
    removed = 0
    for root in ("client", "server"):
        if not os.path.exists(root):
            continue
        for dirpath, dirs, _files in os.walk(root):
            if "__pycache__" not in dirs:
                continue
            pycache_dir = Path(dirpath) / "__pycache__"
            rmtree(pycache_dir)
            removed += 1
            logging.info("%s: removed '%s'", message, pycache_dir)

    if not removed:
        logging.info("%s: no source __pycache__ dirs found", message)


def on_startup(command: str, dirty: bool) -> None:
    """Prepare the source tree for MkDocs startup.

    Args:
        command: MkDocs command being executed.
        dirty: Whether MkDocs is using a dirty reload.
    """
    del command, dirty
    _remove_pycache_dirs(message="HOOK - on_startup")


def on_pre_build(config: object) -> None:
    """Prepare Python package roots before documentation generation.

    Args:
        config: MkDocs configuration object.
    """
    del config
    try:
        _add_missing_init_files(
            "client",
            "server",
            message="HOOK - on_pre_build",
        )
    except BaseException:
        _remove_missing_init_files(message="HOOK - cleanup after error")
        raise


def on_post_build(config: object) -> None:
    """Restore temporary package changes after documentation generation.

    Args:
        config: MkDocs configuration object.
    """
    del config
    _remove_missing_init_files(message="HOOK - on_post_build")
