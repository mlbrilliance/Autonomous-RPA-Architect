"""Tests for the UI selector robustness scorer."""

from __future__ import annotations

import pytest

from rpa_architect.validation.selector_scorer import (
    SelectorScore,
    aggregate_score,
    score_project_selectors,
    score_selector,
)


class TestScoreSelector:
    """Tests for the score_selector function."""

    def test_perfect_selector_scores_high(self):
        sel = '<wnd app="app.exe" title="Main" /><ctrl id="btnOk" automationid="okButton" name="OK" />'
        result = score_selector(sel, "OkButton")
        # Has id (+10), automationid (+10), name (+5) = 125 -> clamped to 100
        assert result.score == 100
        assert result.element_name == "OkButton"

    def test_idx_attribute_penalizes(self):
        sel = '<wnd app="app.exe" title="Main" /><ctrl idx="3" name="item" />'
        result = score_selector(sel, "ListItem")
        assert any("idx" in p for p in result.penalties)
        # No id or automationid: -15, idx: -20, has name: +5 => 100-15-20+5=70
        assert result.score == 70

    def test_id_attribute_gives_bonus(self):
        sel = '<wnd app="app.exe" title="Main" /><ctrl id="myButton" />'
        result = score_selector(sel)
        assert any("id" in b for b in result.bonuses)
        # Has id: +10 => 100+10=110 -> clamped to 100
        assert result.score == 100

    def test_absolute_coordinates_penalty(self):
        sel = '<wnd app="app.exe" title="Main" /><ctrl x="100" y="200" />'
        result = score_selector(sel)
        assert any("coordinates" in p.lower() for p in result.penalties)
        # coords: -30, no id/automationid: -15 => 100-30-15=55
        assert result.score == 55

    def test_wildcard_aaname_penalty(self):
        sel = '<wnd app="app.exe" title="Main" /><ctrl aaname="Item *" id="lst" />'
        result = score_selector(sel)
        assert any("aaname" in p for p in result.penalties)

    def test_wildcard_title_penalty(self):
        sel = '<wnd app="app.exe" title="Main - *" /><ctrl id="btn" />'
        result = score_selector(sel)
        assert any("title" in p.lower() for p in result.penalties)

    def test_very_short_selector(self):
        sel = '<ctrl />'
        result = score_selector(sel)
        assert any("short" in p.lower() for p in result.penalties)

    def test_score_clamped_to_zero(self):
        # Combine many penalties
        sel = '<c idx="1" x="0" y="0" />'
        result = score_selector(sel)
        assert result.score >= 0

    def test_score_clamped_to_100(self):
        sel = '<ctrl id="a" automationid="b" data-testid="c" aria-label="d" class="e" name="f" />'
        result = score_selector(sel)
        assert result.score <= 100

    def test_data_testid_bonus(self):
        sel = '<wnd app="app.exe" title="Main" /><ctrl data-testid="submit-btn" id="btn1" />'
        result = score_selector(sel)
        assert any("data-testid" in b for b in result.bonuses)


class TestScoreProjectSelectors:
    def test_scores_all_selectors(self):
        selectors = {
            "Button1": '<ctrl id="btn1" />',
            "Button2": '<ctrl automationid="btn2" />',
        }
        scores = score_project_selectors(selectors)
        assert "Button1" in scores
        assert "Button2" in scores
        assert scores["Button1"].element_name == "Button1"
        assert scores["Button2"].element_name == "Button2"


class TestAggregateScore:
    def test_averages_correctly(self):
        scores = {
            "A": SelectorScore(element_name="A", score=80, penalties=[], bonuses=[]),
            "B": SelectorScore(element_name="B", score=60, penalties=[], bonuses=[]),
        }
        assert aggregate_score(scores) == 70

    def test_empty_returns_zero(self):
        assert aggregate_score({}) == 0

    def test_single_element(self):
        scores = {
            "X": SelectorScore(element_name="X", score=95, penalties=[], bonuses=[]),
        }
        assert aggregate_score(scores) == 95
