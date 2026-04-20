"""Adapter from the existing ``selectors.browser_harvester`` → swarm's Harvester.

Selector repair imports the ``Harvester`` Protocol with exactly one method
(``harvest_replacement``). The repo's production harvester is synchronous-ish
(wraps Playwright) and has a richer signature. This adapter narrows it.

Deliberately imported lazily from :func:`graph.build_default_swarm` so unit
tests that don't install Playwright still run.
"""

from __future__ import annotations

import logging

logger = logging.getLogger("rpa_architect.lifecycle.swarm.playwright_harvester")


class PlaywrightHarvesterAdapter:
    """Wraps :mod:`rpa_architect.selectors.browser_harvester` for the swarm.

    Returns ``None`` when harvesting is unavailable (no Playwright install)
    rather than raising — the specialist treats ``None`` as "give up".
    """

    async def harvest_replacement(
        self, *, url: str, activity_display_name: str
    ) -> str | None:
        try:
            # Lazy import so missing playwright dep does not break module import.
            from rpa_architect.selectors.browser_harvester import (
                BrowserHarvester,
                HarvestConfig,
            )
        except ImportError:
            logger.debug("playwright not installed; selector repair cannot harvest")
            return None

        try:
            harvester = BrowserHarvester(HarvestConfig(headless=True, timeout_ms=10000))
            report = await harvester.harvest_url(url, [activity_display_name])
            # Pick the highest-confidence selector whose label matches.
            for label, selector in report.selectors.items():
                if label == activity_display_name and selector:
                    return selector
            # Fallback — return any non-empty harvested selector.
            for selector in report.selectors.values():
                if selector:
                    return selector
        except Exception as exc:  # noqa: BLE001
            logger.warning("harvest failed for %s: %s", url, exc)
        return None
