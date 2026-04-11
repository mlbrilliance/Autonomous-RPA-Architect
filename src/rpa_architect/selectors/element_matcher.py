"""Match harvested DOM elements to UIActions from the IR.

Uses a two-tier approach:
  1. Heuristic matching (fast, no LLM) — token overlap and attribute matching
  2. LLM fallback — for unmatched actions, uses an LLM to reason about matches
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from rpa_architect.ir.schema import UIAction
from rpa_architect.selectors.uipath_converter import HarvestedElement

if TYPE_CHECKING:
    from rpa_architect.utils.llm_client import LLMClient

logger = logging.getLogger(__name__)


@dataclass
class MatchResult:
    """Result of matching a UIAction to a harvested element."""

    action: UIAction
    element: HarvestedElement | None
    element_name: str
    confidence: float
    match_method: str  # "heuristic_id", "heuristic_aria", "heuristic_text", "llm", "unmatched"
    reasoning: str = ""


def _normalize(text: str) -> str:
    """Normalize text for comparison: lowercase, strip punctuation, collapse whitespace."""
    text = text.lower()
    text = re.sub(r"[^a-z0-9\s]", " ", text)
    return " ".join(text.split())


def _tokenize(text: str) -> set[str]:
    """Split normalized text into tokens."""
    return set(_normalize(text).split())


def _jaccard(set_a: set[str], set_b: set[str]) -> float:
    """Jaccard similarity between two token sets."""
    if not set_a or not set_b:
        return 0.0
    intersection = set_a & set_b
    union = set_a | set_b
    return len(intersection) / len(union)


_ENGLISH_ORDINALS: dict[str, int] = {
    "first": 0, "second": 1, "third": 2, "fourth": 3, "fifth": 4,
    "sixth": 5, "seventh": 6, "eighth": 7, "ninth": 8, "tenth": 9,
    "1st": 0, "2nd": 1, "3rd": 2, "4th": 3, "5th": 4,
}

# Map action verbs to expected input_type / tag values
_ACTION_TYPE_MAP: dict[str, set[str]] = {
    "check": {"checkbox"},
    "uncheck": {"checkbox"},
    "select_item": {"select"},
    "type_into": {"text", "email", "password", "search", "tel", "url", "number", "textarea"},
}

# Map target keywords to expected types
_TARGET_TYPE_KEYWORDS: dict[str, set[str]] = {
    "checkbox": {"checkbox"},
    "radio": {"radio"},
    "dropdown": {"select"},
    "combobox": {"select"},
    "input": {"text", "email", "password", "search", "tel", "url", "number", "textarea"},
    "field": {"text", "email", "password", "search", "tel", "url", "number", "textarea"},
    "button": {"button", "submit"},
}


def _extract_ordinal(target: str) -> int | None:
    """Extract 0-based ordinal index from target string.

    Examples: "checkbox 1" -> 0, "checkbox 2" -> 1, "third input" -> 2.
    """
    normalized = _normalize(target)
    tokens = normalized.split()

    # Check English ordinals
    for tok in tokens:
        if tok in _ENGLISH_ORDINALS:
            return _ENGLISH_ORDINALS[tok]

    # Check trailing digit: "checkbox 1" -> 0
    m = re.search(r"\b(\d+)\s*$", normalized)
    if m:
        return int(m.group(1)) - 1

    return None


def _infer_expected_types(action: UIAction) -> set[str]:
    """Infer expected element types from action verb and target tokens."""
    expected: set[str] = set()

    # From action verb
    expected.update(_ACTION_TYPE_MAP.get(action.action, set()))

    # From target keywords
    for tok in _tokenize(action.target):
        expected.update(_TARGET_TYPE_KEYWORDS.get(tok, set()))

    return expected


def _type_matches(el: HarvestedElement, expected_types: set[str]) -> bool:
    """Check if an element matches any of the expected types."""
    if el.input_type and el.input_type.lower() in expected_types:
        return True
    if el.tag and el.tag.lower() in expected_types:
        return True
    if el.aria_role and el.aria_role.lower() in expected_types:
        return True
    return False


def _jaccard_score_element(
    target_tokens: set[str], el: HarvestedElement,
) -> tuple[float, str]:
    """Score an element against target tokens using Jaccard overlap.

    Returns (best_score, best_method).
    """
    best_score = 0.0
    best_method = "unmatched"

    checks: list[tuple[str, str, str]] = [
        (el.id, "heuristic_id", ""),
        (el.aria_label, "heuristic_aria", ""),
        (el.accessibility_name, "heuristic_aria", ""),
        (el.inner_text[:200] if el.inner_text else "", "heuristic_text", ""),
        (el.placeholder, "heuristic_text", ""),
        (el.name, "heuristic_id", ""),
    ]

    for text, method, _ in checks:
        if not text:
            continue
        overlap = _jaccard(target_tokens, _tokenize(text))
        if overlap > best_score:
            best_score = overlap
            best_method = method

    return best_score, best_method


def _heuristic_match_single(
    action: UIAction,
    elements: list[HarvestedElement],
    threshold: float = 0.3,
) -> tuple[HarvestedElement | None, float, str]:
    """Try to heuristically match a single action to one of the elements.

    Uses a multi-stage strategy:
      1. Type-aware filtering (action verb + target keywords)
      2. Ordinal extraction within type-filtered candidates
      3. Single-candidate inference after type filtering
      4. Jaccard token overlap (type-filtered first, then all elements)

    Returns:
        Tuple of (matched_element, confidence, match_method).
    """
    target_tokens = _tokenize(action.target)
    if not target_tokens:
        return None, 0.0, "unmatched"

    # --- Stage 1: Type-aware filtering ---
    expected_types = _infer_expected_types(action)
    if expected_types:
        typed_candidates = [el for el in elements if _type_matches(el, expected_types)]
    else:
        typed_candidates = []

    # --- Stage 2: Ordinal match within type-filtered candidates ---
    if typed_candidates:
        ordinal = _extract_ordinal(action.target)
        if ordinal is not None and 0 <= ordinal < len(typed_candidates):
            return typed_candidates[ordinal], 0.75, "heuristic_ordinal"

        # --- Stage 3: Single candidate inference ---
        if len(typed_candidates) == 1:
            return typed_candidates[0], 0.70, "heuristic_type_single"

    # --- Stage 4: Jaccard overlap (prefer type-filtered, fallback to all) ---
    search_pools: list[tuple[list[HarvestedElement], float]] = []
    if typed_candidates:
        search_pools.append((typed_candidates, 0.30))  # type bonus
    search_pools.append((elements, 0.0))  # no bonus

    best_element: HarvestedElement | None = None
    best_score = 0.0
    best_method = "unmatched"
    type_bonus = 0.0

    for pool, bonus in search_pools:
        if best_element is not None:
            break  # already found a match in a higher-priority pool
        for el in pool:
            score, method = _jaccard_score_element(target_tokens, el)
            if score + bonus > best_score + type_bonus:
                best_score = score
                best_method = method
                best_element = el
                type_bonus = bonus

    effective_score = best_score + type_bonus

    # Apply threshold
    if effective_score < threshold:
        return None, 0.0, "unmatched"

    # Map method to confidence tiers (with type bonus)
    confidence_map = {
        "heuristic_id": min(0.95, effective_score + 0.45),
        "heuristic_aria": min(0.85, effective_score + 0.35),
        "heuristic_text": min(0.70, effective_score + 0.20),
    }
    confidence = confidence_map.get(best_method, effective_score)

    return best_element, confidence, best_method


def _make_element_name(action: UIAction, step_id: str, index: int) -> str:
    """Generate an element name from action context."""
    raw = f"{step_id}_{action.target}"
    sanitized = re.sub(r"[^a-zA-Z0-9]", "_", raw)
    sanitized = re.sub(r"_+", "_", sanitized).strip("_")
    return f"{sanitized}_{index}"


def heuristic_match(
    actions: list[tuple[str, int, UIAction]],
    elements: list[HarvestedElement],
    threshold: float = 0.3,
) -> tuple[list[MatchResult], list[tuple[str, int, UIAction]]]:
    """Run heuristic matching on all actions.

    Args:
        actions: List of (step_id, index, UIAction) tuples.
        elements: Available harvested elements.
        threshold: Minimum Jaccard similarity to accept a match.

    Returns:
        Tuple of (matched_results, unmatched_actions).
    """
    matched: list[MatchResult] = []
    unmatched: list[tuple[str, int, UIAction]] = []
    used_elements: set[int] = set()

    for step_id, idx, action in actions:
        # Filter out already-used elements
        available = [el for i, el in enumerate(elements) if i not in used_elements]
        element, confidence, method = _heuristic_match_single(action, available, threshold)

        element_name = _make_element_name(action, step_id, idx)

        if element is not None:
            # Mark element as used
            el_idx = elements.index(element)
            used_elements.add(el_idx)
            matched.append(MatchResult(
                action=action,
                element=element,
                element_name=element_name,
                confidence=confidence,
                match_method=method,
                reasoning=f"Token overlap matched via {method}",
            ))
        else:
            unmatched.append((step_id, idx, action))

    return matched, unmatched


async def _llm_match(
    unmatched_actions: list[tuple[str, int, UIAction]],
    elements: list[HarvestedElement],
    llm_client: LLMClient,
) -> list[MatchResult]:
    """Use LLM to match remaining unmatched actions to elements.

    Args:
        unmatched_actions: Actions that heuristic matching couldn't resolve.
        elements: All harvested elements (some may already be matched).
        llm_client: LLM client for inference.

    Returns:
        List of MatchResult objects from LLM matching.
    """
    if not unmatched_actions or not elements:
        return []

    # Build element descriptions for the prompt
    element_descs = []
    for i, el in enumerate(elements):
        desc_parts = [f"[{i}] tag={el.tag}"]
        if el.id:
            desc_parts.append(f"id='{el.id}'")
        if el.aria_label:
            desc_parts.append(f"aria-label='{el.aria_label}'")
        if el.inner_text:
            desc_parts.append(f"text='{el.inner_text[:100]}'")
        if el.placeholder:
            desc_parts.append(f"placeholder='{el.placeholder}'")
        if el.name:
            desc_parts.append(f"name='{el.name}'")
        if el.input_type:
            desc_parts.append(f"type='{el.input_type}'")
        element_descs.append(", ".join(desc_parts))

    # Build action descriptions
    action_descs = []
    for step_id, idx, action in unmatched_actions:
        action_descs.append(f"- {step_id}[{idx}]: action={action.action}, target='{action.target}'")

    prompt = (
        "Match these UI actions to the available DOM elements.\n\n"
        "Actions (unmatched):\n" + "\n".join(action_descs) + "\n\n"
        "Available elements:\n" + "\n".join(element_descs) + "\n\n"
        "Return a JSON array of matches:\n"
        '[{"action_target": "...", "element_index": N, "confidence": 0.0-1.0, "reasoning": "..."}]\n'
        "Use element_index -1 if no element matches. Only return the JSON array."
    )

    try:
        response = await llm_client.generate(prompt)
        content = response.get("content", "")
        # Extract JSON from response
        json_match = re.search(r"\[.*\]", content, re.DOTALL)
        if not json_match:
            logger.warning("LLM match response did not contain valid JSON array")
            return []

        llm_matches: list[dict[str, Any]] = json.loads(json_match.group())
    except Exception as exc:
        logger.warning("LLM matching failed: %s", exc)
        return []

    results: list[MatchResult] = []
    for step_id, idx, action in unmatched_actions:
        element_name = _make_element_name(action, step_id, idx)
        # Find LLM match for this action
        llm_match_data = None
        for m in llm_matches:
            if m.get("action_target") == action.target:
                llm_match_data = m
                break

        if llm_match_data and llm_match_data.get("element_index", -1) >= 0:
            el_idx = llm_match_data["element_index"]
            if 0 <= el_idx < len(elements):
                results.append(MatchResult(
                    action=action,
                    element=elements[el_idx],
                    element_name=element_name,
                    confidence=min(float(llm_match_data.get("confidence", 0.5)), 0.80),
                    match_method="llm",
                    reasoning=llm_match_data.get("reasoning", "LLM match"),
                ))
                continue

        # Still unmatched
        results.append(MatchResult(
            action=action,
            element=None,
            element_name=element_name,
            confidence=0.0,
            match_method="unmatched",
            reasoning="No match found",
        ))

    return results


async def match_actions_to_elements(
    actions: list[tuple[str, int, UIAction]],
    elements: list[HarvestedElement],
    llm_client: LLMClient | None = None,
) -> list[MatchResult]:
    """Match UIActions to harvested DOM elements using two-tier strategy.

    Tier 1: Heuristic matching (fast, no LLM cost).
    Tier 2: LLM fallback for unmatched actions.

    Args:
        actions: List of (step_id, index, UIAction) tuples.
        elements: Harvested elements from the browser.
        llm_client: Optional LLM client for tier-2 matching.

    Returns:
        List of MatchResult objects for all actions.
    """
    if not elements:
        return [
            MatchResult(
                action=action,
                element=None,
                element_name=_make_element_name(action, step_id, idx),
                confidence=0.0,
                match_method="unmatched",
                reasoning="No elements available",
            )
            for step_id, idx, action in actions
        ]

    # Tier 1: Heuristic matching
    matched, unmatched = heuristic_match(actions, elements)

    # Tier 2: LLM fallback
    if unmatched and llm_client:
        llm_results = await _llm_match(unmatched, elements, llm_client)
        if llm_results:
            matched.extend(llm_results)
        else:
            # LLM returned no results (e.g., error) — create unmatched entries
            for step_id, idx, action in unmatched:
                matched.append(MatchResult(
                    action=action,
                    element=None,
                    element_name=_make_element_name(action, step_id, idx),
                    confidence=0.0,
                    match_method="unmatched",
                    reasoning="LLM matching returned no results",
                ))
    elif unmatched:
        # No LLM available — create unmatched results
        for step_id, idx, action in unmatched:
            matched.append(MatchResult(
                action=action,
                element=None,
                element_name=_make_element_name(action, step_id, idx),
                confidence=0.0,
                match_method="unmatched",
                reasoning="No heuristic match and no LLM available",
            ))

    return matched
