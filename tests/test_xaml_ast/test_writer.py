"""Tests for xaml_ast.writer — mutate an AST and emit valid XAML."""

from __future__ import annotations

from rpa_architect.xaml_ast.reader import read_xaml
from rpa_architect.xaml_ast.writer import write_xaml

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
  </Sequence>
</Activity>
"""


class TestRoundTrip:
    def test_parse_then_write_preserves_namespaces(self) -> None:
        doc = read_xaml(SIMPLE_XAML)
        out = write_xaml(doc)
        # All three namespace URIs must appear in output
        assert "http://schemas.microsoft.com/netfx/2009/xaml/activities" in out
        assert "http://schemas.uipath.com/workflow/activities" in out
        assert "http://schemas.microsoft.com/winfx/2006/xaml" in out

    def test_parse_then_write_preserves_activity_names(self) -> None:
        doc = read_xaml(SIMPLE_XAML)
        out = write_xaml(doc)
        assert "Click" in out
        assert "Sequence" in out
        assert "Target" in out

    def test_parse_then_write_preserves_display_names(self) -> None:
        doc = read_xaml(SIMPLE_XAML)
        out = write_xaml(doc)
        assert 'DisplayName="Main"' in out
        assert 'DisplayName="Click Login"' in out

    def test_parse_then_write_preserves_selector_string(self) -> None:
        doc = read_xaml(SIMPLE_XAML)
        out = write_xaml(doc)
        # The escaped selector must survive round-trip (content-wise, encoding may differ)
        out_reparsed = read_xaml(out)
        from rpa_architect.xaml_ast.selector_extractor import extract_selectors

        selectors = extract_selectors(out_reparsed)
        assert len(selectors) == 1
        assert "id='login'" in selectors[0].selector_xml

    def test_round_trip_is_parseable(self) -> None:
        """write output must be parseable by read_xaml again."""
        doc = read_xaml(SIMPLE_XAML)
        out = write_xaml(doc)
        # Should not raise
        doc2 = read_xaml(out)
        assert doc2.root.activity_type == "Activity"


class TestSelectorPatch:
    def test_can_mutate_selector_then_write(self) -> None:
        doc = read_xaml(SIMPLE_XAML)
        from rpa_architect.xaml_ast.selector_extractor import (
            extract_selectors,
            patch_selector,
        )

        selectors = extract_selectors(doc)
        assert len(selectors) == 1
        original = selectors[0]
        new_xml = "<webctrl id='login-v2' />"
        patch_selector(doc, original.activity_xpath, new_xml)
        out = write_xaml(doc)
        reparsed = read_xaml(out)
        new_selectors = extract_selectors(reparsed)
        assert len(new_selectors) == 1
        assert "id='login-v2'" in new_selectors[0].selector_xml
