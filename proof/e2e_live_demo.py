#!/usr/bin/env python3
"""End-to-end live proof: real website -> selectors -> REFramework -> UiPath project.

Navigates to https://the-internet.herokuapp.com/ via Playwright, harvests real
DOM elements, builds UiPath selectors, generates a complete REFramework project
with coded C# workflows, lints everything, and writes a comprehensive report.

Usage:
    python3 proof/e2e_live_demo.py

No LLM API keys or UiPath installation required.
"""

from __future__ import annotations

import asyncio
import importlib.util
import json
import logging
import os
import sys
import time
from dataclasses import asdict, dataclass, field, fields as dc_fields
from enum import Enum
from pathlib import Path
from typing import Any

# ---------------------------------------------------------------------------
# Bootstrap: ensure rpa_architect is importable
# ---------------------------------------------------------------------------
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
_SRC = _PROJECT_ROOT / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

# ---------------------------------------------------------------------------
# Output paths
# ---------------------------------------------------------------------------
OUTPUT_DIR = Path(__file__).resolve().parent / "e2e_output"
SCREENSHOTS_DIR = OUTPUT_DIR / "screenshots"
HARVEST_DIR = OUTPUT_DIR / "harvested_data"
SELECTORS_DIR = OUTPUT_DIR / "selectors"
PROJECT_DIR = OUTPUT_DIR / "uipath_project"
REPORTS_DIR = OUTPUT_DIR / "reports"

TARGET_URL = "https://the-internet.herokuapp.com"

# ---------------------------------------------------------------------------
# Phase tracking
# ---------------------------------------------------------------------------

@dataclass
class PhaseResult:
    name: str
    passed: bool = False
    duration_s: float = 0.0
    detail: str = ""
    error: str | None = None


PHASE_RESULTS: list[PhaseResult] = []


def _run_phase(name: str):
    """Decorator factory for phase functions."""
    def decorator(fn):
        async def wrapper(*args, **kwargs):
            pr = PhaseResult(name=name)
            t0 = time.monotonic()
            try:
                result = await fn(*args, **kwargs)
                pr.passed = True
                pr.detail = str(result) if result else "OK"
                return result
            except Exception as exc:
                pr.error = f"{type(exc).__name__}: {exc}"
                logger.error("Phase '%s' FAILED: %s", name, pr.error)
                return None
            finally:
                pr.duration_s = round(time.monotonic() - t0, 2)
                PHASE_RESULTS.append(pr)
                status = "PASS" if pr.passed else "FAIL"
                logger.info(
                    "Phase %-40s [%s]  %.1fs",
                    name, status, pr.duration_s,
                )
        return wrapper
    return decorator


# ---------------------------------------------------------------------------
# JSON serialiser for dataclasses / Path / Enum
# ---------------------------------------------------------------------------

def _serializable(obj: Any) -> Any:
    """Recursively convert to JSON-safe types."""
    if obj is None or isinstance(obj, (str, int, float, bool)):
        return obj
    if isinstance(obj, Path):
        return str(obj)
    if isinstance(obj, Enum):
        return obj.value
    if hasattr(obj, "__dataclass_fields__"):
        return {f.name: _serializable(getattr(obj, f.name)) for f in dc_fields(obj)}
    if hasattr(obj, "model_dump"):  # Pydantic
        return obj.model_dump()
    if isinstance(obj, dict):
        return {str(k): _serializable(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_serializable(v) for v in obj]
    return str(obj)


def _dump_json(data: Any, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w") as f:
        json.dump(_serializable(data), f, indent=2, default=str)


# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-7s  %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("e2e_proof")

# File handler added once output dir exists
_file_handler: logging.FileHandler | None = None


def _setup_file_logging() -> None:
    global _file_handler
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    _file_handler = logging.FileHandler(OUTPUT_DIR / "console.log", mode="w")
    _file_handler.setFormatter(
        logging.Formatter("%(asctime)s  %(levelname)-7s  %(message)s", "%H:%M:%S")
    )
    logging.getLogger().addHandler(_file_handler)


# ============================================================================
# PHASE 0 — Setup
# ============================================================================

@_run_phase("Phase 0: Setup")
async def phase_0_setup() -> str:
    for d in (SCREENSHOTS_DIR, HARVEST_DIR, SELECTORS_DIR, REPORTS_DIR,
              PROJECT_DIR / "Framework", PROJECT_DIR / "Data",
              PROJECT_DIR / ".objects", PROJECT_DIR / "Tests"):
        d.mkdir(parents=True, exist_ok=True)
    _setup_file_logging()

    # Check playwright
    if importlib.util.find_spec("playwright") is None:
        raise RuntimeError(
            "Playwright not installed. Run: pip install playwright && "
            "python3 -m playwright install chromium"
        )
    return "Directories created, playwright available"


# ============================================================================
# PHASE 1 — Build ProcessIR
# ============================================================================

@_run_phase("Phase 1: Build ProcessIR")
async def phase_1_build_ir():
    from rpa_architect.ir.schema import (
        ProcessIR, SystemInfo, Transaction, Step, UIAction,
    )

    ir = ProcessIR(
        process_name="TheInternetAutomation",
        process_type="transactional",
        description="End-to-end proof: automate interactions on the-internet.herokuapp.com",
        systems=[
            SystemInfo(
                name="TheInternet", type="web",
                url=TARGET_URL,
                login_required=False,
            ),
        ],
        credentials=[],
        transactions=[
            Transaction(
                name="InteractWithTestPages",
                steps=[
                    Step(
                        id="S001", type="navigate", system_ref="TheInternet",
                        description="Click Add Element button",
                        parameters={"url": f"{TARGET_URL}/add_remove_elements/"},
                        actions=[UIAction(action="click", target="Add Element", confidence=0.5)],
                    ),
                    Step(
                        id="S002", type="ui_flow", system_ref="TheInternet",
                        description="Toggle checkboxes",
                        parameters={"url": f"{TARGET_URL}/checkboxes"},
                        actions=[
                            UIAction(action="check", target="checkbox 1", confidence=0.5),
                            UIAction(action="check", target="checkbox 2", confidence=0.5),
                        ],
                    ),
                    Step(
                        id="S003", type="ui_flow", system_ref="TheInternet",
                        description="Select dropdown option",
                        parameters={"url": f"{TARGET_URL}/dropdown"},
                        actions=[UIAction(action="select_item", target="Dropdown", value="Option 1", confidence=0.5)],
                    ),
                    Step(
                        id="S004", type="ui_flow", system_ref="TheInternet",
                        description="Type into number input",
                        parameters={"url": f"{TARGET_URL}/inputs"},
                        actions=[UIAction(action="type_into", target="Number Input", value="42", confidence=0.5)],
                    ),
                    Step(
                        id="S005", type="ui_flow", system_ref="TheInternet",
                        description="Type text and read result",
                        parameters={"url": f"{TARGET_URL}/key_presses"},
                        actions=[
                            UIAction(action="type_into", target="Input Field", value="Hello World", confidence=0.5),
                            UIAction(action="get_text", target="Result", confidence=0.5),
                        ],
                    ),
                ],
                business_rules=[],
            ),
        ],
        exception_categories=[],
        config={"MaxRetryNumber": "3", "LogLevel": "Info"},
    )

    # Validate round-trip
    ir.model_validate(ir.model_dump())

    _dump_json(ir.model_dump(), OUTPUT_DIR / "process_ir.json")

    total_actions = sum(
        len(a.actions) for t in ir.transactions for a in t.steps
    )
    logger.info(
        "IR: %d system(s), %d transaction(s), %d step(s), %d action(s)",
        len(ir.systems),
        len(ir.transactions),
        sum(len(t.steps) for t in ir.transactions),
        total_actions,
    )
    return ir


# ============================================================================
# PHASE 2 — Browser Harvest (Playwright)
# ============================================================================

@_run_phase("Phase 2: Browser Harvest")
async def phase_2_browser_harvest(ir):
    from rpa_architect.selectors.browser_harvester import (
        HarvestConfig, harvest_selectors_from_browser,
    )

    config = HarvestConfig(
        enabled=True,
        headless=True,
        timeout_ms=30000,
        screenshot_dir=SCREENSHOTS_DIR,
        max_elements_per_page=200,
    )

    reports = await harvest_selectors_from_browser(ir, config, llm_client=None)

    # Save reports
    for sys_name, report in reports.items():
        _dump_json(report, HARVEST_DIR / f"{sys_name}_report.json")
        for result in report.results:
            _dump_json(result, HARVEST_DIR / f"{result.step_id}_elements.json")

    # Log summary
    total_elements = 0
    total_screenshots = 0
    for sys_name, report in reports.items():
        for r in report.results:
            total_elements += len(r.elements)
            if r.screenshot_path:
                total_screenshots += 1
        logger.info(
            "System '%s': %d results, %d selectors, %d errors",
            sys_name, len(report.results), len(report.selectors), len(report.errors),
        )

    logger.info(
        "Harvest totals: %d elements, %d screenshots, %d selectors",
        total_elements, total_screenshots,
        sum(len(r.selectors) for r in reports.values()),
    )
    return reports


# ============================================================================
# PHASE 3 — Element Matching (per-step heuristic + enhanced fallbacks)
# ============================================================================

def _enhanced_fallback_match(
    step_id: str, idx: int, action, elements, used_indices: set,
):
    """Enhanced fallback matching for elements the heuristic misses.

    Strategies (applied in order):
    1. Semantic role: action type implies element type (checkbox→input[checkbox])
    2. Ordinal position: "checkbox 1" → first checkbox on page
    3. Single-candidate: only one element of matching tag/type → auto-match
    4. ID substring: action target partially matches element id
    """
    import re
    from rpa_architect.selectors.element_matcher import MatchResult

    target_lower = action.target.lower()
    target_tokens = set(re.sub(r"[^a-z0-9\s]", " ", target_lower).split())

    available = [(i, el) for i, el in enumerate(elements) if i not in used_indices]
    if not available:
        return None

    element_name = re.sub(r"[^a-zA-Z0-9]", "_", f"{step_id}_{action.target}")
    element_name = re.sub(r"_+", "_", element_name).strip("_") + f"_{idx}"

    # Strategy 1: Semantic role — action type matches element input_type
    role_map = {
        "check": "checkbox", "uncheck": "checkbox",
        "type_into": None, "get_text": None,
        "click": None, "select_item": None,
    }
    expected_type = role_map.get(action.action)

    # Also infer from target tokens
    if "checkbox" in target_tokens or "check" in target_tokens:
        expected_type = "checkbox"
    elif "number" in target_tokens:
        expected_type = "number"
    elif "input" in target_tokens or "field" in target_tokens or "text" in target_tokens:
        expected_type = "__input__"  # any input
    elif "result" in target_tokens or "output" in target_tokens:
        expected_type = "__id_match__"

    # Strategy 2: Ordinal extraction ("checkbox 1" → index 0)
    ordinal = None
    for tok in target_tokens:
        if tok.isdigit():
            ordinal = int(tok) - 1  # "1" → index 0
            break
    ordinal_map = {"first": 0, "second": 1, "third": 2, "fourth": 3, "fifth": 4}
    for word, oidx in ordinal_map.items():
        if word in target_tokens:
            ordinal = oidx
            break

    # Filter candidates by semantic role
    if expected_type == "__input__":
        candidates = [(i, el) for i, el in available
                       if el.tag == "input" and el.input_type in ("text", "password", "email", "search", "number", "")]
    elif expected_type == "__id_match__":
        candidates = [(i, el) for i, el in available
                       if any(t in (el.id or "").lower() for t in target_tokens if len(t) > 2)]
    elif expected_type:
        candidates = [(i, el) for i, el in available
                       if el.input_type == expected_type or el.aria_role == expected_type]
    else:
        candidates = list(available)

    if not candidates:
        candidates = list(available)

    # Apply ordinal selection
    if ordinal is not None and expected_type:
        typed = [(i, el) for i, el in available
                  if (expected_type in (el.input_type, el.aria_role))
                  or (expected_type == "__input__" and el.tag == "input")]
        if 0 <= ordinal < len(typed):
            chosen_i, chosen_el = typed[ordinal]
            return MatchResult(
                action=action, element=chosen_el, element_name=element_name,
                confidence=0.75, match_method="enhanced_ordinal",
                reasoning=f"Ordinal '{ordinal+1}' matched {expected_type} element",
            ), chosen_i

    # Strategy 3: Single candidate of matching type
    if len(candidates) == 1:
        chosen_i, chosen_el = candidates[0]
        return MatchResult(
            action=action, element=chosen_el, element_name=element_name,
            confidence=0.70, match_method="enhanced_single_candidate",
            reasoning=f"Only matching element on page: {chosen_el.tag}[{chosen_el.input_type}]",
        ), chosen_i

    # Strategy 4: ID substring match
    for ci, cel in candidates:
        if cel.id:
            id_tokens = set(re.sub(r"[^a-z0-9]", " ", cel.id.lower()).split())
            overlap = target_tokens & id_tokens
            if overlap:
                return MatchResult(
                    action=action, element=cel, element_name=element_name,
                    confidence=0.80, match_method="enhanced_id_substring",
                    reasoning=f"ID '{cel.id}' overlaps with target tokens {overlap}",
                ), ci

    # Strategy 5: If action is type_into and there's exactly one input, use it
    if action.action in ("type_into", "get_text"):
        inputs = [(i, el) for i, el in available if el.tag in ("input", "textarea")]
        if len(inputs) == 1:
            chosen_i, chosen_el = inputs[0]
            return MatchResult(
                action=action, element=chosen_el, element_name=element_name,
                confidence=0.65, match_method="enhanced_sole_input",
                reasoning=f"Only input element on page for {action.action}",
            ), chosen_i

    return None


@_run_phase("Phase 3: Element Matching")
async def phase_3_element_matching(ir, reports):
    from rpa_architect.selectors.element_matcher import heuristic_match, MatchResult

    # Build per-step element map from harvest results
    step_elements: dict[str, list] = {}
    for report in reports.values():
        for result in report.results:
            step_elements[result.step_id] = result.elements

    all_matched: list[MatchResult] = []
    all_unmatched: list[tuple] = []
    total_actions = 0

    for txn in ir.transactions:
        for step in txn.steps:
            step_actions = [(step.id, idx, action) for idx, action in enumerate(step.actions)]
            total_actions += len(step_actions)
            elements = step_elements.get(step.id, [])

            if not elements:
                all_unmatched.extend(step_actions)
                continue

            # Tier 1: Standard heuristic matching (per-step)
            matched, unmatched = heuristic_match(step_actions, elements, threshold=0.2)
            all_matched.extend(matched)

            # Tier 2: Enhanced fallback for remaining unmatched
            used_indices: set[int] = set()
            for m in matched:
                if m.element is not None and m.element in elements:
                    used_indices.add(elements.index(m.element))

            still_unmatched = []
            for sid, idx, action in unmatched:
                result = _enhanced_fallback_match(sid, idx, action, elements, used_indices)
                if result:
                    match_result, el_idx = result
                    used_indices.add(el_idx)
                    all_matched.append(match_result)
                    logger.info(
                        "  Enhanced match: '%s' -> %s (%s, %.2f)",
                        action.target, match_result.match_method,
                        match_result.element.tag if match_result.element else "?",
                        match_result.confidence,
                    )
                else:
                    still_unmatched.append((sid, idx, action))

            all_unmatched.extend(still_unmatched)

    match_data = {
        "total_actions": total_actions,
        "matched_count": len(all_matched),
        "unmatched_count": len(all_unmatched),
        "match_rate_pct": round(100 * len(all_matched) / max(total_actions, 1), 1),
        "matches": [
            {
                "element_name": m.element_name,
                "action_target": m.action.target,
                "action_type": m.action.action,
                "confidence": m.confidence,
                "match_method": m.match_method,
                "reasoning": m.reasoning,
                "element_tag": m.element.tag if m.element else None,
                "element_id": m.element.id if m.element else None,
                "element_type": m.element.input_type if m.element else None,
                "element_text": (m.element.inner_text[:80] if m.element and m.element.inner_text else None),
            }
            for m in all_matched
        ],
        "unmatched": [
            {"step_id": s, "index": i, "action_target": a.target, "action_type": a.action}
            for s, i, a in all_unmatched
        ],
    }
    _dump_json(match_data, HARVEST_DIR / "match_results.json")

    logger.info(
        "Matched: %d/%d (%.0f%%), unmatched: %d",
        len(all_matched), total_actions, match_data["match_rate_pct"], len(all_unmatched),
    )
    return all_matched, all_unmatched


# ============================================================================
# PHASE 4 — UiPath Selector Conversion
# ============================================================================

@_run_phase("Phase 4: Selector Conversion")
async def phase_4_selector_conversion(ir, matched, unmatched):
    from rpa_architect.selectors.uipath_converter import batch_convert, convert_to_uipath_selector
    from rpa_architect.selectors.placeholder_gen import generate_placeholder_selectors
    from rpa_architect.selectors.harvest_pipeline import merge_selectors

    # Convert matched elements to selectors
    harvested_selectors = batch_convert(matched, app_name="chrome.exe")

    # Per-element details with stability scores
    selector_details = {}
    for m in matched:
        if m.element is not None:
            sel_xml, stability = convert_to_uipath_selector(m.element, "chrome.exe")
            selector_details[m.element_name] = {
                "selector_xml": sel_xml,
                "stability_score": stability,
                "match_method": m.match_method,
                "match_confidence": m.confidence,
                "source_element": {
                    "tag": m.element.tag,
                    "id": m.element.id,
                    "name": m.element.name,
                    "aria_label": m.element.aria_label,
                    "inner_text": m.element.inner_text[:80] if m.element.inner_text else "",
                },
            }

    # Generate placeholders for unmatched
    placeholders = generate_placeholder_selectors(ir)

    # Merge: harvested overrides placeholders
    all_selectors = merge_selectors(
        harvested=harvested_selectors,
        placeholders=placeholders,
    )

    _dump_json(all_selectors, SELECTORS_DIR / "all_selectors.json")
    _dump_json(selector_details, SELECTORS_DIR / "selector_details.json")

    logger.info(
        "Selectors: %d harvested, %d placeholders, %d total merged",
        len(harvested_selectors), len(placeholders), len(all_selectors),
    )
    return all_selectors, selector_details, matched


# ============================================================================
# PHASE 4b — LIVE SELECTOR VALIDATION (prove selectors actually work)
# ============================================================================

@_run_phase("Phase 4b: Live Selector Validation")
async def phase_4b_validate_selectors_live(ir, selectors, matched):
    """Re-open browser, navigate to each page, and verify selectors find elements.

    This is the KEY proof: the generated UiPath selectors actually resolve to
    real DOM elements on the live page. We translate the UiPath selector XML
    back to CSS/attribute queries and verify element existence, then optionally
    click/type to prove interactivity.
    """
    import re
    from playwright.async_api import async_playwright

    # Parse UiPath selector XML to extract attributes for Playwright querying
    def _uipath_selector_to_css(sel_xml: str) -> str | None:
        """Convert UiPath webctrl selector to a CSS selector for Playwright."""
        # Extract attributes from <webctrl ... />
        webctrl_match = re.search(r"<webctrl\s+([^/]*)/?>", sel_xml)
        if not webctrl_match:
            return None
        attrs_str = webctrl_match.group(1)

        tag = "*"
        css_parts = []
        for attr_match in re.finditer(r"(\w[\w-]*)='([^']*)'", attrs_str):
            attr_name, attr_val = attr_match.group(1), attr_match.group(2)
            if attr_name == "tag":
                tag = attr_val
            elif attr_name == "id":
                css_parts.append(f"#{attr_val}")
            elif attr_name == "name":
                css_parts.append(f"[name='{attr_val}']")
            elif attr_name == "type":
                css_parts.append(f"[type='{attr_val}']")
            elif attr_name == "aaname":
                pass  # accessibility name — can't directly query via CSS
            elif attr_name == "innertext":
                pass  # handled separately with text selector
            elif attr_name == "class":
                css_parts.append(f".{attr_val}")

        if tag != "*" and css_parts:
            return tag + "".join(css_parts)
        elif css_parts:
            return "".join(css_parts)
        elif tag != "*":
            return tag
        return None

    # Build per-step mapping: step_id -> (url, list of (element_name, selector, action))
    step_map: dict[str, dict] = {}
    for txn in ir.transactions:
        for step in txn.steps:
            step_map[step.id] = {
                "url": step.parameters.get("url", ""),
                "elements": [],
            }

    for m in matched:
        step_id = m.element_name.split("_")[0]
        sel_xml = selectors.get(m.element_name, "")
        if step_id in step_map and sel_xml and "TODO" not in sel_xml:
            step_map[step_id]["elements"].append({
                "name": m.element_name,
                "selector": sel_xml,
                "action": m.action,
            })

    validation_results = []
    total_validated = 0
    total_found = 0
    total_interacted = 0

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page(viewport={"width": 1920, "height": 1080})

        for step_id, step_info in sorted(step_map.items()):
            url = step_info["url"]
            if not url or not step_info["elements"]:
                continue

            try:
                await page.goto(url, wait_until="networkidle", timeout=15000)
            except Exception as exc:
                logger.warning("  Validation: failed to navigate to %s: %s", url, exc)
                continue

            for elem_info in step_info["elements"]:
                total_validated += 1
                result = {
                    "element_name": elem_info["name"],
                    "selector_xml": elem_info["selector"],
                    "page_url": url,
                    "found": False,
                    "interacted": False,
                    "css_used": "",
                    "error": None,
                }

                css = _uipath_selector_to_css(elem_info["selector"])
                result["css_used"] = css or ""

                if not css:
                    # Try text-based lookup for innertext selectors
                    innertext_match = re.search(r"innertext='([^']+)'", elem_info["selector"])
                    if innertext_match:
                        text = innertext_match.group(1)
                        try:
                            el = page.locator(f"text='{text}'").first
                            if await el.count() > 0:
                                result["found"] = True
                                total_found += 1
                                result["css_used"] = f"text='{text}'"
                        except Exception:
                            pass
                    validation_results.append(result)
                    continue

                try:
                    el = page.locator(css).first
                    count = await el.count()
                    if count > 0:
                        result["found"] = True
                        total_found += 1

                        # Try to interact based on action type
                        action_type = elem_info["action"].action
                        try:
                            if action_type == "click":
                                await el.click(timeout=3000)
                                result["interacted"] = True
                                total_interacted += 1
                            elif action_type == "type_into":
                                await el.fill(elem_info["action"].value or "test", timeout=3000)
                                result["interacted"] = True
                                total_interacted += 1
                            elif action_type == "select_item":
                                await el.select_option(label=elem_info["action"].value or "", timeout=3000)
                                result["interacted"] = True
                                total_interacted += 1
                            elif action_type in ("check", "uncheck"):
                                await el.check(timeout=3000)
                                result["interacted"] = True
                                total_interacted += 1
                            elif action_type == "get_text":
                                text = await el.inner_text(timeout=3000)
                                result["interacted"] = True
                                result["extracted_text"] = text[:100]
                                total_interacted += 1
                        except Exception as exc:
                            result["interaction_error"] = str(exc)[:200]
                    else:
                        result["error"] = "Element not found on page"
                except Exception as exc:
                    result["error"] = str(exc)[:200]

                validation_results.append(result)
                status = "FOUND+INTERACTED" if result["interacted"] else ("FOUND" if result["found"] else "NOT FOUND")
                logger.info(
                    "  Validate: %-30s %s (css: %s)",
                    elem_info["name"], status, css,
                )

        # Take a validation screenshot showing actual interaction
        if total_interacted > 0:
            await page.screenshot(
                path=str(SCREENSHOTS_DIR / "validation_proof.png"),
                full_page=False,
            )

        await browser.close()

    _dump_json({
        "total_validated": total_validated,
        "total_found": total_found,
        "total_interacted": total_interacted,
        "find_rate_pct": round(100 * total_found / max(total_validated, 1), 1),
        "interact_rate_pct": round(100 * total_interacted / max(total_validated, 1), 1),
        "results": validation_results,
    }, REPORTS_DIR / "selector_validation.json")

    logger.info(
        "Selector validation: %d/%d found (%.0f%%), %d/%d interacted (%.0f%%)",
        total_found, total_validated,
        100 * total_found / max(total_validated, 1),
        total_interacted, total_validated,
        100 * total_interacted / max(total_validated, 1),
    )
    return total_validated, total_found, total_interacted, validation_results


# ============================================================================
# PHASE 5 — Selector Quality Scoring
# ============================================================================

@_run_phase("Phase 5: Selector Scoring")
async def phase_5_selector_scoring(selectors):
    from rpa_architect.validation.selector_scorer import score_project_selectors, aggregate_score

    scores = score_project_selectors(selectors)
    overall = aggregate_score(scores)

    score_data = {
        "aggregate_score": overall,
        "element_scores": {
            name: {
                "score": s.score,
                "penalties": s.penalties,
                "bonuses": s.bonuses,
            }
            for name, s in scores.items()
        },
    }
    _dump_json(score_data, REPORTS_DIR / "selector_scores.json")

    logger.info("Selector quality: aggregate %d/100 across %d selectors", overall, len(scores))
    return scores, overall


# ============================================================================
# PHASE 6 — REFramework XAML Generation (with real activities)
# ============================================================================

@_run_phase("Phase 6: XAML Generation")
async def phase_6_xaml_generation(ir, selectors, matched):
    from rpa_architect.assembler.reframework_gen import generate_reframework_xaml
    from rpa_architect.generators.ui_activities import (
        gen_click, gen_type_into, gen_get_text, gen_select_item, gen_check,
    )
    from rpa_architect.generators.logging_misc import gen_log_message

    # 6a: Standard REFramework templates
    xaml_files = generate_reframework_xaml(ir)
    for filename, content in xaml_files.items():
        out_path = PROJECT_DIR / filename
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(content, encoding="utf-8")

    # 6b: OVERRIDE Process.xaml — replace comment-only template with real activities
    #     This ensures the REFramework's core workflow has actual UI activities wired in.
    activity_fragments_process = []
    for m in matched:
        sel = selectors.get(m.element_name, "")
        if not sel or "TODO" in sel:
            continue
        target = m.action.target
        if m.action.action == "click":
            activity_fragments_process.append(gen_click(sel, display_name=f"Click {target}"))
        elif m.action.action == "type_into":
            activity_fragments_process.append(gen_type_into(sel, m.action.value or "", display_name=f"Type Into {target}"))
        elif m.action.action == "get_text":
            activity_fragments_process.append(gen_get_text(sel, "extractedText", display_name=f"Get Text {target}"))
        elif m.action.action == "select_item":
            activity_fragments_process.append(gen_select_item(sel, m.action.value or "", display_name=f"Select {target}"))
        elif m.action.action in ("check", "uncheck"):
            activity_fragments_process.append(gen_check(sel, action=m.action.action.capitalize(), display_name=f"Check {target}"))

    if activity_fragments_process:
        process_header = (
            '<?xml version="1.0" encoding="utf-8"?>\n'
            '<Activity mc:Ignorable="sap sap2010 sads"'
            ' x:Class="Process"'
            ' xmlns="http://schemas.microsoft.com/netfx/2009/xaml/activities"'
            ' xmlns:mc="http://schemas.openxmlformats.org/markup-compatibility/2006"'
            ' xmlns:sap="http://schemas.microsoft.com/netfx/2009/xaml/activities/presentation"'
            ' xmlns:sap2010="http://schemas.microsoft.com/netfx/2010/xaml/activities/presentation"'
            ' xmlns:sads="http://schemas.microsoft.com/netfx/2010/xaml/activities/debugger"'
            ' xmlns:scg="clr-namespace:System.Collections.Generic;assembly=mscorlib"'
            ' xmlns:ui="http://schemas.uipath.com/workflow/activities"'
            ' xmlns:x="http://schemas.microsoft.com/winfx/2006/xaml">\n'
        )
        process_body = [f'  <Sequence DisplayName="Process Transaction">\n']
        process_body.append(f'    <!-- REFramework Process.xaml with live-harvested selectors -->\n')
        process_body.append(f'    <!-- Generated from {TARGET_URL} -->\n')
        process_body.append(gen_log_message(
            "Starting transaction processing", level="Info",
            display_name="Log Start Processing",
        ))
        process_body.append("\n")
        for frag in activity_fragments_process:
            for line in frag.split("\n"):
                process_body.append(f"    {line}\n")
        process_body.append(gen_log_message(
            "Transaction processing completed", level="Info",
            display_name="Log End Processing",
        ))
        process_body.append("\n")
        process_body.append('  </Sequence>\n')

        process_xaml = process_header + "".join(process_body) + '</Activity>\n'
        xaml_files["Framework/Process.xaml"] = process_xaml
        (PROJECT_DIR / "Framework" / "Process.xaml").write_text(process_xaml, encoding="utf-8")
        logger.info("Process.xaml OVERRIDDEN with real UI activities from harvested selectors")

    # 6c: Process_WithActivities.xaml — standalone copy with real XAML activities
    activity_fragments = []
    for m in matched:
        sel = selectors.get(m.element_name, "")
        if not sel:
            continue
        target = m.action.target
        if m.action.action == "click":
            activity_fragments.append(gen_click(sel, display_name=f"Click {target}"))
        elif m.action.action == "type_into":
            activity_fragments.append(gen_type_into(sel, m.action.value or "", display_name=f"Type Into {target}"))
        elif m.action.action == "get_text":
            activity_fragments.append(gen_get_text(sel, "extractedText", display_name=f"Get Text {target}"))
        elif m.action.action == "select_item":
            activity_fragments.append(gen_select_item(sel, m.action.value or "", display_name=f"Select {target}"))
        elif m.action.action in ("check", "uncheck"):
            activity_fragments.append(gen_check(sel, action=m.action.action.capitalize(), display_name=f"Check {target}"))

        activity_fragments.append(gen_log_message(
            f"Completed: {target}", level="Info",
            display_name=f"Log Completed {target}",
        ))

    # Wrap in proper XAML
    header = (
        '<?xml version="1.0" encoding="utf-8"?>\n'
        '<Activity mc:Ignorable="sap sap2010 sads"'
        ' x:Class="ProcessWithActivities"'
        ' xmlns="http://schemas.microsoft.com/netfx/2009/xaml/activities"'
        ' xmlns:mc="http://schemas.openxmlformats.org/markup-compatibility/2006"'
        ' xmlns:sap="http://schemas.microsoft.com/netfx/2009/xaml/activities/presentation"'
        ' xmlns:sap2010="http://schemas.microsoft.com/netfx/2010/xaml/activities/presentation"'
        ' xmlns:sads="http://schemas.microsoft.com/netfx/2010/xaml/activities/debugger"'
        ' xmlns:scg="clr-namespace:System.Collections.Generic;assembly=mscorlib"'
        ' xmlns:ui="http://schemas.uipath.com/workflow/activities"'
        ' xmlns:x="http://schemas.microsoft.com/winfx/2006/xaml">\n'
    )
    body_lines = [f'  <Sequence DisplayName="Process With Live Selectors">\n']
    body_lines.append(f'    <!-- Generated from live harvest of {TARGET_URL} -->\n')
    for frag in activity_fragments:
        for line in frag.split("\n"):
            body_lines.append(f"    {line}\n")
    body_lines.append('  </Sequence>\n')
    footer = '</Activity>\n'

    process_with_activities = header + "".join(body_lines) + footer
    (PROJECT_DIR / "Process_WithActivities.xaml").write_text(process_with_activities, encoding="utf-8")

    all_xaml = dict(xaml_files)
    all_xaml["Process_WithActivities.xaml"] = process_with_activities

    logger.info("Generated %d XAML files (%d REFramework + Process_WithActivities)",
                len(all_xaml), len(xaml_files))
    return all_xaml


# ============================================================================
# PHASE 7 — Object Repository v2
# ============================================================================

@_run_phase("Phase 7: Object Repository v2")
async def phase_7_object_repository(ir, selectors):
    from rpa_architect.selectors.object_repository import generate_object_repository_v2

    obj_files = generate_object_repository_v2(ir, selectors)

    for filepath, content in obj_files.items():
        out_path = PROJECT_DIR / filepath
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(content, encoding="utf-8")

    logger.info("Object Repository v2: %d files written", len(obj_files))
    return obj_files


# ============================================================================
# PHASE 8 — Coded C# Workflow Generation
# ============================================================================

@_run_phase("Phase 8: Coded C# Workflows")
async def phase_8_coded_workflows(selectors, matched):
    from rpa_architect.codegen.coded_workflow_gen import generate_coded_workflow, generate_coded_test
    from rpa_architect.generators.coded_apis import (
        gen_coded_open_app, gen_coded_click, gen_coded_type_into,
        gen_coded_get_text, gen_coded_log_message,
    )

    # ProcessTestPages.cs — main workflow with real selectors
    body = [
        gen_coded_log_message("Starting TheInternet automation"),
        gen_coded_open_app("Descriptors.TheInternet.TheInternet", "screen"),
        "",
    ]
    for m in matched:
        if m.element_name not in selectors:
            continue
        if m.action.action == "click":
            body.append(gen_coded_click("screen", m.element_name))
        elif m.action.action == "type_into":
            body.append(gen_coded_type_into("screen", m.element_name, m.action.value or ""))
        elif m.action.action == "get_text":
            body.append(gen_coded_get_text("screen", m.element_name, "resultText"))
        elif m.action.action in ("check", "uncheck", "select_item"):
            body.append(gen_coded_click("screen", m.element_name))
        body.append(gen_coded_log_message(f"Done: {m.action.target}"))

    cs_main = generate_coded_workflow(
        class_name="ProcessTestPages",
        namespace="TheInternetAutomation",
        body_statements=body,
        imports=["using UiPath.UIAutomationNext.API;"],
    )
    (PROJECT_DIR / "ProcessTestPages.cs").write_text(cs_main, encoding="utf-8")

    # TestVerification.cs — coded test
    test_body = [
        gen_coded_log_message("Starting selector verification test"),
        "",
        "// Verify all harvested selectors resolve",
    ]
    for name in selectors:
        test_body.append(f'Assert.IsNotNull(uiAutomation.Find("{name}"), "Selector {name} not found");')
    test_body.append("")
    test_body.append(gen_coded_log_message("All selectors verified successfully"))

    cs_test = generate_coded_test(
        class_name="SelectorVerification",
        namespace="TheInternetAutomation",
        test_body=test_body,
        test_name="VerifyAllSelectors",
        imports=["using UiPath.UIAutomationNext.API;", "using Microsoft.VisualStudio.TestTools.UnitTesting;"],
    )
    (PROJECT_DIR / "Tests" / "TestVerification.cs").write_text(cs_test, encoding="utf-8")

    logger.info("Generated 2 C# files: ProcessTestPages.cs, Tests/TestVerification.cs")
    return {"ProcessTestPages.cs": cs_main, "Tests/TestVerification.cs": cs_test}


# ============================================================================
# PHASE 9 — project.json
# ============================================================================

@_run_phase("Phase 9: project.json")
async def phase_9_project_json(ir):
    from rpa_architect.assembler.project_json_gen import generate_project_json

    content = generate_project_json(ir)
    (PROJECT_DIR / "project.json").write_text(content, encoding="utf-8")

    parsed = json.loads(content)
    logger.info(
        "project.json: toolVersion=%s, targetFramework=%s, %d dependencies",
        parsed.get("toolVersion"), parsed.get("targetFramework"),
        len(parsed.get("dependencies", {})),
    )
    return content


# ============================================================================
# PHASE 10 — XAML Linting
# ============================================================================

@_run_phase("Phase 10: XAML Linting")
async def phase_10_xaml_lint(xaml_files):
    from rpa_architect.xaml_lint import lint_xaml

    all_issues = {}
    error_count = 0
    warning_count = 0
    info_count = 0

    for filename, content in xaml_files.items():
        issues = lint_xaml(content)
        all_issues[filename] = [
            {
                "rule_id": i.rule_id,
                "severity": i.severity.value if hasattr(i.severity, "value") else str(i.severity),
                "message": i.message,
                "suggestion": i.suggestion if hasattr(i, "suggestion") else "",
            }
            for i in issues
        ]
        for i in issues:
            sev = i.severity.value if hasattr(i.severity, "value") else str(i.severity)
            if "error" in sev.lower():
                error_count += 1
            elif "warning" in sev.lower():
                warning_count += 1
            else:
                info_count += 1

    _dump_json(all_issues, REPORTS_DIR / "xaml_lint_report.json")
    logger.info("XAML lint: %d errors, %d warnings, %d info across %d files",
                error_count, warning_count, info_count, len(xaml_files))
    return all_issues, error_count, warning_count, info_count


# ============================================================================
# PHASE 11 — Coded Workflow Linting
# ============================================================================

@_run_phase("Phase 11: Coded Lint")
async def phase_11_coded_lint(cs_files):
    from rpa_architect.xaml_lint.rules_coded import lint_coded_file

    all_issues = {}
    total = 0
    for filename, content in cs_files.items():
        issues = lint_coded_file(content, file_path=filename)
        all_issues[filename] = [
            {
                "rule_id": i.rule_id,
                "severity": i.severity.value if hasattr(i.severity, "value") else str(i.severity),
                "message": i.message,
            }
            for i in issues
        ]
        total += len(issues)

    _dump_json(all_issues, REPORTS_DIR / "coded_lint_report.json")
    logger.info("Coded lint: %d issues across %d files", total, len(cs_files))
    return all_issues, total


# ============================================================================
# PHASE 12 — Summary Report
# ============================================================================

@_run_phase("Phase 12: Summary Report")
async def phase_12_summary(
    ir, reports, match_data_tuple, selectors, selector_details,
    validation_result, scores_tuple, xaml_files, obj_files, cs_files,
    lint_xaml_tuple, lint_coded_tuple, elapsed_total,
):
    from datetime import datetime, timezone

    matched, unmatched = match_data_tuple or ([], [])
    scores, overall_score = scores_tuple or ({}, 0)
    xaml_issues, xerr, xwarn, xinfo = lint_xaml_tuple or ({}, 0, 0, 0)
    coded_issues, coded_total = lint_coded_tuple or ({}, 0)

    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")

    lines = [
        f"# End-to-End Proof Report",
        f"",
        f"**Generated**: {now}",
        f"**Target**: {TARGET_URL}",
        f"**Process**: {ir.process_name if ir else 'N/A'}",
        f"**Duration**: {elapsed_total:.1f}s",
        f"",
    ]

    # --- ProcessIR ---
    lines.append("## 1. ProcessIR")
    if ir:
        total_actions = sum(len(s.actions) for t in ir.transactions for s in t.steps)
        lines.append(f"- Systems: {len(ir.systems)} ({', '.join(s.name for s in ir.systems)})")
        lines.append(f"- Transactions: {len(ir.transactions)}")
        lines.append(f"- Steps: {sum(len(t.steps) for t in ir.transactions)}")
        lines.append(f"- UIActions: {total_actions}")
    lines.append("")

    # --- Browser Harvest ---
    lines.append("## 2. Browser Harvest Results")
    if reports:
        lines.append("| Step | Page | Elements | Screenshot |")
        lines.append("|------|------|----------|------------|")
        for report in reports.values():
            for r in report.results:
                page = r.page_url.replace(TARGET_URL, "") or "/"
                scr = f"S {r.step_id}.png" if r.screenshot_path else "N/A"
                lines.append(f"| {r.step_id} | {page} | {len(r.elements)} | {scr} |")
    else:
        lines.append("*Harvest was skipped or failed.*")
    lines.append("")

    # --- Element Matching ---
    lines.append("## 3. Element Matching")
    total_actions_count = len(matched) + len(unmatched)
    rate = round(100 * len(matched) / max(total_actions_count, 1), 1)
    lines.append(f"- Total actions: {total_actions_count}")
    lines.append(f"- Matched: {len(matched)} ({rate}%)")
    lines.append(f"- Unmatched: {len(unmatched)}")
    lines.append("")
    if matched:
        lines.append("| Action | Target | Matched To | Method | Confidence |")
        lines.append("|--------|--------|-----------|--------|------------|")
        for m in matched:
            el_desc = ""
            if m.element:
                el_desc = m.element.id or m.element.inner_text[:30] or m.element.tag
            lines.append(
                f"| {m.action.action} | {m.action.target} | {el_desc} | {m.match_method} | {m.confidence:.2f} |"
            )
    lines.append("")

    # --- Selectors ---
    lines.append("## 4. UiPath Selectors Built")
    if selector_details:
        lines.append("| Element | Selector XML | Stability |")
        lines.append("|---------|-------------|-----------|")
        for name, detail in selector_details.items():
            sel_short = detail["selector_xml"][:80] + "..." if len(detail["selector_xml"]) > 80 else detail["selector_xml"]
            lines.append(f"| {name} | `{sel_short}` | {detail['stability_score']:.2f} |")
    lines.append("")

    # --- Live Validation ---
    lines.append("## 4b. LIVE SELECTOR VALIDATION (Proof of Execution)")
    if validation_result:
        v_total, v_found, v_interacted, v_results = validation_result
        lines.append(f"- Selectors validated against live page: {v_total}")
        lines.append(f"- Elements found: {v_found}/{v_total} ({round(100*v_found/max(v_total,1))}%)")
        lines.append(f"- Successfully interacted (clicked/typed/selected): {v_interacted}/{v_total} ({round(100*v_interacted/max(v_total,1))}%)")
        lines.append("")
        lines.append("| Element | Found | Interacted | CSS Query Used |")
        lines.append("|---------|-------|------------|----------------|")
        for vr in v_results:
            found = "YES" if vr["found"] else "NO"
            interacted = "YES" if vr["interacted"] else ("PARTIAL" if vr.get("interaction_error") else "NO")
            css = vr.get("css_used", "")[:50]
            lines.append(f"| {vr['element_name']} | {found} | {interacted} | `{css}` |")
    else:
        lines.append("*Validation skipped.*")
    lines.append("")

    # --- Scores ---
    lines.append("## 5. Selector Quality Scores")
    if scores:
        lines.append("| Element | Score | Bonuses | Penalties |")
        lines.append("|---------|-------|---------|-----------|")
        for name, s in scores.items():
            bonuses = "; ".join(s.bonuses) if s.bonuses else "-"
            penalties = "; ".join(s.penalties) if s.penalties else "-"
            lines.append(f"| {name} | {s.score}/100 | {bonuses} | {penalties} |")
        lines.append(f"\n**Aggregate Score: {overall_score}/100**")
    lines.append("")

    # --- Generated Files ---
    lines.append("## 6. Generated UiPath Project")
    lines.append("| File | Size | Description |")
    lines.append("|------|------|-------------|")

    all_files = []
    # XAML
    if xaml_files:
        for fn, content in xaml_files.items():
            all_files.append((fn, len(content), "XAML workflow"))
    # Object repo
    if obj_files:
        for fn, content in obj_files.items():
            all_files.append((fn, len(content), "Object Repository v2"))
    # C#
    if cs_files:
        for fn, content in cs_files.items():
            all_files.append((fn, len(content), "Coded C# workflow"))
    # project.json
    pj = PROJECT_DIR / "project.json"
    if pj.exists():
        all_files.append(("project.json", pj.stat().st_size, "Studio 25.10 manifest"))

    for fn, size, desc in sorted(all_files):
        lines.append(f"| {fn} | {size:,}b | {desc} |")
    lines.append("")

    # --- Lint ---
    lines.append("## 7. Lint Results")
    lines.append(f"- XAML: {xerr} errors, {xwarn} warnings, {xinfo} info")
    lines.append(f"- Coded: {coded_total} issues")
    lines.append("")

    # --- Phase Summary ---
    lines.append("## 8. Phase Summary")
    lines.append("| # | Phase | Status | Duration |")
    lines.append("|---|-------|--------|----------|")
    passed_count = 0
    for i, pr in enumerate(PHASE_RESULTS):
        status = "PASS" if pr.passed else "FAIL"
        symbol = "+" if pr.passed else "X"
        if pr.passed:
            passed_count += 1
        err = f" — {pr.error}" if pr.error else ""
        lines.append(f"| {i} | {pr.name} | {symbol} {status}{err} | {pr.duration_s:.1f}s |")

    lines.append(f"\n**Overall: {passed_count}/{len(PHASE_RESULTS)} phases passed**")
    lines.append(f"\n**Total elapsed: {elapsed_total:.1f}s**")

    summary_md = "\n".join(lines) + "\n"
    (OUTPUT_DIR / "SUMMARY.md").write_text(summary_md, encoding="utf-8")

    # Machine-readable summary
    summary_json = {
        "timestamp": now,
        "target_url": TARGET_URL,
        "process_name": ir.process_name if ir else None,
        "elapsed_s": elapsed_total,
        "phases": [
            {"name": pr.name, "passed": pr.passed, "duration_s": pr.duration_s, "error": pr.error}
            for pr in PHASE_RESULTS
        ],
        "totals": {
            "actions": total_actions_count,
            "matched": len(matched),
            "unmatched": len(unmatched),
            "selectors": len(selectors) if selectors else 0,
            "aggregate_score": overall_score,
            "xaml_files": len(xaml_files) if xaml_files else 0,
            "cs_files": len(cs_files) if cs_files else 0,
            "obj_repo_files": len(obj_files) if obj_files else 0,
            "lint_errors": xerr,
            "lint_warnings": xwarn,
        },
    }
    _dump_json(summary_json, OUTPUT_DIR / "summary.json")

    logger.info("Summary written to %s", OUTPUT_DIR / "SUMMARY.md")
    return summary_md


# ============================================================================
# MAIN
# ============================================================================

async def main() -> None:
    t_start = time.monotonic()

    print("=" * 70)
    print("  AUTONOMOUS RPA ARCHITECT — End-to-End Live Proof")
    print(f"  Target: {TARGET_URL}")
    print("=" * 70)
    print()

    # Phase 0
    await phase_0_setup()

    # Phase 1
    ir = await phase_1_build_ir()
    if ir is None:
        logger.error("Cannot continue without IR. Aborting.")
        return

    # Phase 2
    reports = await phase_2_browser_harvest(ir)

    # Phase 3
    match_data = None
    if reports:
        match_data = await phase_3_element_matching(ir, reports)

    matched = match_data[0] if match_data else []
    unmatched = match_data[1] if match_data else []

    # Phase 4
    sel_result = await phase_4_selector_conversion(ir, matched, unmatched)
    selectors = sel_result[0] if sel_result else {}
    selector_details = sel_result[1] if sel_result else {}
    matched_from_sel = sel_result[2] if sel_result else matched

    # Phase 4b — LIVE VALIDATION (the real proof)
    validation_result = None
    if selectors and matched_from_sel:
        validation_result = await phase_4b_validate_selectors_live(ir, selectors, matched_from_sel)

    # Phase 5
    scores_tuple = await phase_5_selector_scoring(selectors)

    # Phase 6
    xaml_files = await phase_6_xaml_generation(ir, selectors, matched_from_sel)

    # Phase 7
    obj_files = await phase_7_object_repository(ir, selectors)

    # Phase 8
    cs_files = await phase_8_coded_workflows(selectors, matched_from_sel)

    # Phase 9
    await phase_9_project_json(ir)

    # Phase 10
    lint_xaml_result = None
    if xaml_files:
        lint_xaml_result = await phase_10_xaml_lint(xaml_files)

    # Phase 11
    lint_coded_result = None
    if cs_files:
        lint_coded_result = await phase_11_coded_lint(cs_files)

    # Phase 12
    elapsed = round(time.monotonic() - t_start, 1)
    await phase_12_summary(
        ir=ir,
        reports=reports,
        match_data_tuple=(matched_from_sel, unmatched),
        selectors=selectors,
        selector_details=selector_details,
        validation_result=validation_result,
        scores_tuple=scores_tuple,
        xaml_files=xaml_files,
        obj_files=obj_files,
        cs_files=cs_files,
        lint_xaml_tuple=lint_xaml_result,
        lint_coded_tuple=lint_coded_result,
        elapsed_total=elapsed,
    )

    # Final banner
    passed = sum(1 for pr in PHASE_RESULTS if pr.passed)
    total = len(PHASE_RESULTS)
    print()
    print("=" * 70)
    print(f"  RESULT: {passed}/{total} phases passed  ({elapsed:.1f}s)")
    print(f"  Output: {OUTPUT_DIR}")
    print(f"  Report: {OUTPUT_DIR / 'SUMMARY.md'}")
    print("=" * 70)


if __name__ == "__main__":
    asyncio.run(main())
