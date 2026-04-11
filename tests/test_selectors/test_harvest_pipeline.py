"""Tests for the harvest pipeline and selector merging."""

from __future__ import annotations

from unittest.mock import patch

import pytest

from rpa_architect.ir.schema import ProcessIR, SystemInfo
from rpa_architect.selectors.browser_harvester import HarvestConfig
from rpa_architect.selectors.harvest_pipeline import merge_selectors, run_harvest_pipeline


class TestMergeSelectors:
    """Tests for the selector merging logic."""

    def test_placeholder_only(self):
        placeholders = {
            "S001_Username_0": "<html app='TODO_APP' tag='TODO_TAG' aaname='TODO: Username' />",
        }
        result = merge_selectors({}, placeholders)
        assert result == placeholders

    def test_harvested_overrides_placeholder(self):
        placeholders = {
            "S001_Username_0": "<html app='TODO_APP' tag='TODO_TAG' aaname='TODO: Username' />",
        }
        harvested = {
            "S001_Username_0": "<html app='chrome.exe' /><webctrl tag='input' id='username' />",
        }
        result = merge_selectors(harvested, placeholders)
        assert "id='username'" in result["S001_Username_0"]

    def test_known_app_overrides_placeholder(self):
        placeholders = {
            "S001_Username_0": "<html app='TODO_APP' />",
        }
        known = {
            "S001_Username_0": "<html app='chrome.exe' /><webctrl tag='input' name='user' />",
        }
        result = merge_selectors({}, placeholders, known_app=known)
        assert "name='user'" in result["S001_Username_0"]

    def test_harvested_overrides_known_app(self):
        placeholders = {"el1": "placeholder"}
        known = {"el1": "known_app"}
        harvested = {"el1": "harvested"}
        result = merge_selectors(harvested, placeholders, known_app=known)
        assert result["el1"] == "harvested"

    def test_merge_disjoint(self):
        placeholders = {"el1": "p1"}
        known = {"el2": "k2"}
        harvested = {"el3": "h3"}
        result = merge_selectors(harvested, placeholders, known_app=known)
        assert result == {"el1": "p1", "el2": "k2", "el3": "h3"}

    def test_merge_empty(self):
        result = merge_selectors({}, {})
        assert result == {}

    def test_priority_chain(self):
        """Full priority chain: harvested > known > placeholder."""
        placeholders = {"a": "p", "b": "p", "c": "p"}
        known = {"a": "k", "b": "k"}
        harvested = {"a": "h"}

        result = merge_selectors(harvested, placeholders, known_app=known)
        assert result["a"] == "h"  # harvested wins
        assert result["b"] == "k"  # known wins over placeholder
        assert result["c"] == "p"  # placeholder is fallback


class TestRunHarvestPipeline:
    """Tests for the harvest pipeline orchestration."""

    @pytest.mark.asyncio
    async def test_returns_empty_on_exception(self):
        """Should return empty on harvest failure."""
        ir = ProcessIR(process_name="Test")
        config = HarvestConfig(enabled=True)

        with patch.object(
            __import__("rpa_architect.selectors.harvest_pipeline", fromlist=["harvest_selectors_from_browser"]),
            "harvest_selectors_from_browser",
            side_effect=RuntimeError("browser crash"),
        ):
            result = await run_harvest_pipeline(ir, config)
            assert result == {}

    @pytest.mark.asyncio
    async def test_returns_aggregated_selectors(self):
        """Should aggregate selectors from all system reports."""
        from rpa_architect.selectors.browser_harvester import BrowserHarvestReport

        ir = ProcessIR(
            process_name="Test",
            systems=[SystemInfo(name="WebApp", type="web", url="https://example.com")],
        )
        config = HarvestConfig(enabled=True)

        mock_report = BrowserHarvestReport(
            system_name="WebApp",
            selectors={"el1": "<selector1>", "el2": "<selector2>"},
        )

        import rpa_architect.selectors.harvest_pipeline as hp_mod

        with patch.object(
            hp_mod,
            "harvest_selectors_from_browser",
            return_value={"WebApp": mock_report},
        ):
            result = await run_harvest_pipeline(ir, config)
            assert result == {"el1": "<selector1>", "el2": "<selector2>"}

    @pytest.mark.asyncio
    async def test_handles_harvest_exception(self):
        """Should return empty on harvest failure."""
        ir = ProcessIR(process_name="Test")
        config = HarvestConfig(enabled=True)

        import rpa_architect.selectors.harvest_pipeline as hp_mod

        with patch.object(
            hp_mod,
            "harvest_selectors_from_browser",
            side_effect=RuntimeError("browser crash"),
        ):
            result = await run_harvest_pipeline(ir, config)
            assert result == {}

    @pytest.mark.asyncio
    async def test_default_config(self):
        """Should create default config when none provided."""
        ir = ProcessIR(process_name="Test")

        import rpa_architect.selectors.harvest_pipeline as hp_mod

        with patch.object(
            hp_mod,
            "harvest_selectors_from_browser",
            return_value={},
        ) as mock_harvest:
            await run_harvest_pipeline(ir)
            call_args = mock_harvest.call_args
            assert call_args[0][1].enabled is True
