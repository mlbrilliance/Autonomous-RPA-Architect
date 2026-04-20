"""Tests for xaml_ast.selector_extractor — pull selectors from deployed XAML."""

from __future__ import annotations

from rpa_architect.xaml_ast.reader import read_xaml
from rpa_architect.xaml_ast.selector_extractor import (
    ExtractedSelector,
    extract_selectors,
)


MULTI_ACTIVITY_XAML = """<?xml version="1.0" encoding="utf-8"?>
<Activity xmlns="http://schemas.microsoft.com/netfx/2009/xaml/activities"
          xmlns:ui="http://schemas.uipath.com/workflow/activities"
          xmlns:x="http://schemas.microsoft.com/winfx/2006/xaml">
  <Sequence DisplayName="Login Flow">
    <ui:Click DisplayName="Click Submit">
      <ui:Click.Target>
        <ui:Target Selector="&lt;webctrl id='submit' /&gt;" />
      </ui:Click.Target>
    </ui:Click>
    <ui:TypeInto DisplayName="Type Username" Text="admin">
      <ui:TypeInto.Target>
        <ui:Target Selector="&lt;webctrl name='user' /&gt;"
                   WindowSelector="&lt;wnd app='chrome.exe' /&gt;" />
      </ui:TypeInto.Target>
    </ui:TypeInto>
    <ui:GetText DisplayName="Read Status">
      <ui:GetText.Target>
        <ui:Target Selector="&lt;webctrl css-selector='#status' /&gt;" />
      </ui:GetText.Target>
    </ui:GetText>
  </Sequence>
</Activity>
"""


class TestExtractSelectors:
    def test_finds_all_three_selectors(self) -> None:
        doc = read_xaml(MULTI_ACTIVITY_XAML)
        selectors = extract_selectors(doc)
        assert len(selectors) == 3

    def test_selector_carries_activity_display_name(self) -> None:
        doc = read_xaml(MULTI_ACTIVITY_XAML)
        selectors = extract_selectors(doc)
        names = [s.activity_display_name for s in selectors]
        assert "Click Submit" in names
        assert "Type Username" in names
        assert "Read Status" in names

    def test_selector_carries_activity_type(self) -> None:
        doc = read_xaml(MULTI_ACTIVITY_XAML)
        selectors = extract_selectors(doc)
        by_name = {s.activity_display_name: s for s in selectors}
        assert by_name["Click Submit"].activity_type == "Click"
        assert by_name["Type Username"].activity_type == "TypeInto"
        assert by_name["Read Status"].activity_type == "GetText"

    def test_selector_xml_is_unescaped(self) -> None:
        doc = read_xaml(MULTI_ACTIVITY_XAML)
        selectors = extract_selectors(doc)
        by_name = {s.activity_display_name: s for s in selectors}
        # The selector value must be readable as XML (already unescaped by parser)
        assert "id='submit'" in by_name["Click Submit"].selector_xml

    def test_window_selector_captured(self) -> None:
        doc = read_xaml(MULTI_ACTIVITY_XAML)
        selectors = extract_selectors(doc)
        by_name = {s.activity_display_name: s for s in selectors}
        # TypeInto has a WindowSelector; others do not
        assert "app='chrome.exe'" in (by_name["Type Username"].window_selector or "")
        assert not by_name["Click Submit"].window_selector

    def test_each_selector_has_xpath(self) -> None:
        doc = read_xaml(MULTI_ACTIVITY_XAML)
        selectors = extract_selectors(doc)
        xpaths = [s.activity_xpath for s in selectors]
        assert all(xp for xp in xpaths)
        assert len(set(xpaths)) == 3  # all unique

    def test_selector_is_instance_of_extracted_selector(self) -> None:
        doc = read_xaml(MULTI_ACTIVITY_XAML)
        selectors = extract_selectors(doc)
        assert all(isinstance(s, ExtractedSelector) for s in selectors)


class TestEmptyDocument:
    def test_no_selectors_for_logmessage_only(self) -> None:
        xaml = """<?xml version="1.0"?>
<Activity xmlns="http://schemas.microsoft.com/netfx/2009/xaml/activities"
          xmlns:ui="http://schemas.uipath.com/workflow/activities">
  <Sequence>
    <ui:LogMessage DisplayName="Log" Level="Info" Message="hi" />
  </Sequence>
</Activity>
"""
        doc = read_xaml(xaml)
        selectors = extract_selectors(doc)
        assert selectors == []
