"""Browser-based selector harvesting using Playwright.

Navigates to actual application URLs found in the ProcessIR, follows
documented steps through the live UI, and harvests real selectors from
interactive DOM elements.
"""

from __future__ import annotations

import logging
import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any

from rpa_architect.ir.schema import ProcessIR, Step
from rpa_architect.selectors.uipath_converter import HarvestedElement

if TYPE_CHECKING:
    from rpa_architect.utils.llm_client import LLMClient

logger = logging.getLogger(__name__)

# Interactive element CSS selector for DOM discovery
_INTERACTIVE_SELECTOR = ", ".join([
    "input",
    "button",
    "select",
    "textarea",
    "a[href]",
    "[role='button']",
    "[role='textbox']",
    "[role='combobox']",
    "[role='checkbox']",
    "[role='radio']",
    "[role='link']",
    "[role='menuitem']",
    "[role='tab']",
    "[onclick]",
    "[data-testid]",
])


@dataclass
class HarvestConfig:
    """Configuration for browser-based selector harvesting."""

    enabled: bool = False
    headless: bool = True
    timeout_ms: int = 30000
    viewport_width: int = 1920
    viewport_height: int = 1080
    screenshot_dir: Path | None = None
    max_elements_per_page: int = 200
    credential_env_prefix: str = "HARVEST_CRED_"
    user_data_dir: Path | None = None
    """If set, Chromium uses ``launch_persistent_context`` so cookies and
    localStorage persist across runs. Log in once, harvest forever."""


@dataclass
class HarvestResult:
    """Result of harvesting a single step."""

    step_id: str
    elements: list[HarvestedElement] = field(default_factory=list)
    screenshot_path: str | None = None
    page_url: str = ""
    errors: list[str] = field(default_factory=list)


@dataclass
class BrowserHarvestReport:
    """Aggregate harvest report for a single system."""

    system_name: str
    results: list[HarvestResult] = field(default_factory=list)
    selectors: dict[str, str] = field(default_factory=dict)
    confidence_scores: dict[str, float] = field(default_factory=dict)
    fallbacks: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)


def _get_credentials(system_name: str, prefix: str) -> tuple[str, str] | None:
    """Look up credentials from environment variables.

    Expected format: {prefix}{SYSTEM_NAME}_USER / {prefix}{SYSTEM_NAME}_PASS
    """
    safe_name = re.sub(r"[^A-Z0-9]", "_", system_name.upper())
    user = os.environ.get(f"{prefix}{safe_name}_USER")
    password = os.environ.get(f"{prefix}{safe_name}_PASS")
    if user and password:
        return user, password
    return None


async def _extract_element_attrs(page: Any, element: Any) -> dict[str, Any]:
    """Extract all relevant attributes from a Playwright element handle."""
    try:
        attrs = await element.evaluate("""el => {
            const rect = el.getBoundingClientRect();
            return {
                tag: el.tagName.toLowerCase(),
                id: el.id || '',
                name: el.getAttribute('name') || '',
                classes: Array.from(el.classList),
                aria_label: el.getAttribute('aria-label') || '',
                aria_role: el.getAttribute('role') || '',
                inner_text: (el.innerText || '').substring(0, 200),
                placeholder: el.getAttribute('placeholder') || '',
                input_type: el.getAttribute('type') || '',
                data_testid: el.getAttribute('data-testid') || '',
                bounding_box: {
                    x: rect.x,
                    y: rect.y,
                    width: rect.width,
                    height: rect.height,
                },
            };
        }""")
        return attrs
    except Exception as exc:
        logger.debug("Failed to extract element attributes: %s", exc)
        return {}


def _attrs_to_element(attrs: dict[str, Any], page_url: str, xpath: str = "") -> HarvestedElement:
    """Convert raw attribute dict to a HarvestedElement."""
    return HarvestedElement(
        tag=attrs.get("tag", ""),
        id=attrs.get("id", ""),
        name=attrs.get("name", ""),
        classes=attrs.get("classes", []),
        aria_label=attrs.get("aria_label", ""),
        aria_role=attrs.get("aria_role", ""),
        inner_text=attrs.get("inner_text", ""),
        placeholder=attrs.get("placeholder", ""),
        input_type=attrs.get("input_type", ""),
        data_testid=attrs.get("data_testid", ""),
        xpath=xpath,
        bounding_box=attrs.get("bounding_box", {}),
        page_url=page_url,
    )


async def _discover_elements(
    page: Any,
    max_elements: int = 200,
) -> list[HarvestedElement]:
    """Discover interactive elements on the current page.

    Uses DOM queries for interactive elements and extracts attributes.
    """
    page_url = page.url
    elements: list[HarvestedElement] = []

    try:
        handles = await page.query_selector_all(_INTERACTIVE_SELECTOR)
    except Exception as exc:
        logger.warning("DOM query failed: %s", exc)
        return elements

    for handle in handles[:max_elements]:
        attrs = await _extract_element_attrs(page, handle)
        if attrs:
            el = _attrs_to_element(attrs, page_url)
            elements.append(el)

    # Also try accessibility tree for semantic names
    try:
        snapshot = await page.accessibility.snapshot()
        if snapshot:
            _enrich_from_a11y(elements, snapshot)
    except Exception as exc:
        logger.debug("Accessibility snapshot failed: %s", exc)

    return elements


def _enrich_from_a11y(
    elements: list[HarvestedElement],
    a11y_node: dict[str, Any],
    depth: int = 0,
) -> None:
    """Enrich elements with accessibility tree names.

    Walks the a11y tree and tries to match nodes to harvested elements
    by role+name. When matched, sets the accessibility_name field.
    """
    if depth > 20:
        return

    name = a11y_node.get("name", "")

    if name:
        for el in elements:
            if not el.accessibility_name and (
                (el.aria_label and el.aria_label == name)
                or (el.inner_text and el.inner_text.strip() == name)
                or (el.id and el.id == name)
            ):
                el.accessibility_name = name
                break

    for child in a11y_node.get("children", []):
        _enrich_from_a11y(elements, child, depth + 1)


async def _harvest_step(
    page: Any,
    step: Step,
    system_url: str,
    config: HarvestConfig,
    screenshot_dir: Path | None = None,
) -> HarvestResult:
    """Harvest elements for a single step."""
    result = HarvestResult(step_id=step.id)

    # Navigate if step has a different URL
    step_url = step.parameters.get("url", "")
    target_url = step_url if step_url else system_url
    if not target_url:
        result.errors.append(f"No URL available for step {step.id}")
        return result

    try:
        current_url = page.url
        if target_url and target_url != current_url:
            await page.goto(target_url, wait_until="networkidle", timeout=config.timeout_ms)
        else:
            # Wait for any pending loads
            try:
                await page.wait_for_load_state("networkidle", timeout=5000)
            except Exception:
                pass

        result.page_url = page.url

        # Take screenshot if configured
        if screenshot_dir:
            screenshot_path = screenshot_dir / f"{step.id}.png"
            screenshot_path.parent.mkdir(parents=True, exist_ok=True)
            await page.screenshot(path=str(screenshot_path), full_page=False)
            result.screenshot_path = str(screenshot_path)

        # Discover elements
        result.elements = await _discover_elements(page, config.max_elements_per_page)
        logger.info(
            "Step %s: discovered %d interactive elements on %s",
            step.id, len(result.elements), result.page_url,
        )

    except Exception as exc:
        error_msg = f"Step {step.id} navigation/harvest failed: {exc}"
        result.errors.append(error_msg)
        logger.warning(error_msg)

    return result


async def harvest_selectors_from_browser(
    ir: ProcessIR,
    config: HarvestConfig | None = None,
    llm_client: LLMClient | None = None,
) -> dict[str, BrowserHarvestReport]:
    """Harvest selectors from live browser sessions for all web systems in the IR.

    For each web system:
    1. Launches a Playwright browser
    2. Navigates to the system URL
    3. Attempts login if required (using env-var credentials)
    4. For each step referencing the system, discovers interactive elements
    5. Matches elements to UIActions and converts to UiPath selectors

    Args:
        ir: The ProcessIR containing systems and steps.
        config: Harvest configuration. Uses defaults if None.
        llm_client: Optional LLM client for tier-2 element matching.

    Returns:
        Dictionary mapping system_name -> BrowserHarvestReport.
    """
    try:
        from playwright.async_api import async_playwright
    except ImportError:
        logger.warning(
            "Playwright is not installed. Install with: pip install 'autonomous-rpa-architect[harvest]'"
        )
        return {}

    if config is None:
        config = HarvestConfig(enabled=True)

    from rpa_architect.selectors.element_matcher import match_actions_to_elements
    from rpa_architect.selectors.uipath_converter import batch_convert

    reports: dict[str, BrowserHarvestReport] = {}

    # Only harvest web systems with URLs
    web_systems = [s for s in ir.systems if s.type == "web" and s.url]

    if not web_systems:
        logger.info("No web systems with URLs found in IR; skipping browser harvest.")
        return reports

    async with async_playwright() as pw:
        for system in web_systems:
            report = BrowserHarvestReport(system_name=system.name)

            browser = None
            try:
                viewport = {
                    "width": config.viewport_width,
                    "height": config.viewport_height,
                }
                if config.user_data_dir is not None:
                    config.user_data_dir.mkdir(parents=True, exist_ok=True)
                    context = await pw.chromium.launch_persistent_context(
                        user_data_dir=str(config.user_data_dir),
                        headless=config.headless,
                        viewport=viewport,
                        timeout=config.timeout_ms,
                    )
                    page = context.pages[0] if context.pages else await context.new_page()
                else:
                    browser = await pw.chromium.launch(
                        headless=config.headless,
                        timeout=config.timeout_ms,
                    )
                    context = await browser.new_context(viewport=viewport)
                    page = await context.new_page()

                # Navigate to system URL
                await page.goto(system.url, wait_until="networkidle", timeout=config.timeout_ms)

                # Attempt login if required
                if system.login_required:
                    creds = _get_credentials(system.name, config.credential_env_prefix)
                    if creds:
                        logger.info("Attempting login for system '%s'", system.name)
                        try:
                            await _attempt_login(page, creds[0], creds[1], config.timeout_ms)
                        except Exception as exc:
                            warn = f"Login failed for {system.name}: {exc}"
                            report.errors.append(warn)
                            logger.warning(warn)
                    else:
                        warn = f"No credentials found for {system.name}; harvesting pre-login page only"
                        report.fallbacks.append(warn)
                        logger.info(warn)

                # Collect steps for this system
                system_steps = _collect_system_steps(ir, system.name)

                # Screenshot directory per system
                screenshot_dir = None
                if config.screenshot_dir:
                    screenshot_dir = config.screenshot_dir / system.name

                # Harvest each step
                all_elements: list[HarvestedElement] = []
                for step in system_steps:
                    harvest_result = await _harvest_step(
                        page, step, system.url, config, screenshot_dir
                    )
                    report.results.append(harvest_result)
                    all_elements.extend(harvest_result.elements)
                    report.errors.extend(harvest_result.errors)

                # Match actions to elements
                actions = _collect_step_actions(system_steps)
                if actions and all_elements:
                    matches = await match_actions_to_elements(actions, all_elements, llm_client)
                    selectors = batch_convert(matches)
                    report.selectors.update(selectors)
                    for m in matches:
                        report.confidence_scores[m.element_name] = m.confidence
                        if m.match_method == "unmatched":
                            report.fallbacks.append(
                                f"{m.element_name}: no match for '{m.action.target}'"
                            )

                await context.close()
                if browser is not None:
                    await browser.close()

            except Exception as exc:
                error_msg = f"Browser harvest failed for {system.name}: {exc}"
                report.errors.append(error_msg)
                logger.warning(error_msg)

            reports[system.name] = report

    return reports


async def _attempt_login(
    page: Any,
    username: str,
    password: str,
    timeout_ms: int,
) -> None:
    """Attempt to fill and submit a login form."""
    # Look for username field
    username_selectors = [
        "input[name='username']",
        "input[name='user']",
        "input[name='email']",
        "input[type='email']",
        "input[id='username']",
        "input[id='email']",
        "input[autocomplete='username']",
    ]
    for sel in username_selectors:
        try:
            el = await page.query_selector(sel)
            if el:
                await el.fill(username)
                break
        except Exception:
            continue

    # Look for password field
    password_selectors = [
        "input[type='password']",
        "input[name='password']",
        "input[name='pass']",
    ]
    for sel in password_selectors:
        try:
            el = await page.query_selector(sel)
            if el:
                await el.fill(password)
                break
        except Exception:
            continue

    # Look for submit button
    submit_selectors = [
        "button[type='submit']",
        "input[type='submit']",
        "button:has-text('Log in')",
        "button:has-text('Sign in')",
        "button:has-text('Login')",
    ]
    for sel in submit_selectors:
        try:
            el = await page.query_selector(sel)
            if el:
                await el.click()
                break
        except Exception:
            continue

    # Wait for navigation
    try:
        await page.wait_for_load_state("networkidle", timeout=timeout_ms)
    except Exception:
        pass


def _collect_system_steps(ir: ProcessIR, system_name: str) -> list[Step]:
    """Collect all steps referencing a given system, in order."""
    steps: list[Step] = []
    for txn in ir.transactions:
        _collect_steps_recursive(txn.steps, system_name, steps)
    return steps


def _collect_steps_recursive(
    steps: list[Step],
    system_name: str,
    result: list[Step],
) -> None:
    """Recursively collect steps for a system."""
    for step in steps:
        if step.system_ref == system_name:
            result.append(step)
        _collect_steps_recursive(step.substeps, system_name, result)


def _collect_step_actions(
    steps: list[Step],
) -> list[tuple[str, int, Any]]:
    """Collect (step_id, index, UIAction) tuples from steps."""
    from rpa_architect.ir.schema import UIAction

    actions: list[tuple[str, int, UIAction]] = []
    for step in steps:
        for idx, action in enumerate(step.actions):
            actions.append((step.id, idx, action))
    return actions
