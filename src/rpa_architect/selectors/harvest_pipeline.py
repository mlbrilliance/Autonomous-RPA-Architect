"""Harvest pipeline glue module.

Wires browser harvesting into the assembly pipeline and provides
selector merging logic.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from rpa_architect.ir.schema import ProcessIR
from rpa_architect.selectors.browser_harvester import (
    HarvestConfig,
    harvest_selectors_from_browser,
)

if TYPE_CHECKING:
    from rpa_architect.utils.llm_client import LLMClient

logger = logging.getLogger(__name__)


async def run_harvest_pipeline(
    ir: ProcessIR,
    harvest_config: HarvestConfig | None = None,
    llm_client: LLMClient | None = None,
) -> dict[str, str]:
    """Run the full browser harvest pipeline and return selectors.

    Navigates to all web system URLs in the IR, discovers elements,
    matches them to UIActions, and converts to UiPath selectors.

    Args:
        ir: The ProcessIR containing systems and steps.
        harvest_config: Harvest configuration.
        llm_client: Optional LLM client for tier-2 matching.

    Returns:
        Dictionary mapping element_name -> selector_xml.
    """
    if harvest_config is None:
        harvest_config = HarvestConfig(enabled=True)

    try:
        reports = await harvest_selectors_from_browser(ir, harvest_config, llm_client)
    except Exception as exc:
        logger.warning("Browser harvest pipeline failed: %s", exc)
        return {}

    # Aggregate selectors from all system reports
    all_selectors: dict[str, str] = {}
    for system_name, report in reports.items():
        all_selectors.update(report.selectors)
        if report.errors:
            logger.warning(
                "System '%s' had %d harvest errors", system_name, len(report.errors)
            )

    logger.info("Harvest pipeline produced %d selectors", len(all_selectors))
    return all_selectors


def merge_selectors(
    harvested: dict[str, str],
    placeholders: dict[str, str],
    known_app: dict[str, str] | None = None,
) -> dict[str, str]:
    """Merge selectors from multiple sources with priority ordering.

    Priority (highest first):
    1. Browser-harvested selectors (real DOM elements)
    2. Known app selectors (pre-built library)
    3. Placeholder selectors (TODO stubs)

    Args:
        harvested: Selectors from browser harvesting.
        placeholders: Placeholder/TODO selectors.
        known_app: Optional pre-built selectors from knowledge base.

    Returns:
        Merged dictionary of element_name -> selector_xml.
    """
    merged: dict[str, str] = {}

    # Start with placeholders (lowest priority)
    merged.update(placeholders)

    # Override with known app selectors
    if known_app:
        merged.update(known_app)

    # Override with harvested selectors (highest priority)
    merged.update(harvested)

    return merged
