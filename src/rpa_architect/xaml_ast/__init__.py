"""Shared XAML AST layer used by both Self-Healing Swarm and XAML Migrator."""

from rpa_architect.xaml_ast.nodes import (
    XamlActivity,
    XamlDocument,
    XamlNode,
    XamlSelector,
)
from rpa_architect.xaml_ast.reader import XamlParseError, read_xaml
from rpa_architect.xaml_ast.selector_extractor import (
    ExtractedSelector,
    extract_selectors,
    patch_selector,
)
from rpa_architect.xaml_ast.writer import write_xaml

__all__ = [
    "ExtractedSelector",
    "XamlActivity",
    "XamlDocument",
    "XamlNode",
    "XamlParseError",
    "XamlSelector",
    "extract_selectors",
    "patch_selector",
    "read_xaml",
    "write_xaml",
]
