"""UI selector robustness scorer.

Scores UiPath UI selectors (XML fragments) for robustness on a 0-100 scale
by applying penalty and bonus heuristics.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field


@dataclass
class SelectorScore:
    """Score result for a single UI selector."""

    element_name: str
    score: int  # 0-100
    penalties: list[str] = field(default_factory=list)
    bonuses: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Scoring helpers
# ---------------------------------------------------------------------------

_ATTR_RE = re.compile(r"""(\w[\w\-]*)=["']([^"']*)["']""")


def _has_attr(selector_xml: str, attr_name: str) -> bool:
    """Check if the selector contains a given attribute (case-insensitive)."""
    for m in _ATTR_RE.finditer(selector_xml):
        if m.group(1).lower() == attr_name.lower():
            return True
    return False


def _attr_value(selector_xml: str, attr_name: str) -> str | None:
    """Return the value of *attr_name* if present, else ``None``."""
    for m in _ATTR_RE.finditer(selector_xml):
        if m.group(1).lower() == attr_name.lower():
            return m.group(2)
    return None


def score_selector(selector_xml: str, element_name: str = "") -> SelectorScore:
    """Score a single UI selector for robustness (0-100).

    Scoring rules
    -------------
    Start at 100, then apply penalties and bonuses.

    **Penalties**
    - ``idx`` attribute present: -20
    - Absolute coordinates (``x=`` or ``y=``): -30
    - ``aaname`` with wildcard ``*``: -10
    - No ``id`` or ``automationid``: -15
    - Window title contains ``*`` wildcard: -5
    - Very short selector (< 20 chars): -10

    **Bonuses**
    - Has ``id`` attribute: +10
    - Has ``automationid``: +10
    - Has ``data-testid``: +10
    - Has ``aria-label``: +5
    - Has CSS ``class``: +5
    - Has ``name`` attribute: +5

    The final score is clamped to 0-100.
    """
    score = 100
    penalties: list[str] = []
    bonuses: list[str] = []

    # --- Penalties ---

    if _has_attr(selector_xml, "idx"):
        score -= 20
        penalties.append("idx attribute present (-20)")

    # Absolute coordinates
    if _has_attr(selector_xml, "x") or _has_attr(selector_xml, "y"):
        score -= 30
        penalties.append("Absolute coordinates detected (-30)")

    # aaname with wildcard
    aaname_val = _attr_value(selector_xml, "aaname")
    if aaname_val is not None and "*" in aaname_val:
        score -= 10
        penalties.append("aaname contains wildcard (-10)")

    # No id or automationid
    has_id = _has_attr(selector_xml, "id")
    has_automationid = _has_attr(selector_xml, "automationid")
    if not has_id and not has_automationid:
        score -= 15
        penalties.append("No id or automationid attribute (-15)")

    # Window title with wildcard
    title_val = _attr_value(selector_xml, "title")
    if title_val is not None and "*" in title_val:
        score -= 5
        penalties.append("Window title contains wildcard (-5)")

    # Very short selector
    if len(selector_xml.strip()) < 20:
        score -= 10
        penalties.append("Very short selector < 20 chars (-10)")

    # --- Bonuses ---

    if has_id:
        score += 10
        bonuses.append("Has id attribute (+10)")

    if has_automationid:
        score += 10
        bonuses.append("Has automationid attribute (+10)")

    if _has_attr(selector_xml, "data-testid"):
        score += 10
        bonuses.append("Has data-testid attribute (+10)")

    if _has_attr(selector_xml, "aria-label"):
        score += 5
        bonuses.append("Has aria-label attribute (+5)")

    if _has_attr(selector_xml, "class"):
        score += 5
        bonuses.append("Has CSS class attribute (+5)")

    if _has_attr(selector_xml, "name"):
        score += 5
        bonuses.append("Has name attribute (+5)")

    # Clamp
    score = max(0, min(100, score))

    return SelectorScore(
        element_name=element_name,
        score=score,
        penalties=penalties,
        bonuses=bonuses,
    )


def score_project_selectors(
    selectors: dict[str, str],
) -> dict[str, SelectorScore]:
    """Score all selectors in a project.

    Parameters
    ----------
    selectors:
        Mapping of element name to selector XML string.

    Returns
    -------
    dict[str, SelectorScore]
        Per-element scores.
    """
    return {
        name: score_selector(xml, element_name=name)
        for name, xml in selectors.items()
    }


def aggregate_score(scores: dict[str, SelectorScore]) -> int:
    """Return the average score across all selectors (0-100).

    Returns 0 when *scores* is empty.
    """
    if not scores:
        return 0
    total = sum(s.score for s in scores.values())
    return round(total / len(scores))
