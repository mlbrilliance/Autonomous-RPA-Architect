"""Filesystem helper utilities."""

from __future__ import annotations

import re
from pathlib import Path

from jinja2 import Template


def ensure_dir(path: Path) -> Path:
    """Create a directory (and parents) if it does not exist.

    Args:
        path: Directory path to ensure.

    Returns:
        The same *path*, guaranteed to exist.
    """
    path.mkdir(parents=True, exist_ok=True)
    return path


def write_file(path: Path, content: str) -> None:
    """Write *content* to *path*, creating parent directories as needed.

    Args:
        path: Target file path.
        content: Text content to write.
    """
    ensure_dir(path.parent)
    path.write_text(content, encoding="utf-8")


def read_file(path: Path) -> str:
    """Read and return the full text content of a file.

    Args:
        path: File to read.

    Returns:
        File contents as a string.

    Raises:
        FileNotFoundError: If *path* does not exist.
    """
    return path.read_text(encoding="utf-8")


def copy_template(src: Path, dst: Path, context: dict[str, str]) -> None:
    """Copy a Jinja2 template file, rendering it with *context*.

    If the source is not a template (contains no ``{{``), it is copied as-is.

    Args:
        src: Source template file.
        dst: Destination file path.
        context: Template variable mapping.
    """
    raw = read_file(src)
    if "{{" in raw:
        rendered = Template(raw).render(**context)
    else:
        rendered = raw
    write_file(dst, rendered)


def safe_filename(name: str) -> str:
    """Sanitize *name* for safe use as a filesystem path component.

    Replaces whitespace with underscores, strips non-alphanumeric characters
    (except ``_`` and ``-``), and truncates to 255 characters.

    Args:
        name: Raw name to sanitize.

    Returns:
        A filesystem-safe string.
    """
    sanitized = re.sub(r"\s+", "_", name.strip())
    sanitized = re.sub(r"[^\w\-]", "", sanitized)
    return sanitized[:255]
