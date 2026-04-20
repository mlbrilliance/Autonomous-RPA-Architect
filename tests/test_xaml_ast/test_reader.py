"""Tests for xaml_ast.reader — parses XAML into a typed AST."""

from __future__ import annotations

import pytest

from rpa_architect.xaml_ast.nodes import (
    XamlActivity,
    XamlDocument,
    XamlSelector,
)
from rpa_architect.xaml_ast.reader import XamlParseError, read_xaml


SIMPLE_XAML = """<?xml version="1.0" encoding="utf-8"?>
<Activity xmlns="http://schemas.microsoft.com/netfx/2009/xaml/activities"
          xmlns:ui="http://schemas.uipath.com/workflow/activities"
          xmlns:x="http://schemas.microsoft.com/winfx/2006/xaml">
  <Sequence DisplayName="Main">
    <ui:Click DisplayName="Click Login">
      <ui:Click.Target>
        <ui:Target Selector="&lt;webctrl id='login' /&gt;" />
      </ui:Click.Target>
    </ui:Click>
    <ui:TypeInto DisplayName="Type Username" Text="admin">
      <ui:TypeInto.Target>
        <ui:Target Selector="&lt;webctrl name='user' /&gt;" />
      </ui:TypeInto.Target>
    </ui:TypeInto>
    <ui:LogMessage DisplayName="Log Done" Level="Info" Message="Done" />
  </Sequence>
</Activity>
"""


class TestReadXaml:
    def test_returns_xaml_document(self) -> None:
        doc = read_xaml(SIMPLE_XAML)
        assert isinstance(doc, XamlDocument)

    def test_captures_namespace_declarations(self) -> None:
        doc = read_xaml(SIMPLE_XAML)
        assert "ui" in doc.namespaces
        assert doc.namespaces["ui"] == "http://schemas.uipath.com/workflow/activities"
        assert "x" in doc.namespaces

    def test_root_is_activity_node(self) -> None:
        doc = read_xaml(SIMPLE_XAML)
        assert doc.root.activity_type == "Activity"

    def test_walks_into_sequence(self) -> None:
        doc = read_xaml(SIMPLE_XAML)
        seq = doc.root.children[0]
        assert isinstance(seq, XamlActivity)
        assert seq.activity_type == "Sequence"
        assert seq.properties.get("DisplayName") == "Main"

    def test_identifies_click_activity(self) -> None:
        doc = read_xaml(SIMPLE_XAML)
        seq = doc.root.children[0]
        click = seq.children[0]
        assert click.activity_type == "Click"
        assert click.display_name == "Click Login"

    def test_display_name_convenience_property(self) -> None:
        doc = read_xaml(SIMPLE_XAML)
        seq = doc.root.children[0]
        assert seq.display_name == "Main"

    def test_xpath_back_reference(self) -> None:
        """Every activity must carry an xpath so writers can locate it."""
        doc = read_xaml(SIMPLE_XAML)
        seq = doc.root.children[0]
        assert seq.xpath  # non-empty
        click = seq.children[0]
        assert click.xpath
        # xpath should be unique
        assert seq.xpath != click.xpath

    def test_parse_error_raises_xaml_parse_error(self) -> None:
        with pytest.raises(XamlParseError):
            read_xaml("<not-valid xml")

    def test_empty_document_raises(self) -> None:
        with pytest.raises(XamlParseError):
            read_xaml("")


class TestSelectorCapture:
    def test_click_target_has_selector(self) -> None:
        doc = read_xaml(SIMPLE_XAML)
        click = doc.root.children[0].children[0]
        selectors = [c for c in _walk(click) if isinstance(c, XamlSelector)]
        assert len(selectors) == 1
        assert "id='login'" in selectors[0].selector_xml

    def test_typeinto_target_has_selector(self) -> None:
        doc = read_xaml(SIMPLE_XAML)
        typeinto = doc.root.children[0].children[1]
        selectors = [c for c in _walk(typeinto) if isinstance(c, XamlSelector)]
        assert len(selectors) == 1
        assert "name='user'" in selectors[0].selector_xml


def _walk(node):
    yield node
    for child in getattr(node, "children", []):
        yield from _walk(child)
