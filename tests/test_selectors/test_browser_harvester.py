"""Tests for browser-based selector harvesting (mocked Playwright)."""

from __future__ import annotations

import os
from unittest.mock import patch

import pytest

from rpa_architect.ir.schema import (
    ProcessIR,
    Step,
    SystemInfo,
    Transaction,
    UIAction,
)
from rpa_architect.selectors.browser_harvester import (
    BrowserHarvestReport,
    HarvestConfig,
    HarvestResult,
    _attrs_to_element,
    _collect_step_actions,
    _collect_system_steps,
    _get_credentials,
)


class TestGetCredentials:
    """Tests for credential lookup from environment variables."""

    def test_credentials_found(self):
        with patch.dict(os.environ, {
            "HARVEST_CRED_INVOICEPORTAL_USER": "admin",
            "HARVEST_CRED_INVOICEPORTAL_PASS": "secret",
        }):
            result = _get_credentials("InvoicePortal", "HARVEST_CRED_")
            assert result == ("admin", "secret")

    def test_credentials_not_found(self):
        result = _get_credentials("NonexistentApp", "HARVEST_CRED_")
        assert result is None

    def test_partial_credentials(self):
        with patch.dict(os.environ, {
            "HARVEST_CRED_APP_USER": "user",
        }, clear=False):
            result = _get_credentials("App", "HARVEST_CRED_")
            assert result is None

    def test_special_chars_in_name(self):
        with patch.dict(os.environ, {
            "HARVEST_CRED_SAP_GUI_USER": "sapuser",
            "HARVEST_CRED_SAP_GUI_PASS": "sappass",
        }):
            result = _get_credentials("SAP GUI", "HARVEST_CRED_")
            assert result == ("sapuser", "sappass")


class TestAttrsToElement:
    """Tests for attribute dict to HarvestedElement conversion."""

    def test_full_attrs(self):
        attrs = {
            "tag": "input",
            "id": "username",
            "name": "user",
            "classes": ["form-control"],
            "aria_label": "Username",
            "aria_role": "textbox",
            "inner_text": "",
            "placeholder": "Enter username",
            "input_type": "text",
            "data_testid": "login-user",
            "bounding_box": {"x": 10, "y": 20, "width": 200, "height": 30},
        }
        el = _attrs_to_element(attrs, "https://example.com")
        assert el.tag == "input"
        assert el.id == "username"
        assert el.name == "user"
        assert el.placeholder == "Enter username"
        assert el.page_url == "https://example.com"

    def test_minimal_attrs(self):
        el = _attrs_to_element({}, "https://example.com")
        assert el.tag == ""
        assert el.id == ""
        assert el.page_url == "https://example.com"


class TestCollectSystemSteps:
    """Tests for collecting steps by system reference."""

    def test_collect_steps(self):
        ir = ProcessIR(
            process_name="Test",
            transactions=[
                Transaction(
                    name="T1",
                    steps=[
                        Step(id="S001", type="open_application", system_ref="WebApp"),
                        Step(id="S002", type="data_operation"),
                        Step(id="S003", type="ui_flow", system_ref="WebApp"),
                        Step(id="S004", type="ui_flow", system_ref="OtherApp"),
                    ],
                ),
            ],
        )
        steps = _collect_system_steps(ir, "WebApp")
        assert len(steps) == 2
        assert steps[0].id == "S001"
        assert steps[1].id == "S003"

    def test_collect_no_match(self):
        ir = ProcessIR(
            process_name="Test",
            transactions=[
                Transaction(
                    name="T1",
                    steps=[
                        Step(id="S001", type="open_application", system_ref="Other"),
                    ],
                ),
            ],
        )
        steps = _collect_system_steps(ir, "WebApp")
        assert len(steps) == 0

    def test_collect_from_substeps(self):
        ir = ProcessIR(
            process_name="Test",
            transactions=[
                Transaction(
                    name="T1",
                    steps=[
                        Step(
                            id="S001",
                            type="decision",
                            substeps=[
                                Step(id="S001a", type="ui_flow", system_ref="WebApp"),
                            ],
                        ),
                    ],
                ),
            ],
        )
        steps = _collect_system_steps(ir, "WebApp")
        assert len(steps) == 1
        assert steps[0].id == "S001a"


class TestCollectStepActions:
    """Tests for collecting actions from steps."""

    def test_collect_actions(self):
        steps = [
            Step(
                id="S001",
                type="ui_flow",
                actions=[
                    UIAction(action="click", target="Button A"),
                    UIAction(action="type_into", target="Field B"),
                ],
            ),
            Step(
                id="S002",
                type="extract_data",
                actions=[
                    UIAction(action="get_text", target="Label C"),
                ],
            ),
        ]
        actions = _collect_step_actions(steps)
        assert len(actions) == 3
        assert actions[0] == ("S001", 0, steps[0].actions[0])
        assert actions[2] == ("S002", 0, steps[1].actions[0])


class TestHarvestConfig:
    """Tests for HarvestConfig defaults."""

    def test_defaults(self):
        config = HarvestConfig()
        assert config.enabled is False
        assert config.headless is True
        assert config.timeout_ms == 30000
        assert config.max_elements_per_page == 200
        assert config.credential_env_prefix == "HARVEST_CRED_"

    def test_custom(self):
        config = HarvestConfig(
            enabled=True,
            headless=False,
            timeout_ms=60000,
        )
        assert config.enabled is True
        assert config.headless is False
        assert config.timeout_ms == 60000


class TestHarvestReport:
    """Tests for harvest report dataclasses."""

    def test_harvest_result_defaults(self):
        result = HarvestResult(step_id="S001")
        assert result.step_id == "S001"
        assert result.elements == []
        assert result.errors == []

    def test_browser_harvest_report(self):
        report = BrowserHarvestReport(system_name="TestApp")
        assert report.system_name == "TestApp"
        assert report.selectors == {}
        assert report.errors == []


class TestHarvestSelectorsFromBrowser:
    """Tests for the main harvest function with mocked Playwright."""

    @pytest.mark.asyncio
    async def test_no_web_systems(self):
        """Should return empty when no web systems with URLs."""
        from rpa_architect.selectors.browser_harvester import harvest_selectors_from_browser

        ir = ProcessIR(
            process_name="Test",
            systems=[SystemInfo(name="Desktop", type="desktop")],
        )
        config = HarvestConfig(enabled=True)

        # No web systems with URLs → short-circuits before launching browser
        reports = await harvest_selectors_from_browser(ir, config)
        assert reports == {}

    @pytest.mark.asyncio
    async def test_function_exists(self):
        """Verify the harvest function is callable."""
        from rpa_architect.selectors.browser_harvester import harvest_selectors_from_browser

        assert callable(harvest_selectors_from_browser)
