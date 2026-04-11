"""Shared line-number registry for XAML elements.

ElementTree Elements don't support arbitrary attribute assignment, so we
store line numbers in a module-level dict keyed by ``id(element)``.  The
engine populates this map after parsing; rule modules read it via
``get_line_number()``.
"""

from __future__ import annotations

import xml.etree.ElementTree as ET

# Maps id(element) -> 1-based source line number
_line_number_map: dict[int, int] = {}


def get_line_number(element: ET.Element) -> int:
    """Return the approximate source line number for *element*, or 0 if unknown."""
    return _line_number_map.get(id(element), 0)


def clear() -> None:
    """Clear the map (called before each lint run)."""
    _line_number_map.clear()


def set_line_number(element: ET.Element, line: int) -> None:
    """Record the line number for *element*."""
    _line_number_map[id(element)] = line
