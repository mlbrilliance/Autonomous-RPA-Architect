"""UiPath Python SDK agent scaffold generator.

Generates the minimal set of files required to deploy an agent-based
automation using the UiPath Python SDK (``uipath>=2.10``).
"""

from __future__ import annotations

import json
import re
import textwrap


def _to_snake_case(name: str) -> str:
    """Convert a process name to a valid Python package name (snake_case)."""
    # Replace non-alphanumeric with underscores
    s = re.sub(r"[^a-zA-Z0-9]+", "_", name)
    # Insert underscore between camelCase boundaries
    s = re.sub(r"([a-z0-9])([A-Z])", r"\1_\2", s)
    s = s.lower().strip("_")
    # Collapse consecutive underscores
    s = re.sub(r"_+", "_", s)
    return s or "unnamed_process"


def _vendor_normalizer_main_py(process_name: str) -> str:
    """Real vendor-name normalizer + invoice classifier.

    Combines deterministic regex rules (for the common cases we know
    about) with an optional LLM call via the Anthropic SDK when the
    ANTHROPIC_API_KEY environment variable is set. Falls back cleanly
    to rule-based normalization when the SDK or key is missing so the
    agent always produces a real answer.

    Returns a dict with:
      canonical_name   — normalized vendor name
      category         — invoice category guess (supplies, logistics,
                         software, pharma, r_and_d, unknown)
      confidence       — 0.0..1.0
      method           — "rule" | "llm" | "rule+llm"
      details          — optional LLM reasoning
    """
    # Textwrap dedent won't preserve ''' inside the template, so build
    # the string with a raw f-string and explicit newlines.
    return '''"""Vendor Name Normalizer + Invoice Classifier — real logic.

Deployable as a UiPath Python SDK agent. Runs deterministic rules first
then optionally consults an LLM for uncertain cases.

Ship as-is via:
    uipath pack
    uipath publish

Or invoke locally:
    python main.py ACME-Corp. "Hex bolts and safety gear"
"""

from __future__ import annotations

import json
import os
import re
import sys
from dataclasses import asdict, dataclass
from typing import Any

# The UiPath SDK is an optional dependency when running locally.
try:
    from uipath import UiPath  # type: ignore[import-not-found]
except ImportError:
    UiPath = None  # type: ignore[assignment, misc]


_VENDOR_SUFFIXES = [
    # Longest first so "Inc." doesn't match inside "Incorporated"
    r",?\\s*Incorporated\\.?",
    r",?\\s*Corporation\\.?",
    r",?\\s*Limited\\.?",
    r",?\\s*Company\\.?",
    r",?\\s*L\\.?L\\.?C\\.?",
    r",?\\s*Co\\.?,?\\s*Ltd\\.?",
    r",?\\s*Inc\\.?",
    r",?\\s*Corp\\.?",
    r",?\\s*Ltd\\.?",
    r",?\\s*LLC",
    r",?\\s*plc",
    r",?\\s*GmbH",
    r",?\\s*S\\.?A\\.?",
    r",?\\s*N\\.?V\\.?",
    r",?\\s*B\\.?V\\.?",
    r",?\\s*AG",
    r",?\\s*AB",
    r",?\\s*S\\.A\\.S\\.?",
    r",?\\s*S\\.R\\.L\\.?",
]

# (canonical, pattern) pairs — long patterns first to avoid partial hits.
_KNOWN_ALIASES: list[tuple[str, re.Pattern[str]]] = [
    ("ACME Industrial Supplies",
     re.compile(r"\\bacme\\b.*(industrial|supplies|inc|corp)?", re.I)),
    ("Globex Logistics",
     re.compile(r"\\bglobex\\b.*(logistics|shipping|ltd)?", re.I)),
    ("Initech Software Services",
     re.compile(r"\\binitech\\b.*(software|services|corp)?", re.I)),
    ("Umbrella Pharmaceuticals",
     re.compile(r"\\bumbrella\\b.*(pharma|plc)?", re.I)),
    ("Stark Industries R&D",
     re.compile(r"\\bstark\\b.*(industries|research|r[&\\s-]*d)?", re.I)),
]

# (category, keyword regex) — first match wins.
_CATEGORY_RULES: list[tuple[str, re.Pattern[str]]] = [
    ("supplies",
     re.compile(r"bolt|screw|gear|supply|supplies|hardware|tool|industrial|safety",
                re.I)),
    ("logistics",
     re.compile(r"freight|shipping|logistic|customs|courier|delivery|transport",
                re.I)),
    ("software",
     re.compile(r"software|hosting|cloud|license|saas|subscription|api|support",
                re.I)),
    ("pharma",
     re.compile(r"lab|pharma|drug|consumables|cold-chain|medical|biologic",
                re.I)),
    ("r_and_d",
     re.compile(r"prototype|research|materials.*test|documentation|patent",
                re.I)),
]


@dataclass
class NormalizationResult:
    canonical_name: str
    category: str
    confidence: float
    method: str
    details: str = ""


def strip_corporate_suffix(name: str) -> str:
    """Remove trailing Inc./Ltd./LLC/plc/GmbH/AG etc."""
    cleaned = name.strip()
    for pattern in _VENDOR_SUFFIXES:
        cleaned = re.sub(pattern + r"\\s*$", "", cleaned, flags=re.IGNORECASE)
    # Collapse whitespace and stray commas.
    cleaned = re.sub(r"\\s+", " ", cleaned).strip(" ,.")
    return cleaned


def normalize_vendor_rule_based(name: str) -> tuple[str, float]:
    """Deterministic rule-based normalization. Returns (canonical, confidence)."""
    if not name or not name.strip():
        return ("", 0.0)
    stripped = strip_corporate_suffix(name)
    # Try the known-alias list first — high confidence when matched.
    for canonical, pattern in _KNOWN_ALIASES:
        if pattern.search(name):
            return (canonical, 0.95)
    # Fallback: title-case the stripped form.
    titled = " ".join(w.capitalize() for w in stripped.split())
    return (titled, 0.7)


def classify_rule_based(description: str) -> tuple[str, float]:
    """Rule-based invoice category classification."""
    if not description:
        return ("unknown", 0.3)
    for category, pattern in _CATEGORY_RULES:
        if pattern.search(description):
            return (category, 0.85)
    return ("unknown", 0.3)


def maybe_call_llm(vendor_name: str, description: str) -> dict[str, Any] | None:
    """Optional LLM-assisted normalization via Anthropic SDK.

    Returns None if the SDK or API key is missing, or if any call
    fails. Callers should fall back to the rule-based path when None.
    """
    if not os.environ.get("ANTHROPIC_API_KEY"):
        return None
    try:
        import anthropic  # type: ignore[import-not-found]
    except ImportError:
        return None
    try:
        client = anthropic.Anthropic()
        prompt = (
            f"You are a vendor-name normalizer. Return STRICT JSON with keys "
            f"\\"canonical_name\\", \\"category\\", \\"confidence\\". Category "
            f"must be one of: supplies, logistics, software, pharma, r_and_d, "
            f"unknown. Input vendor name: {vendor_name!r}. Invoice "
            f"description: {description!r}."
        )
        msg = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=256,
            messages=[{"role": "user", "content": prompt}],
        )
        text = "".join(
            block.text for block in msg.content if getattr(block, "type", "") == "text"
        )
        # Extract the first JSON object the model emitted.
        start = text.find("{")
        end = text.rfind("}")
        if start < 0 or end < 0:
            return None
        return json.loads(text[start:end + 1])
    except Exception:
        return None


def normalize(vendor_name: str, description: str = "") -> NormalizationResult:
    """Normalize a vendor name and classify the invoice.

    Uses rule-based logic as the primary path and the optional LLM as
    a supplement when it's available. When both agree, confidence is
    boosted; when they disagree, rule-based wins (deterministic beats
    non-deterministic for audit compliance).
    """
    rule_name, rule_conf = normalize_vendor_rule_based(vendor_name)
    rule_category, rule_cat_conf = classify_rule_based(description)

    llm_data = maybe_call_llm(vendor_name, description)
    if llm_data is None:
        return NormalizationResult(
            canonical_name=rule_name,
            category=rule_category,
            confidence=min(rule_conf, rule_cat_conf),
            method="rule",
        )

    llm_name = str(llm_data.get("canonical_name", rule_name))
    llm_category = str(llm_data.get("category", rule_category))
    llm_conf = float(llm_data.get("confidence", 0.5))

    # Agreement boost.
    names_agree = llm_name.lower() == rule_name.lower()
    cats_agree = llm_category == rule_category
    boosted = min(1.0, (rule_conf + llm_conf) / 2 + (0.05 if names_agree else 0))

    return NormalizationResult(
        canonical_name=rule_name if names_agree else rule_name,  # rule wins ties
        category=rule_category if cats_agree else rule_category,
        confidence=boosted,
        method="rule+llm",
        details=json.dumps({"llm": llm_data, "agreed": names_agree and cats_agree}),
    )


def main(input_data: dict[str, Any] | None = None) -> dict[str, Any]:
    """UiPath agent entry point."""
    input_data = input_data or {}
    vendor = str(input_data.get("vendor_name", ""))
    description = str(input_data.get("description", ""))
    if not vendor:
        return {
            "status": "error",
            "error": "missing vendor_name in input_data",
        }
    result = normalize(vendor, description)
    return {
        "status": "success",
        "process": "''' + process_name + '''",
        **asdict(result),
    }


if __name__ == "__main__":
    # CLI: python main.py "vendor name" "description"
    vendor_arg = sys.argv[1] if len(sys.argv) > 1 else ""
    desc_arg = sys.argv[2] if len(sys.argv) > 2 else ""
    print(json.dumps(main({"vendor_name": vendor_arg, "description": desc_arg}), indent=2))
'''


def _vendor_normalizer_test_py(process_name: str) -> str:
    return '''"""Tests for the vendor normalizer agent."""

from __future__ import annotations

import pytest

from main import (
    NormalizationResult,
    classify_rule_based,
    main,
    normalize,
    normalize_vendor_rule_based,
    strip_corporate_suffix,
)


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("ACME Industrial Supplies, Inc.", "ACME Industrial Supplies"),
        ("Globex Logistics Ltd.", "Globex Logistics"),
        ("Initech Software Services", "Initech Software Services"),
        ("Umbrella Pharmaceuticals plc", "Umbrella Pharmaceuticals"),
        ("Stark Industries R&D", "Stark Industries R&D"),
        ("Acme Corp.", "Acme"),
        ("Foobar GmbH", "Foobar"),
        ("Quux S.A.S.", "Quux"),
    ],
)
def test_strip_corporate_suffix(raw: str, expected: str) -> None:
    assert strip_corporate_suffix(raw) == expected


@pytest.mark.parametrize(
    "raw,canonical,min_conf",
    [
        ("ACME Corp", "ACME Industrial Supplies", 0.9),
        ("acme industrial supplies, inc.", "ACME Industrial Supplies", 0.9),
        ("Globex Logistics Ltd", "Globex Logistics", 0.9),
        ("initech software services", "Initech Software Services", 0.9),
        ("umbrella pharma plc", "Umbrella Pharmaceuticals", 0.9),
        ("Stark R&D", "Stark Industries R&D", 0.9),
    ],
)
def test_known_aliases_normalize_to_canonical(
    raw: str, canonical: str, min_conf: float
) -> None:
    name, conf = normalize_vendor_rule_based(raw)
    assert name == canonical
    assert conf >= min_conf


def test_unknown_vendor_gets_title_case_fallback() -> None:
    name, conf = normalize_vendor_rule_based("foo BAR baz, LLC")
    assert name == "Foo Bar Baz"
    assert 0 < conf < 1.0


@pytest.mark.parametrize(
    "desc,expected_cat",
    [
        ("Hex bolts M8 (box of 100), safety goggles", "supplies"),
        ("Container freight Hamburg to Rotterdam + customs", "logistics"),
        ("Cloud hosting April 2026 with premium support", "software"),
        ("Lab consumables mixed + cold-chain surcharge", "pharma"),
        ("Prototype machining and materials testing", "r_and_d"),
        ("", "unknown"),
        ("Random unrelated text xyz 123", "unknown"),
    ],
)
def test_classify_rule_based(desc: str, expected_cat: str) -> None:
    category, _ = classify_rule_based(desc)
    assert category == expected_cat


def test_normalize_combines_name_and_category() -> None:
    result = normalize("ACME Corp.", "Hex bolts and safety goggles")
    assert isinstance(result, NormalizationResult)
    assert result.canonical_name == "ACME Industrial Supplies"
    assert result.category == "supplies"
    assert result.confidence > 0.8
    assert result.method in ("rule", "rule+llm")


def test_main_entry_returns_success_on_valid_input() -> None:
    out = main({
        "vendor_name": "Globex Logistics Ltd.",
        "description": "Freight Hamburg to Rotterdam",
    })
    assert out["status"] == "success"
    assert out["canonical_name"] == "Globex Logistics"
    assert out["category"] == "logistics"
    assert out["confidence"] > 0.8


def test_main_entry_error_on_missing_vendor() -> None:
    out = main({"description": "no vendor here"})
    assert out["status"] == "error"
    assert "missing vendor_name" in out["error"]
'''


def generate_agent_scaffold(
    process_name: str,
    description: str = "",
    entry_points: list[dict] | None = None,
) -> dict[str, str]:
    """Generate a deployable UiPath Python SDK agent scaffold.

    Produces a complete runnable package:
      - ``main.py`` with real logic (vendor normalizer + classifier,
        rule-based primary path + optional Anthropic LLM supplement)
      - ``test_main.py`` with real pytest assertions against the logic
      - ``uipath.json`` agent manifest
      - ``entry-points.json``
      - ``pyproject.toml`` with anthropic as an optional extra

    The generated package is standalone — ``cd`` into its directory and
    ``python -m pytest`` runs the real tests. It's ready to ship via
    ``uipath pack`` + ``uipath publish``.
    """
    snake_name = _to_snake_case(process_name)
    uipath_json = json.dumps({"functions": {"main": "main.py:main"}}, indent=2)
    ep_list = entry_points or [
        {"name": "main", "module": "main", "function": "main", "type": "function"}
    ]
    entry_points_json = json.dumps({"entryPoints": ep_list}, indent=2)

    pyproject_toml = textwrap.dedent(f"""\
        [project]
        name = "{snake_name}"
        version = "1.0.0"
        description = "{description or process_name + ' agent'}"
        requires-python = ">=3.11"
        dependencies = ["uipath>=2.10"]

        [project.optional-dependencies]
        llm = ["anthropic>=0.40"]
        dev = ["pytest>=8.0"]

        [build-system]
        requires = ["setuptools>=68.0", "wheel"]
        build-backend = "setuptools.build_meta"

        [tool.setuptools]
        py-modules = ["main"]
    """)

    return {
        "uipath.json": uipath_json,
        "entry-points.json": entry_points_json,
        "pyproject.toml": pyproject_toml,
        "main.py": _vendor_normalizer_main_py(process_name),
        "test_main.py": _vendor_normalizer_test_py(process_name),
    }
