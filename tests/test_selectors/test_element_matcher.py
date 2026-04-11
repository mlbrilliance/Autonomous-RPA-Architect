"""Tests for element matching (heuristic + LLM fallback)."""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from rpa_architect.ir.schema import UIAction
from rpa_architect.selectors.element_matcher import (
    _jaccard,
    _normalize,
    _tokenize,
    heuristic_match,
    match_actions_to_elements,
)
from rpa_architect.selectors.uipath_converter import HarvestedElement


class TestNormalize:
    """Tests for text normalization."""

    def test_lowercase(self):
        assert _normalize("Hello World") == "hello world"

    def test_strip_punctuation(self):
        assert _normalize("user-name_field") == "user name field"

    def test_collapse_whitespace(self):
        assert _normalize("  hello   world  ") == "hello world"


class TestTokenize:
    """Tests for tokenization."""

    def test_basic(self):
        tokens = _tokenize("Username Field")
        assert tokens == {"username", "field"}

    def test_punctuation_split(self):
        tokens = _tokenize("user_name-input")
        assert "user" in tokens
        assert "name" in tokens
        assert "input" in tokens


class TestJaccard:
    """Tests for Jaccard similarity."""

    def test_identical(self):
        assert _jaccard({"a", "b"}, {"a", "b"}) == 1.0

    def test_disjoint(self):
        assert _jaccard({"a", "b"}, {"c", "d"}) == 0.0

    def test_partial(self):
        assert _jaccard({"a", "b", "c"}, {"a", "b"}) == pytest.approx(2 / 3)

    def test_empty(self):
        assert _jaccard(set(), {"a"}) == 0.0


class TestHeuristicMatch:
    """Tests for heuristic element matching."""

    def test_match_by_id(self):
        actions = [
            ("S001", 0, UIAction(action="type_into", target="Username Field")),
        ]
        elements = [
            HarvestedElement(tag="input", id="username"),
            HarvestedElement(tag="button", id="submit"),
        ]

        matched, unmatched = heuristic_match(actions, elements)
        assert len(matched) == 1
        assert len(unmatched) == 0
        assert matched[0].element is not None
        assert matched[0].element.id == "username"
        assert matched[0].match_method == "heuristic_id"

    def test_match_by_aria_label(self):
        actions = [
            ("S001", 0, UIAction(action="click", target="Submit Button")),
        ]
        elements = [
            HarvestedElement(tag="button", aria_label="Submit Button"),
        ]

        matched, unmatched = heuristic_match(actions, elements)
        assert len(matched) == 1
        assert matched[0].match_method in ("heuristic_aria", "heuristic_type_single")

    def test_match_by_inner_text(self):
        actions = [
            ("S001", 0, UIAction(action="click", target="Sign In")),
        ]
        elements = [
            HarvestedElement(tag="button", inner_text="Sign In"),
        ]

        matched, unmatched = heuristic_match(actions, elements)
        assert len(matched) == 1
        assert matched[0].match_method in ("heuristic_text", "heuristic_type_single")

    def test_match_by_placeholder(self):
        actions = [
            ("S001", 0, UIAction(action="type_into", target="Email Address")),
        ]
        elements = [
            HarvestedElement(tag="input", placeholder="Email Address"),
        ]

        matched, unmatched = heuristic_match(actions, elements)
        assert len(matched) == 1

    def test_match_by_name(self):
        actions = [
            ("S001", 0, UIAction(action="type_into", target="Invoice Number")),
        ]
        elements = [
            HarvestedElement(tag="input", name="invoice_number"),
        ]

        matched, unmatched = heuristic_match(actions, elements)
        assert len(matched) == 1
        assert matched[0].match_method == "heuristic_id"

    def test_no_match(self):
        actions = [
            ("S001", 0, UIAction(action="click", target="Nonexistent Button")),
        ]
        elements = [
            HarvestedElement(tag="input", id="email"),
        ]

        matched, unmatched = heuristic_match(actions, elements)
        assert len(matched) == 0
        assert len(unmatched) == 1

    def test_multiple_matches_uses_best(self):
        actions = [
            ("S001", 0, UIAction(action="type_into", target="Username")),
        ]
        elements = [
            HarvestedElement(tag="input", inner_text="Username hint"),
            HarvestedElement(tag="input", id="username"),  # better match
        ]

        matched, unmatched = heuristic_match(actions, elements)
        assert len(matched) == 1
        assert matched[0].element is not None
        assert matched[0].element.id == "username"

    def test_element_used_once(self):
        """Each element should only be matched to one action."""
        actions = [
            ("S001", 0, UIAction(action="click", target="Submit")),
            ("S001", 1, UIAction(action="click", target="Submit Button")),
        ]
        elements = [
            HarvestedElement(tag="button", id="submit"),
        ]

        matched, unmatched = heuristic_match(actions, elements)
        # First action matches the element; second has no available elements
        assert len(matched) == 1
        assert len(unmatched) == 1

    def test_confidence_tiers(self):
        """Verify confidence is appropriately tiered by match method."""
        actions_id = [("S001", 0, UIAction(action="click", target="Username"))]
        actions_aria = [("S001", 0, UIAction(action="click", target="Login Button"))]
        actions_text = [("S001", 0, UIAction(action="click", target="Sign In"))]

        el_id = [HarvestedElement(tag="input", id="username")]
        el_aria = [HarvestedElement(tag="button", aria_label="Login Button")]
        el_text = [HarvestedElement(tag="button", inner_text="Sign In")]

        m_id, _ = heuristic_match(actions_id, el_id)
        m_aria, _ = heuristic_match(actions_aria, el_aria)
        m_text, _ = heuristic_match(actions_text, el_text)

        # ID match should have highest confidence
        assert m_id[0].confidence > m_aria[0].confidence
        assert m_aria[0].confidence >= m_text[0].confidence


class TestMatchActionsToElements:
    """Tests for the full two-tier matching function."""

    @pytest.mark.asyncio
    async def test_all_matched_heuristically(self):
        actions = [
            ("S001", 0, UIAction(action="type_into", target="Username")),
        ]
        elements = [
            HarvestedElement(tag="input", id="username"),
        ]

        results = await match_actions_to_elements(actions, elements)
        assert len(results) == 1
        assert results[0].element is not None
        assert results[0].match_method.startswith("heuristic")

    @pytest.mark.asyncio
    async def test_no_elements(self):
        actions = [
            ("S001", 0, UIAction(action="click", target="Button")),
        ]

        results = await match_actions_to_elements(actions, [])
        assert len(results) == 1
        assert results[0].match_method == "unmatched"
        assert results[0].confidence == 0.0

    @pytest.mark.asyncio
    async def test_llm_fallback(self):
        """Test that LLM is called for unmatched actions."""
        actions = [
            ("S001", 0, UIAction(action="click", target="Approval Dialog")),
        ]
        elements = [
            HarvestedElement(tag="div", id="modal_container"),
        ]

        mock_llm = AsyncMock()
        mock_llm.generate.return_value = {
            "content": '[{"action_target": "Approval Dialog", "element_index": 0, "confidence": 0.7, "reasoning": "Best match"}]',
        }

        results = await match_actions_to_elements(actions, elements, llm_client=mock_llm)
        assert len(results) == 1
        assert results[0].match_method == "llm"
        assert results[0].element is not None

    @pytest.mark.asyncio
    async def test_no_llm_creates_unmatched(self):
        """Without LLM, unmatched actions should get unmatched results."""
        actions = [
            ("S001", 0, UIAction(action="click", target="Completely Unknown")),
        ]
        elements = [
            HarvestedElement(tag="input", id="email"),
        ]

        results = await match_actions_to_elements(actions, elements, llm_client=None)
        assert len(results) == 1
        assert results[0].match_method == "unmatched"

    @pytest.mark.asyncio
    async def test_llm_error_graceful(self):
        """LLM errors should not crash matching."""
        actions = [
            ("S001", 0, UIAction(action="click", target="Confirmation Popup")),
        ]
        elements = [
            HarvestedElement(tag="div", id="overlay_panel"),
        ]

        mock_llm = AsyncMock()
        mock_llm.generate.side_effect = RuntimeError("API error")

        results = await match_actions_to_elements(actions, elements, llm_client=mock_llm)
        assert len(results) == 1
        # Should still get a result even if LLM fails
        assert results[0].match_method == "unmatched"


class TestTypeAwareMatching:
    """Tests for type-aware matching, ordinal extraction, and single-candidate inference."""

    def test_match_checkbox_by_type(self):
        """action='check' should prefer input[type=checkbox] even without text."""
        actions = [
            ("S001", 0, UIAction(action="check", target="checkbox 1")),
        ]
        elements = [
            HarvestedElement(tag="input", input_type="text", id="name"),
            HarvestedElement(tag="input", input_type="checkbox"),
            HarvestedElement(tag="input", input_type="checkbox"),
        ]

        matched, unmatched = heuristic_match(actions, elements)
        assert len(matched) == 1
        assert len(unmatched) == 0
        assert matched[0].element is not None
        assert matched[0].element.input_type == "checkbox"
        assert matched[0].match_method == "heuristic_ordinal"

    def test_match_checkbox_ordinal_second(self):
        """'checkbox 2' should pick the second checkbox element."""
        actions = [
            ("S001", 0, UIAction(action="check", target="checkbox 2")),
        ]
        elements = [
            HarvestedElement(tag="input", input_type="checkbox"),
            HarvestedElement(tag="input", input_type="checkbox"),
            HarvestedElement(tag="input", input_type="checkbox"),
        ]

        matched, unmatched = heuristic_match(actions, elements)
        assert len(matched) == 1
        assert matched[0].element is elements[1]  # 0-based index 1
        assert matched[0].match_method == "heuristic_ordinal"

    def test_match_english_ordinal(self):
        """'third input field' should pick the third text input."""
        actions = [
            ("S001", 0, UIAction(action="type_into", target="third input field")),
        ]
        elements = [
            HarvestedElement(tag="input", input_type="text"),
            HarvestedElement(tag="input", input_type="text"),
            HarvestedElement(tag="input", input_type="text"),
        ]

        matched, unmatched = heuristic_match(actions, elements)
        assert len(matched) == 1
        assert matched[0].element is elements[2]
        assert matched[0].match_method == "heuristic_ordinal"

    def test_type_aware_prefers_checkbox_over_text(self):
        """action='check' with mixed elements should prefer checkbox type."""
        actions = [
            ("S001", 0, UIAction(action="check", target="Accept Terms")),
        ]
        elements = [
            HarvestedElement(tag="input", input_type="text", id="terms_search"),
            HarvestedElement(tag="input", input_type="checkbox", id="accept"),
        ]

        matched, unmatched = heuristic_match(actions, elements)
        assert len(matched) == 1
        assert matched[0].element is not None
        assert matched[0].element.input_type == "checkbox"

    def test_single_candidate_inference(self):
        """One select element + target mentioning 'dropdown' -> single-candidate match."""
        actions = [
            ("S001", 0, UIAction(action="select_item", target="Status Dropdown")),
        ]
        elements = [
            HarvestedElement(tag="input", input_type="text"),
            HarvestedElement(tag="select", id="status"),
        ]

        matched, unmatched = heuristic_match(actions, elements)
        assert len(matched) == 1
        assert matched[0].element is not None
        assert matched[0].element.tag == "select"
        assert matched[0].match_method == "heuristic_type_single"

    def test_select_item_matches_select_tag(self):
        """select_item action should match <select> tags by type."""
        actions = [
            ("S001", 0, UIAction(action="select_item", target="Dropdown")),
        ]
        elements = [
            HarvestedElement(tag="select", id="dropdown"),
        ]

        matched, unmatched = heuristic_match(actions, elements)
        assert len(matched) == 1
        assert matched[0].element is not None
        assert matched[0].element.tag == "select"

    def test_type_into_matches_number_input(self):
        """type_into should match input[type=number]."""
        actions = [
            ("S001", 0, UIAction(action="type_into", target="Number Input")),
        ]
        elements = [
            HarvestedElement(tag="input", input_type="number"),
        ]

        matched, unmatched = heuristic_match(actions, elements)
        assert len(matched) == 1
        assert matched[0].element is not None
        assert matched[0].element.input_type == "number"
