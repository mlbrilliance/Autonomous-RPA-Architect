"""Tests for UiPath selector conversion from harvested elements."""

from __future__ import annotations

from rpa_architect.selectors.uipath_converter import (
    HarvestedElement,
    _is_dynamic_id,
    _is_stable_class,
    _truncate_text,
    batch_convert,
    convert_to_uipath_selector,
)


class TestIsDynamicId:
    """Tests for dynamic ID detection."""

    def test_static_id(self):
        assert not _is_dynamic_id("username")

    def test_static_short_id(self):
        assert not _is_dynamic_id("submitBtn")

    def test_empty_id(self):
        assert _is_dynamic_id("")

    def test_hex_hash(self):
        assert _is_dynamic_id("a1b2c3d4e5f6")

    def test_uuid(self):
        assert _is_dynamic_id("550e8400-e29b-41d4-a716-446655440000")

    def test_react_id(self):
        assert _is_dynamic_id(":r1a:")

    def test_numeric_id(self):
        assert _is_dynamic_id("123456")

    def test_framework_id(self):
        assert _is_dynamic_id("ember123")
        assert _is_dynamic_id("react-42")
        assert _is_dynamic_id("ng5678")


class TestIsStableClass:
    """Tests for stable CSS class detection."""

    def test_semantic_class(self):
        assert _is_stable_class("login-button")

    def test_empty_class(self):
        assert not _is_stable_class("")

    def test_css_modules_hash(self):
        assert not _is_stable_class("ab-X7kR2m")

    def test_styled_components(self):
        assert not _is_stable_class("_abc12def")

    def test_emotion_class(self):
        assert not _is_stable_class("css-1a2b3c")

    def test_bootstrap_class(self):
        assert _is_stable_class("btn-primary")


class TestTruncateText:
    """Tests for text truncation."""

    def test_short_text(self):
        assert _truncate_text("Submit") == "Submit"

    def test_long_text(self):
        result = _truncate_text("A" * 100, max_len=50)
        assert len(result) == 50

    def test_whitespace_collapse(self):
        assert _truncate_text("Submit   Form\n Now") == "Submit Form Now"


class TestConvertToUipathSelector:
    """Tests for the main selector conversion function."""

    def test_element_with_stable_id(self):
        el = HarvestedElement(tag="input", id="username")
        selector, stability = convert_to_uipath_selector(el)
        assert "<webctrl tag='input' id='username'" in selector
        assert "<html app='chrome.exe' />" in selector
        assert stability == 0.95

    def test_element_with_dynamic_id_falls_through(self):
        el = HarvestedElement(tag="input", id="a1b2c3d4e5f6g7h8", name="email")
        selector, stability = convert_to_uipath_selector(el)
        assert "name='email'" in selector
        assert stability == 0.90

    def test_element_with_name(self):
        el = HarvestedElement(tag="input", name="inv_num")
        selector, stability = convert_to_uipath_selector(el)
        assert "name='inv_num'" in selector
        assert stability == 0.90

    def test_element_with_data_testid(self):
        el = HarvestedElement(tag="button", data_testid="submit-btn")
        selector, stability = convert_to_uipath_selector(el)
        assert "data-testid='submit-btn'" in selector
        assert stability == 0.90

    def test_element_with_aria_label(self):
        el = HarvestedElement(tag="button", aria_label="Submit Form")
        selector, stability = convert_to_uipath_selector(el)
        assert "aaname='Submit Form'" in selector
        assert stability == 0.85

    def test_element_with_accessibility_name(self):
        el = HarvestedElement(tag="button", accessibility_name="Submit")
        selector, stability = convert_to_uipath_selector(el)
        assert "aaname='Submit'" in selector
        assert stability == 0.85

    def test_element_with_stable_class(self):
        el = HarvestedElement(tag="div", classes=["login-button"])
        selector, stability = convert_to_uipath_selector(el)
        assert "class='login-button'" in selector
        assert stability == 0.70

    def test_element_with_inner_text_fallback(self):
        el = HarvestedElement(tag="button", inner_text="Sign In")
        selector, stability = convert_to_uipath_selector(el)
        assert "innertext='Sign In'" in selector
        assert stability == 0.60

    def test_element_with_input_type(self):
        el = HarvestedElement(tag="input", id="pwd", input_type="password")
        selector, stability = convert_to_uipath_selector(el)
        assert "type='password'" in selector
        assert "id='pwd'" in selector

    def test_custom_app_name(self):
        el = HarvestedElement(tag="input", id="test")
        selector, _ = convert_to_uipath_selector(el, app_name="firefox.exe")
        assert "app='firefox.exe'" in selector

    def test_positional_fallback(self):
        el = HarvestedElement(tag="div")
        _, stability = convert_to_uipath_selector(el)
        assert stability == 0.30

    def test_xml_escaping(self):
        el = HarvestedElement(tag="input", id="field's")
        selector, _ = convert_to_uipath_selector(el)
        assert "&apos;" in selector

    def test_full_selector_format(self):
        """Verify the complete selector format for a simple element."""
        el = HarvestedElement(tag="input", id="username")
        selector, _ = convert_to_uipath_selector(el)
        assert selector == "<html app='chrome.exe' /><webctrl tag='input' id='username' />"


class TestBatchConvert:
    """Tests for batch conversion of match results."""

    def test_batch_convert_with_matches(self):
        from rpa_architect.ir.schema import UIAction
        from rpa_architect.selectors.element_matcher import MatchResult

        el1 = HarvestedElement(tag="input", id="username")
        el2 = HarvestedElement(tag="button", id="submit")

        matches = [
            MatchResult(
                action=UIAction(action="type_into", target="Username"),
                element=el1,
                element_name="S001_Username_0",
                confidence=0.95,
                match_method="heuristic_id",
            ),
            MatchResult(
                action=UIAction(action="click", target="Submit"),
                element=el2,
                element_name="S001_Submit_1",
                confidence=0.90,
                match_method="heuristic_id",
            ),
        ]

        result = batch_convert(matches)
        assert len(result) == 2
        assert "S001_Username_0" in result
        assert "id='username'" in result["S001_Username_0"]

    def test_batch_convert_skips_unmatched(self):
        from rpa_architect.ir.schema import UIAction
        from rpa_architect.selectors.element_matcher import MatchResult

        matches = [
            MatchResult(
                action=UIAction(action="click", target="Unknown"),
                element=None,
                element_name="S001_Unknown_0",
                confidence=0.0,
                match_method="unmatched",
            ),
        ]

        result = batch_convert(matches)
        assert len(result) == 0

    def test_batch_convert_empty(self):
        result = batch_convert([])
        assert result == {}
