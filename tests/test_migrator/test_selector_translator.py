"""selector_translator: UiPath selector XML → Playwright locator."""

from __future__ import annotations

from rpa_architect.migrator.selector_translator import translate_selector


class TestTranslateSelector:
    def test_prefers_data_testid(self) -> None:
        xml = "<webctrl data-testid='submit' id='btn' name='x' />"
        assert translate_selector(xml) == "page.get_by_test_id('submit')"

    def test_id_when_no_testid(self) -> None:
        xml = "<webctrl id='submit' name='x' />"
        assert translate_selector(xml) == "page.locator('#submit')"

    def test_name_when_no_id(self) -> None:
        xml = "<webctrl name='username' tag='input' />"
        assert translate_selector(xml) == "page.locator('input[name=\"username\"]')"

    def test_aria_label_when_no_id_or_name(self) -> None:
        xml = "<webctrl aaname='Log in' tag='button' />"
        # aaname is UiPath's term for the accessible name / aria-label
        assert translate_selector(xml) == "page.get_by_role('button', name='Log in')"

    def test_inner_text_fallback(self) -> None:
        xml = "<webctrl innertext='Submit Invoice' tag='button' />"
        assert translate_selector(xml) == "page.get_by_text('Submit Invoice')"

    def test_css_selector_attribute(self) -> None:
        xml = "<webctrl css-selector='.btn-primary' />"
        assert translate_selector(xml) == "page.locator('.btn-primary')"

    def test_empty_selector_returns_placeholder(self) -> None:
        assert translate_selector("") == "page.locator('TODO: empty selector')"

    def test_strips_namespace_wrappers(self) -> None:
        xml = "<html app='chrome.exe'/><webctrl id='form'/>"
        # Should still find the id from the webctrl portion.
        result = translate_selector(xml)
        assert "#form" in result

    def test_handles_single_and_double_quotes(self) -> None:
        xml = '<webctrl id="quoted" />'
        assert translate_selector(xml) == "page.locator('#quoted')"
