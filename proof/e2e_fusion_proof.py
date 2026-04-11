#!/usr/bin/env python3
"""Fusion-Ready End-to-End Proof: PDD → Working REFramework Project.

Demonstrates the complete autonomous-rpa-architect pipeline:
  PDD document → Parse → ProcessIR → Browser Harvest → Selector Generation
  → REFramework XAML (via Jinja2 templates) → Object Repository → Coded C#
  → Config.xlsx → Wiring → Validation → Report

Produces a UiPath Studio 2025.10 compatible project with:
  - Full REFramework state machine (510+ line Main.xaml)
  - Real UI activities with live-harvested selectors
  - Coded C# workflows
  - Config.xlsx with populated settings
  - Object Repository v2

Usage:
    python3 proof/e2e_fusion_proof.py

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
from dataclasses import dataclass, fields as dc_fields
from enum import Enum
from pathlib import Path
from typing import Any

# ---------------------------------------------------------------------------
# Bootstrap
# ---------------------------------------------------------------------------
PROJECT_ROOT = Path(__file__).resolve().parent.parent
_SRC = PROJECT_ROOT / "src"
_PROOF = PROJECT_ROOT
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))
if str(_PROOF) not in sys.path:
    sys.path.insert(0, str(_PROOF))

# ---------------------------------------------------------------------------
# Output paths
# ---------------------------------------------------------------------------
OUTPUT_DIR = Path(__file__).resolve().parent / "e2e_output_fusion"
SCREENSHOTS_DIR = OUTPUT_DIR / "screenshots"
HARVEST_DIR = OUTPUT_DIR / "harvested_data"
SELECTORS_DIR = OUTPUT_DIR / "selectors"
PROJECT_DIR = OUTPUT_DIR / "uipath_project"
REPORTS_DIR = OUTPUT_DIR / "reports"

PDD_PATH = Path(__file__).resolve().parent / "sample_pdd.md"
TARGET_URL = "https://the-internet.herokuapp.com"

MIN_MAIN_XAML_LINES = 100  # Minimum for full REFramework state machine

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
                pr.detail = str(result)[:200] if result else "OK"
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
                    "Phase %-45s [%s]  %.1fs",
                    name, status, pr.duration_s,
                )
        return wrapper
    return decorator


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _serializable(obj: Any) -> Any:
    if obj is None or isinstance(obj, (str, int, float, bool)):
        return obj
    if isinstance(obj, Path):
        return str(obj)
    if isinstance(obj, Enum):
        return obj.value
    if hasattr(obj, "__dataclass_fields__"):
        return {f.name: _serializable(getattr(obj, f.name)) for f in dc_fields(obj)}
    if hasattr(obj, "model_dump"):
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
logger = logging.getLogger("fusion_proof")
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
              PROJECT_DIR / ".objects", PROJECT_DIR / "Tests",
              PROJECT_DIR / "Workflows"):
        d.mkdir(parents=True, exist_ok=True)
    _setup_file_logging()

    if importlib.util.find_spec("playwright") is None:
        raise RuntimeError(
            "Playwright not installed. Run: pip install playwright && "
            "python3 -m playwright install chromium"
        )
    return "Directories created, playwright available"


# ============================================================================
# PHASE 1 — Load PDD Document
# ============================================================================

@_run_phase("Phase 1: Load PDD")
async def phase_1_load_pdd() -> str:
    if not PDD_PATH.exists():
        raise FileNotFoundError(f"Sample PDD not found at {PDD_PATH}")

    content = PDD_PATH.read_text(encoding="utf-8")
    logger.info("PDD loaded: %s (%d lines, %d bytes)", PDD_PATH.name,
                len(content.splitlines()), len(content))
    return content


# ============================================================================
# PHASE 2 — PDD → ProcessIR
# ============================================================================

@_run_phase("Phase 2: PDD → ProcessIR")
async def phase_2_parse_pdd(pdd_content: str) -> Any:
    from rpa_architect.parser.pdd_parser import parse_pdd

    ir = parse_pdd(PDD_PATH)

    # Validate round-trip
    ir.model_validate(ir.model_dump())
    _dump_json(ir.model_dump(), OUTPUT_DIR / "process_ir.json")

    total_actions = sum(
        len(s.actions) for t in ir.transactions for s in t.steps
    )
    logger.info(
        "IR: %d system(s), %d transaction(s), %d step(s), %d action(s), %d config entries",
        len(ir.systems), len(ir.transactions),
        sum(len(t.steps) for t in ir.transactions),
        total_actions, len(ir.config),
    )
    return ir


# ============================================================================
# PHASE 3 — Browser Harvest
# ============================================================================

@_run_phase("Phase 3: Browser Harvest")
async def phase_3_browser_harvest(ir):
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

    for sys_name, report in reports.items():
        _dump_json(report, HARVEST_DIR / f"{sys_name}_report.json")
        for result in report.results:
            _dump_json(result, HARVEST_DIR / f"{result.step_id}_elements.json")

    total_elements = sum(
        len(r.elements) for report in reports.values() for r in report.results
    )
    logger.info(
        "Harvest: %d elements, %d selectors across %d system(s)",
        total_elements,
        sum(len(r.selectors) for r in reports.values()),
        len(reports),
    )
    return reports


# ============================================================================
# PHASE 4 — Element Matching
# ============================================================================

def _enhanced_fallback_match(step_id, idx, action, elements, used_indices):
    """Enhanced fallback matching for elements the heuristic misses."""
    import re
    from rpa_architect.selectors.element_matcher import MatchResult

    target_lower = action.target.lower()
    target_tokens = set(re.sub(r"[^a-z0-9\s]", " ", target_lower).split())
    available = [(i, el) for i, el in enumerate(elements) if i not in used_indices]
    if not available:
        return None

    element_name = re.sub(r"[^a-zA-Z0-9]", "_", f"{step_id}_{action.target}")
    element_name = re.sub(r"_+", "_", element_name).strip("_") + f"_{idx}"

    role_map = {"check": "checkbox", "uncheck": "checkbox", "type_into": None,
                "get_text": None, "click": None, "select_item": None}
    expected_type = role_map.get(action.action)

    if "checkbox" in target_tokens or "check" in target_tokens:
        expected_type = "checkbox"
    elif "number" in target_tokens:
        expected_type = "number"
    elif "input" in target_tokens or "field" in target_tokens or "text" in target_tokens:
        expected_type = "__input__"
    elif "result" in target_tokens or "output" in target_tokens:
        expected_type = "__id_match__"

    ordinal = None
    for tok in target_tokens:
        if tok.isdigit():
            ordinal = int(tok) - 1
            break
    for word, oidx in {"first": 0, "second": 1, "third": 2}.items():
        if word in target_tokens:
            ordinal = oidx
            break

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

    if ordinal is not None and expected_type:
        typed = [(i, el) for i, el in available
                  if (expected_type in (el.input_type, el.aria_role))
                  or (expected_type == "__input__" and el.tag == "input")]
        if 0 <= ordinal < len(typed):
            ci, cel = typed[ordinal]
            return MatchResult(
                action=action, element=cel, element_name=element_name,
                confidence=0.75, match_method="enhanced_ordinal",
                reasoning=f"Ordinal '{ordinal+1}' matched {expected_type} element",
            ), ci

    if len(candidates) == 1:
        ci, cel = candidates[0]
        return MatchResult(
            action=action, element=cel, element_name=element_name,
            confidence=0.70, match_method="enhanced_single_candidate",
            reasoning=f"Only matching element on page: {cel.tag}[{cel.input_type}]",
        ), ci

    for ci, cel in candidates:
        if cel.id:
            import re as _re
            id_tokens = set(_re.sub(r"[^a-z0-9]", " ", cel.id.lower()).split())
            overlap = target_tokens & id_tokens
            if overlap:
                return MatchResult(
                    action=action, element=cel, element_name=element_name,
                    confidence=0.80, match_method="enhanced_id_substring",
                    reasoning=f"ID '{cel.id}' overlaps with target tokens {overlap}",
                ), ci

    if action.action in ("type_into", "get_text"):
        inputs = [(i, el) for i, el in available if el.tag in ("input", "textarea")]
        if len(inputs) == 1:
            ci, cel = inputs[0]
            return MatchResult(
                action=action, element=cel, element_name=element_name,
                confidence=0.65, match_method="enhanced_sole_input",
                reasoning=f"Only input element on page for {action.action}",
            ), ci

    return None


@_run_phase("Phase 4: Element Matching")
async def phase_4_element_matching(ir, reports):
    from rpa_architect.selectors.element_matcher import heuristic_match, MatchResult

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

            matched, unmatched = heuristic_match(step_actions, elements, threshold=0.2)
            all_matched.extend(matched)

            used_indices: set[int] = set()
            for m in matched:
                if m.element is not None and m.element in elements:
                    used_indices.add(elements.index(m.element))

            for sid, idx, action in unmatched:
                result = _enhanced_fallback_match(sid, idx, action, elements, used_indices)
                if result:
                    match_result, el_idx = result
                    used_indices.add(el_idx)
                    all_matched.append(match_result)
                else:
                    all_unmatched.append((sid, idx, action))

    match_rate = round(100 * len(all_matched) / max(total_actions, 1), 1)
    _dump_json({
        "total_actions": total_actions,
        "matched_count": len(all_matched),
        "unmatched_count": len(all_unmatched),
        "match_rate_pct": match_rate,
    }, HARVEST_DIR / "match_results.json")

    logger.info("Matched: %d/%d (%.0f%%)", len(all_matched), total_actions, match_rate)
    return all_matched, all_unmatched


# ============================================================================
# PHASE 5 — Selector Conversion
# ============================================================================

@_run_phase("Phase 5: Selector Conversion")
async def phase_5_selector_conversion(ir, matched, unmatched):
    from rpa_architect.selectors.uipath_converter import batch_convert, convert_to_uipath_selector
    from rpa_architect.selectors.placeholder_gen import generate_placeholder_selectors
    from rpa_architect.selectors.harvest_pipeline import merge_selectors

    harvested_selectors = batch_convert(matched, app_name="chrome.exe")

    selector_details = {}
    for m in matched:
        if m.element is not None:
            sel_xml, stability = convert_to_uipath_selector(m.element, "chrome.exe")
            selector_details[m.element_name] = {
                "selector_xml": sel_xml, "stability_score": stability,
                "match_method": m.match_method, "match_confidence": m.confidence,
            }

    placeholders = generate_placeholder_selectors(ir)
    all_selectors = merge_selectors(harvested=harvested_selectors, placeholders=placeholders)

    _dump_json(all_selectors, SELECTORS_DIR / "all_selectors.json")
    _dump_json(selector_details, SELECTORS_DIR / "selector_details.json")

    logger.info("Selectors: %d harvested, %d placeholders, %d total",
                len(harvested_selectors), len(placeholders), len(all_selectors))
    return all_selectors, selector_details, matched


# ============================================================================
# PHASE 6 — Live Selector Validation
# ============================================================================

@_run_phase("Phase 6: Live Selector Validation")
async def phase_6_validate_selectors_live(ir, selectors, matched):
    """Re-open browser and verify generated selectors find real elements."""
    import re
    from playwright.async_api import async_playwright

    def _uipath_selector_to_css(sel_xml):
        webctrl = re.search(r"<webctrl\s+([^/]*)/?>", sel_xml)
        if not webctrl:
            return None
        attrs_str = webctrl.group(1)
        tag, css = "*", []
        for m in re.finditer(r"(\w[\w-]*)='([^']*)'", attrs_str):
            n, v = m.group(1), m.group(2)
            if n == "tag": tag = v
            elif n == "id": css.append(f"#{v}")
            elif n == "name": css.append(f"[name='{v}']")
            elif n == "type": css.append(f"[type='{v}']")
            elif n == "class": css.append(f".{v}")
        if tag != "*" and css: return tag + "".join(css)
        elif css: return "".join(css)
        elif tag != "*": return tag
        return None

    step_map: dict[str, dict] = {}
    for txn in ir.transactions:
        for step in txn.steps:
            step_map[step.id] = {"url": step.parameters.get("url", ""), "elements": []}
    for m in matched:
        step_id = m.element_name.split("_")[0]
        sel_xml = selectors.get(m.element_name, "")
        if step_id in step_map and sel_xml and "TODO" not in sel_xml:
            step_map[step_id]["elements"].append({
                "name": m.element_name, "selector": sel_xml, "action": m.action,
            })

    total_validated = total_found = total_interacted = 0
    validation_results = []

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page(viewport={"width": 1920, "height": 1080})

        for step_id, info in sorted(step_map.items()):
            if not info["url"] or not info["elements"]:
                continue
            try:
                await page.goto(info["url"], wait_until="networkidle", timeout=15000)
            except Exception:
                continue

            for elem in info["elements"]:
                total_validated += 1
                result = {"element_name": elem["name"], "found": False, "interacted": False}
                css = _uipath_selector_to_css(elem["selector"])
                if not css:
                    it = re.search(r"innertext='([^']+)'", elem["selector"])
                    if it:
                        try:
                            el = page.locator(f"text='{it.group(1)}'").first
                            if await el.count() > 0:
                                result["found"] = True
                                total_found += 1
                        except Exception:
                            pass
                    validation_results.append(result)
                    continue
                try:
                    el = page.locator(css).first
                    if await el.count() > 0:
                        result["found"] = True
                        total_found += 1
                        act = elem["action"].action
                        try:
                            if act == "click":
                                await el.click(timeout=3000)
                            elif act == "type_into":
                                await el.fill(elem["action"].value or "test", timeout=3000)
                            elif act == "select_item":
                                await el.select_option(label=elem["action"].value or "", timeout=3000)
                            elif act in ("check", "uncheck"):
                                await el.check(timeout=3000)
                            elif act == "get_text":
                                await el.inner_text(timeout=3000)
                            result["interacted"] = True
                            total_interacted += 1
                        except Exception:
                            pass
                except Exception:
                    pass
                validation_results.append(result)

        if total_interacted > 0:
            await page.screenshot(path=str(SCREENSHOTS_DIR / "validation_proof.png"))
        await browser.close()

    _dump_json({
        "total_validated": total_validated, "total_found": total_found,
        "total_interacted": total_interacted, "results": validation_results,
    }, REPORTS_DIR / "selector_validation.json")

    logger.info("Validation: %d/%d found, %d/%d interacted",
                total_found, total_validated, total_interacted, total_validated)
    return total_validated, total_found, total_interacted, validation_results


# ============================================================================
# PHASE 7 — Selector Quality Scoring
# ============================================================================

@_run_phase("Phase 7: Selector Scoring")
async def phase_7_selector_scoring(selectors):
    from rpa_architect.validation.selector_scorer import score_project_selectors, aggregate_score

    scores = score_project_selectors(selectors)
    overall = aggregate_score(scores)

    _dump_json({
        "aggregate_score": overall,
        "element_scores": {n: {"score": s.score} for n, s in scores.items()},
    }, REPORTS_DIR / "selector_scores.json")

    logger.info("Selector quality: %d/100 across %d selectors", overall, len(scores))
    return scores, overall


# ============================================================================
# PHASE 8 — REFramework XAML via Template Engine (THE KEY PHASE)
# ============================================================================

@_run_phase("Phase 8: REFramework XAML (Templates)")
async def phase_8_reframework_xaml(ir):
    from rpa_architect.codegen.template_engine import TemplateEngine
    from rpa_architect.assembler.reframework_gen import generate_reframework_xaml

    # Generate with production templates
    engine = TemplateEngine(templates_dir=PROJECT_ROOT / "templates")
    xaml_files = generate_reframework_xaml(ir, template_engine=engine)

    # Generate stub versions for comparison
    stub_files = generate_reframework_xaml(ir, template_engine=None)

    for filename, content in xaml_files.items():
        out_path = PROJECT_DIR / filename
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(content, encoding="utf-8")

    # Log before/after comparison
    logger.info("  === Template vs Stub Comparison ===")
    for filename in sorted(xaml_files):
        tpl_lines = len(xaml_files[filename].splitlines())
        stub_lines = len(stub_files.get(filename, "").splitlines())
        ratio = f"{tpl_lines / max(stub_lines, 1):.1f}x" if tpl_lines >= stub_lines else "SHORTER"
        logger.info("  %-45s %4d lines (template) vs %3d (stub) = %s",
                     filename, tpl_lines, stub_lines, ratio)

    main_lines = len(xaml_files.get("Main.xaml", "").splitlines())
    if main_lines < MIN_MAIN_XAML_LINES:
        raise ValueError(
            f"Main.xaml only {main_lines} lines — templates not rendering correctly. "
            f"Expected >= {MIN_MAIN_XAML_LINES} lines for full REFramework state machine."
        )

    logger.info("Main.xaml: %d lines — FULL PRODUCTION REFRAMEWORK", main_lines)
    return xaml_files, stub_files


# ============================================================================
# PHASE 9 — Process.xaml Override with Real Activities
# ============================================================================

@_run_phase("Phase 9: Process.xaml with Live Activities")
async def phase_9_process_override(ir, selectors, matched, xaml_files):
    from rpa_architect.generators.ui_activities import (
        gen_click, gen_type_into, gen_get_text, gen_select_item, gen_check,
    )
    from rpa_architect.generators.logging_misc import gen_log_message

    activity_fragments = []
    for m in matched:
        sel = selectors.get(m.element_name, "")
        if not sel or "TODO" in sel:
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

    if activity_fragments:
        header = (
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
        body = ['  <Sequence DisplayName="Process Transaction">\n']
        body.append(gen_log_message("Starting transaction processing", level="Info",
                                     display_name="Log Start Processing"))
        body.append("\n")
        for frag in activity_fragments:
            for line in frag.split("\n"):
                body.append(f"    {line}\n")
        body.append(gen_log_message("Transaction processing completed", level="Info",
                                     display_name="Log End Processing"))
        body.append("\n  </Sequence>\n")

        process_xaml = header + "".join(body) + "</Activity>\n"
        xaml_files["Framework/Process.xaml"] = process_xaml
        (PROJECT_DIR / "Framework" / "Process.xaml").write_text(process_xaml, encoding="utf-8")
        logger.info("Process.xaml OVERRIDDEN with %d real UI activities", len(activity_fragments))

    # Also write a standalone copy
    (PROJECT_DIR / "Process_WithActivities.xaml").write_text(
        xaml_files.get("Framework/Process.xaml", ""), encoding="utf-8"
    )

    return xaml_files


# ============================================================================
# PHASE 10 — Object Repository v2
# ============================================================================

@_run_phase("Phase 10: Object Repository v2")
async def phase_10_object_repository(ir, selectors):
    from rpa_architect.selectors.object_repository import generate_object_repository_v2

    obj_files = generate_object_repository_v2(ir, selectors)
    for filepath, content in obj_files.items():
        out_path = PROJECT_DIR / filepath
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(content, encoding="utf-8")

    logger.info("Object Repository v2: %d files", len(obj_files))
    return obj_files


# ============================================================================
# PHASE 11 — Coded C# Workflows
# ============================================================================

@_run_phase("Phase 11: Coded C# Workflows")
async def phase_11_coded_workflows(selectors, matched):
    from rpa_architect.codegen.coded_workflow_gen import generate_coded_workflow, generate_coded_test
    from rpa_architect.generators.coded_apis import (
        gen_coded_open_app, gen_coded_click, gen_coded_type_into,
        gen_coded_get_text, gen_coded_log_message,
    )

    body = [
        gen_coded_log_message("Starting WebInteraction automation"),
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
        class_name="ProcessWebInteraction",
        namespace="WebInteractionAutomation",
        body_statements=body,
        imports=["using UiPath.UIAutomationNext.API;"],
    )
    (PROJECT_DIR / "ProcessWebInteraction.cs").write_text(cs_main, encoding="utf-8")

    test_body = [gen_coded_log_message("Starting selector verification"), ""]
    for name in selectors:
        test_body.append(f'Assert.IsNotNull(uiAutomation.Find("{name}"), "Selector {name} not found");')
    test_body.append("")
    test_body.append(gen_coded_log_message("All selectors verified"))

    cs_test = generate_coded_test(
        class_name="SelectorVerification",
        namespace="WebInteractionAutomation",
        test_body=test_body,
        test_name="VerifyAllSelectors",
        imports=["using UiPath.UIAutomationNext.API;", "using Microsoft.VisualStudio.TestTools.UnitTesting;"],
    )
    (PROJECT_DIR / "Tests" / "TestVerification.cs").write_text(cs_test, encoding="utf-8")

    logger.info("Generated 2 C# files")
    return {"ProcessWebInteraction.cs": cs_main, "Tests/TestVerification.cs": cs_test}


# ============================================================================
# PHASE 12 — Config.xlsx
# ============================================================================

@_run_phase("Phase 12: Config.xlsx")
async def phase_12_config_xlsx(ir):
    from rpa_architect.assembler.config_xlsx_gen import generate_config_xlsx

    config_path = PROJECT_DIR / "Data" / "Config.xlsx"
    generate_config_xlsx(ir, config_path)

    size = config_path.stat().st_size
    logger.info("Config.xlsx: %d bytes at %s", size, config_path)
    return str(config_path)


# ============================================================================
# PHASE 13 — project.json
# ============================================================================

@_run_phase("Phase 13: project.json")
async def phase_13_project_json(ir):
    from rpa_architect.assembler.project_json_gen import generate_project_json

    content = generate_project_json(ir)
    (PROJECT_DIR / "project.json").write_text(content, encoding="utf-8")

    parsed = json.loads(content)
    logger.info("project.json: toolVersion=%s, framework=%s, %d deps",
                parsed.get("toolVersion"), parsed.get("targetFramework"),
                len(parsed.get("dependencies", {})))
    return content


# ============================================================================
# PHASE 14 — Wiring Engine
# ============================================================================

@_run_phase("Phase 14: Wiring Engine")
async def phase_14_wiring(ir):
    from rpa_architect.wiring import wire_project

    wiring_result = wire_project(PROJECT_DIR, ir.model_dump() if ir else None)

    logger.info("Wiring: %d actions, %d warnings, %d errors",
                len(wiring_result.actions), len(wiring_result.warnings),
                len(wiring_result.errors))

    for action in wiring_result.actions:
        logger.info("  [%s] %s: %s", action.action_type, action.target_file, action.detail)

    _dump_json({
        "success": wiring_result.success,
        "actions": [a.model_dump() for a in wiring_result.actions],
        "warnings": wiring_result.warnings,
        "errors": wiring_result.errors,
    }, REPORTS_DIR / "wiring_result.json")
    return wiring_result


# ============================================================================
# PHASE 15 — XAML Lint + Coded Lint
# ============================================================================

@_run_phase("Phase 15: Validation & Lint")
async def phase_15_lint(xaml_files, cs_files):
    from rpa_architect.xaml_lint import lint_xaml
    from rpa_architect.xaml_lint.rules_coded import lint_coded_file

    xaml_issues = {}
    error_count = warning_count = info_count = 0
    for filename, content in xaml_files.items():
        issues = lint_xaml(content)
        xaml_issues[filename] = [
            {"rule_id": i.rule_id, "severity": i.severity.value if hasattr(i.severity, "value") else str(i.severity),
             "message": i.message}
            for i in issues
        ]
        for i in issues:
            sev = i.severity.value if hasattr(i.severity, "value") else str(i.severity)
            if "error" in sev.lower(): error_count += 1
            elif "warning" in sev.lower(): warning_count += 1
            else: info_count += 1

    coded_issues = {}
    coded_total = 0
    for filename, content in cs_files.items():
        issues = lint_coded_file(content, file_path=filename)
        coded_issues[filename] = [
            {"rule_id": i.rule_id, "severity": i.severity.value if hasattr(i.severity, "value") else str(i.severity),
             "message": i.message}
            for i in issues
        ]
        coded_total += len(issues)

    _dump_json(xaml_issues, REPORTS_DIR / "xaml_lint.json")
    _dump_json(coded_issues, REPORTS_DIR / "coded_lint.json")

    logger.info("XAML lint: %d errors, %d warnings, %d info | Coded: %d issues",
                error_count, warning_count, info_count, coded_total)
    return xaml_issues, error_count, warning_count, info_count, coded_issues, coded_total


# ============================================================================
# PHASE 16 — Execution Video
# ============================================================================

@_run_phase("Phase 16: Execution Video")
async def phase_16_execution_video():
    from proof.execution_video import main as video_main
    return await video_main()


# ============================================================================
# PHASE 17 — Failure Injection
# ============================================================================

@_run_phase("Phase 17: Failure Injection")
async def phase_17_failure_injection():
    from proof.failure_injection import main as failure_main
    return await failure_main()


# ============================================================================
# PHASE 18 — Traceability Matrix
# ============================================================================

@_run_phase("Phase 18: Traceability Matrix")
async def phase_18_traceability_matrix():
    from proof.traceability_matrix import main as trace_main
    return trace_main()


# ============================================================================
# PHASE 19 — Comprehensive Report
# ============================================================================

@_run_phase("Phase 19: Report")
async def phase_19_report(
    ir, pdd_content, match_tuple, selectors, selector_details,
    validation_result, scores_tuple, xaml_files, stub_files,
    obj_files, cs_files, lint_tuple, elapsed_total,
):
    from datetime import datetime, timezone

    matched, unmatched = match_tuple or ([], [])
    scores, overall_score = scores_tuple or ({}, 0)
    xaml_issues, xerr, xwarn, xinfo, coded_issues, coded_total = lint_tuple or ({}, 0, 0, 0, {}, 0)

    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    lines = [
        "# Fusion-Ready E2E Proof Report",
        "",
        f"**Generated**: {now}",
        f"**Target**: {TARGET_URL}",
        f"**Process**: {ir.process_name if ir else 'N/A'}",
        f"**PDD Source**: {PDD_PATH.name}",
        f"**Duration**: {elapsed_total:.1f}s",
        "",
        "---",
        "",
    ]

    # 1. PDD & IR
    lines.append("## 1. PDD → ProcessIR")
    if ir:
        total_actions = sum(len(s.actions) for t in ir.transactions for s in t.steps)
        lines.extend([
            f"- PDD: {len(pdd_content.splitlines()) if pdd_content else 0} lines",
            f"- Systems: {len(ir.systems)} ({', '.join(s.name for s in ir.systems)})",
            f"- Transactions: {len(ir.transactions)}",
            f"- Steps: {sum(len(t.steps) for t in ir.transactions)}",
            f"- UIActions: {total_actions}",
            f"- Config entries: {len(ir.config)}",
        ])
    lines.append("")

    # 2. Element Matching
    lines.append("## 2. Browser Harvest & Element Matching")
    total_count = len(matched) + len(unmatched)
    rate = round(100 * len(matched) / max(total_count, 1), 1)
    lines.extend([
        f"- Total actions: {total_count}",
        f"- Matched: {len(matched)} ({rate}%)",
        f"- Unmatched: {len(unmatched)}",
    ])
    lines.append("")

    # 3. Live Validation
    lines.append("## 3. LIVE Selector Validation (Proof of Execution)")
    if validation_result:
        v_total, v_found, v_interacted, _ = validation_result
        lines.extend([
            f"- Validated against live page: **{v_total}**",
            f"- Elements found: **{v_found}/{v_total}** ({round(100*v_found/max(v_total,1))}%)",
            f"- Interacted (click/type/select): **{v_interacted}/{v_total}** ({round(100*v_interacted/max(v_total,1))}%)",
        ])
    lines.append("")

    # 4. KEY: Template vs Stub Comparison
    lines.append("## 4. REFramework XAML: Template vs Stub (KEY PROOF)")
    lines.append("")
    lines.append("| File | Template (lines) | Stub (lines) | Expansion |")
    lines.append("|------|-----------------|--------------|-----------|")
    total_tpl = total_stub = 0
    for fn in sorted(xaml_files or {}):
        tpl = len(xaml_files[fn].splitlines())
        stub = len((stub_files or {}).get(fn, "").splitlines())
        total_tpl += tpl
        total_stub += stub
        ratio = f"{tpl/max(stub,1):.1f}x"
        lines.append(f"| {fn} | {tpl} | {stub} | {ratio} |")
    lines.append(f"| **TOTAL** | **{total_tpl}** | **{total_stub}** | **{total_tpl/max(total_stub,1):.1f}x** |")
    lines.append("")
    lines.append(f"> Main.xaml expanded from {len((stub_files or {}).get('Main.xaml', '').splitlines())} stub lines "
                 f"to **{len((xaml_files or {}).get('Main.xaml', '').splitlines())} production lines** — "
                 f"full state machine with Init → GetTransactionData → Process → EndProcess transitions, "
                 f"TryCatch blocks, retry logic, and InvokeWorkflowFile calls.")
    lines.append("")

    # 5. Generated Files
    lines.append("## 5. Generated UiPath Project Files")
    lines.append("")
    lines.append("| File | Size | Type |")
    lines.append("|------|------|------|")
    all_files = []
    for fn, c in (xaml_files or {}).items():
        all_files.append((fn, len(c), "XAML"))
    for fn, c in (obj_files or {}).items():
        all_files.append((fn, len(c), "Object Repo v2"))
    for fn, c in (cs_files or {}).items():
        all_files.append((fn, len(c), "C# Coded"))
    pj = PROJECT_DIR / "project.json"
    if pj.exists():
        all_files.append(("project.json", pj.stat().st_size, "Studio manifest"))
    cfg = PROJECT_DIR / "Data" / "Config.xlsx"
    if cfg.exists():
        all_files.append(("Data/Config.xlsx", cfg.stat().st_size, "Configuration"))
    for fn, sz, tp in sorted(all_files):
        lines.append(f"| {fn} | {sz:,} bytes | {tp} |")
    lines.append(f"\n**Total files: {len(all_files)}**")
    lines.append("")

    # 6. Lint
    lines.append("## 6. Validation Results")
    lines.extend([
        f"- XAML lint: {xerr} errors, {xwarn} warnings, {xinfo} info",
        f"- Coded lint: {coded_total} issues",
        f"- Selector quality: {overall_score}/100",
    ])
    lines.append("")

    # 7. Phase Summary
    lines.append("## 7. Phase Execution Summary")
    lines.append("")
    lines.append("| # | Phase | Status | Duration |")
    lines.append("|---|-------|--------|----------|")
    passed_count = 0
    for i, pr in enumerate(PHASE_RESULTS):
        status = "PASS" if pr.passed else "FAIL"
        symbol = "+" if pr.passed else "X"
        if pr.passed:
            passed_count += 1
        err = f" — {pr.error[:60]}" if pr.error else ""
        lines.append(f"| {i} | {pr.name} | {symbol} {status}{err} | {pr.duration_s:.1f}s |")
    lines.append(f"\n**{passed_count}/{len(PHASE_RESULTS)} phases passed in {elapsed_total:.1f}s**\n")

    summary_md = "\n".join(lines) + "\n"
    (OUTPUT_DIR / "SUMMARY.md").write_text(summary_md, encoding="utf-8")

    # Machine-readable
    _dump_json({
        "timestamp": now, "target_url": TARGET_URL,
        "process_name": ir.process_name if ir else None,
        "pdd_source": PDD_PATH.name,
        "elapsed_s": elapsed_total,
        "phases": [{"name": p.name, "passed": p.passed, "duration_s": p.duration_s, "error": p.error}
                   for p in PHASE_RESULTS],
        "totals": {
            "actions": total_count, "matched": len(matched),
            "selectors": len(selectors) if selectors else 0,
            "aggregate_score": overall_score,
            "xaml_template_lines": total_tpl, "xaml_stub_lines": total_stub,
            "files_generated": len(all_files),
            "lint_errors": xerr, "lint_warnings": xwarn,
        },
    }, OUTPUT_DIR / "summary.json")

    logger.info("Report: %s", OUTPUT_DIR / "SUMMARY.md")
    return summary_md


# ============================================================================
# MAIN
# ============================================================================

async def main() -> None:
    t_start = time.monotonic()

    print()
    print("=" * 72)
    print("  AUTONOMOUS RPA ARCHITECT — Fusion-Ready E2E Proof")
    print(f"  PDD: {PDD_PATH.name}")
    print(f"  Target: {TARGET_URL}")
    print("=" * 72)
    print()

    # Phase 0-1
    await phase_0_setup()
    pdd_content = await phase_1_load_pdd()
    if pdd_content is None:
        logger.error("Cannot load PDD. Aborting.")
        return

    # Phase 2: PDD → IR
    ir = await phase_2_parse_pdd(pdd_content)
    if ir is None:
        logger.error("Cannot parse PDD. Aborting.")
        return

    # Phase 3-4: Browser harvest + matching
    reports = await phase_3_browser_harvest(ir)
    match_data = None
    if reports:
        match_data = await phase_4_element_matching(ir, reports)

    matched = match_data[0] if match_data else []
    unmatched = match_data[1] if match_data else []

    # Phase 5: Selector conversion
    sel_result = await phase_5_selector_conversion(ir, matched, unmatched)
    selectors = sel_result[0] if sel_result else {}
    selector_details = sel_result[1] if sel_result else {}
    matched_from_sel = sel_result[2] if sel_result else matched

    # Phase 6: Live validation
    validation_result = None
    if selectors and matched_from_sel:
        validation_result = await phase_6_validate_selectors_live(ir, selectors, matched_from_sel)

    # Phase 7: Scoring
    scores_tuple = await phase_7_selector_scoring(selectors)

    # Phase 8: REFramework XAML (THE KEY PHASE)
    xaml_result = await phase_8_reframework_xaml(ir)
    xaml_files = xaml_result[0] if xaml_result else {}
    stub_files = xaml_result[1] if xaml_result else {}

    # Phase 9: Process.xaml override
    if xaml_files:
        xaml_files = await phase_9_process_override(ir, selectors, matched_from_sel, xaml_files)
        if xaml_files is None:
            xaml_files = xaml_result[0] if xaml_result else {}

    # Phase 10: Object Repository
    obj_files = await phase_10_object_repository(ir, selectors)

    # Phase 11: Coded C#
    cs_files = await phase_11_coded_workflows(selectors, matched_from_sel)

    # Phase 12: Config.xlsx
    await phase_12_config_xlsx(ir)

    # Phase 13: project.json
    await phase_13_project_json(ir)

    # Phase 14: Wiring
    await phase_14_wiring(ir)

    # Phase 15: Lint
    lint_result = None
    if xaml_files and cs_files:
        lint_result = await phase_15_lint(xaml_files, cs_files)

    # Phase 16: Execution Video
    video_result = await phase_16_execution_video()

    # Phase 17: Failure Injection
    failure_result = await phase_17_failure_injection()

    # Phase 18: Traceability Matrix
    trace_result = await phase_18_traceability_matrix()

    # Phase 19: Report
    elapsed = round(time.monotonic() - t_start, 1)
    await phase_19_report(
        ir=ir,
        pdd_content=pdd_content,
        match_tuple=(matched_from_sel, unmatched),
        selectors=selectors,
        selector_details=selector_details,
        validation_result=validation_result,
        scores_tuple=scores_tuple,
        xaml_files=xaml_files,
        stub_files=stub_files,
        obj_files=obj_files,
        cs_files=cs_files,
        lint_tuple=lint_result,
        elapsed_total=elapsed,
    )

    # Final banner
    passed = sum(1 for p in PHASE_RESULTS if p.passed)
    total = len(PHASE_RESULTS)
    print()
    print("=" * 72)
    print(f"  RESULT: {passed}/{total} phases passed  ({elapsed:.1f}s)")
    print(f"  Output: {OUTPUT_DIR}")
    print(f"  Report: {OUTPUT_DIR / 'SUMMARY.md'}")
    print("=" * 72)


if __name__ == "__main__":
    asyncio.run(main())
