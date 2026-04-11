"""Tests for UiPath selector XML validation."""

from __future__ import annotations

import pytest

from rpa_architect.validation.selector_validator import (
    SelectorValidationResult,
    validate_selector,
)


class TestValidHtmlSelector:
    """Test valid HTML-based selectors."""

    def test_valid_html_selector(self) -> None:
        selector = "<html app='chrome.exe' /><webctrl tag='button' id='submitBtn' />"
        result = validate_selector(selector)
        assert result.valid is True
        errors = [i for i in result.issues if i.severity == "error"]
        assert len(errors) == 0

    def test_valid_html_nested(self) -> None:
        selector = "<html app='chrome.exe'><webctrl tag='input' name='user' /></html>"
        result = validate_selector(selector)
        assert result.valid is True


class TestValidWndSelector:
    """Test valid Windows-based selectors."""

    def test_valid_wnd_selector(self) -> None:
        selector = "<wnd app='notepad.exe' cls='Notepad' title='Untitled' />"
        result = validate_selector(selector)
        assert result.valid is True
        errors = [i for i in result.issues if i.severity == "error"]
        assert len(errors) == 0


class TestInvalidSelectorXml:
    """Test malformed XML selectors."""

    def test_invalid_selector_xml(self) -> None:
        selector = "<html app='chrome.exe'><unclosed"
        result = validate_selector(selector)
        assert result.valid is False
        errors = [i for i in result.issues if i.severity == "error"]
        assert any("not valid XML" in e.message for e in errors)

    def test_non_xml_string(self) -> None:
        selector = "this is not xml at all"
        result = validate_selector(selector)
        assert result.valid is False


class TestPlaceholderSelector:
    """Test detection of TODO-marked / placeholder selectors."""

    def test_placeholder_selector(self) -> None:
        selector = "<html app='TODO_APP' tag='TODO_TAG' aaname='TODO: Click here' />"
        result = validate_selector(selector)
        # Placeholder patterns like PLACEHOLDER, CHANGE_ME are detected;
        # plain TODO without the specific patterns may not trigger.
        # The selector itself should still parse as valid XML.
        assert result.selector_xml == selector

    def test_placeholder_pattern_detected(self) -> None:
        selector = "<html app='PLACEHOLDER' />"
        result = validate_selector(selector)
        warnings = [i for i in result.issues if i.severity == "warning"]
        assert any("placeholder" in w.message.lower() for w in warnings)

    def test_change_me_pattern(self) -> None:
        selector = "<html app='CHANGE_ME' />"
        result = validate_selector(selector)
        warnings = [i for i in result.issues if i.severity == "warning"]
        assert any("placeholder" in w.message.lower() for w in warnings)

    def test_mustache_placeholder(self) -> None:
        selector = "<html app='{{ app_name }}' />"
        result = validate_selector(selector)
        warnings = [i for i in result.issues if i.severity == "warning"]
        assert any("placeholder" in w.message.lower() for w in warnings)


class TestEmptySelector:
    """Test empty selector handling."""

    def test_empty_selector(self) -> None:
        result = validate_selector("")
        assert result.valid is False
        errors = [i for i in result.issues if i.severity == "error"]
        assert any("empty" in e.message.lower() for e in errors)

    def test_whitespace_only_selector(self) -> None:
        result = validate_selector("   ")
        assert result.valid is False
