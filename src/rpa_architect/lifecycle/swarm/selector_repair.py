"""The SelectorRepair specialist — the one that actually patches XAML.

Strategy:

1. Read the exception message. If it mentions a selector fragment
   (``<webctrl id='…'/>``), extract the fragment and the human-readable
   activity display name (UiPath's error text includes one).
2. Walk every parsed XAML in the bundle, find the ``ExtractedSelector``
   whose ``activity_display_name`` matches, or — as a fallback — whose
   ``selector_xml`` contains the same fragment.
3. Ask the injected :class:`Harvester` for a replacement selector by
   visiting the target URL and locating the activity. In tests we inject
   a :class:`FakeHarvester`; in production the adapter wraps
   ``rpa_architect.selectors.browser_harvester``.
4. Emit a single :class:`XamlPatch` targeting the Selector attribute of
   the matched ``<ui:Target>``. Round-trip via xaml_ast ensures the
   patched file stays byte-stable except for the selector value.

The specialist refuses to emit guesses when the harvester cannot provide
a replacement (no target URL, unreachable app, ambiguous match). The
arbiter treats a ``None`` return as "this specialist had no answer".
"""

from __future__ import annotations

import logging
import re
from typing import Protocol

from rpa_architect.lifecycle.state import FailureBundle, FixCandidate, XamlPatch
from rpa_architect.xaml_ast import (
    ExtractedSelector,
    XamlDocument,
    extract_selectors,
    patch_selector,
    write_xaml,
)

logger = logging.getLogger("rpa_architect.lifecycle.swarm.selector_repair")


class Harvester(Protocol):
    """Minimal interface a selector harvester must satisfy."""

    async def harvest_replacement(
        self, *, url: str, activity_display_name: str
    ) -> str | None: ...


_SELECTOR_FRAGMENT_RE = re.compile(r"<\s*(?:webctrl|html|wnd)[^>]*>", re.IGNORECASE)
_ACTIVITY_HINT_RE = re.compile(r"activity:\s*([^)\n,]+)", re.IGNORECASE)


class SelectorRepairSpecialist:
    """Patches a drifted selector by harvesting a replacement from the live UI."""

    name = "selector_repair"

    def __init__(self, harvester: Harvester) -> None:
        self._harvester = harvester

    async def propose(
        self,
        bundle: FailureBundle,
        xaml_docs: dict[str, XamlDocument],
        *,
        target_url: str | None,
    ) -> FixCandidate | None:
        if not _is_selector_failure(bundle):
            return None

        if not target_url:
            logger.debug(
                "selector_repair: no target URL — cannot harvest a replacement"
            )
            return None

        activity_hint = _parse_activity_hint(bundle.exception_message)
        broken_fragment = _parse_selector_fragment(bundle.exception_message)

        match = _find_matching_selector(
            xaml_docs=xaml_docs,
            activity_display_name=activity_hint,
            broken_fragment=broken_fragment,
        )
        if match is None:
            logger.debug(
                "selector_repair: failure cites activity %r / fragment %r but no "
                "matching selector was found in deployed XAML",
                activity_hint,
                broken_fragment,
            )
            return None

        file_path, doc, selector = match
        new_selector = await self._harvester.harvest_replacement(
            url=target_url,
            activity_display_name=selector.activity_display_name,
        )
        if not new_selector:
            return None

        patch_selector(doc, selector.activity_xpath, new_selector)
        patched_content = write_xaml(doc)

        return FixCandidate(
            specialist=self.name,
            confidence=0.78,
            diagnosis_category="selector_drift",
            patches=[
                XamlPatch(
                    file_path=file_path,
                    target_xpath=selector.activity_xpath,
                    attribute="Selector",
                    old_value=selector.selector_xml,
                    new_value=new_selector,
                    rationale=(
                        f"Re-harvested selector for '{selector.activity_display_name}' "
                        f"from {target_url}. Original selector no longer matches any "
                        "element; harvester returned the highest-confidence replacement."
                    ),
                )
            ],
            reasoning=(
                f"Selector drift on activity '{selector.activity_display_name}'. "
                f"Old selector {selector.selector_xml!r} → new selector {new_selector!r}."
            ),
            patched_xaml={file_path: patched_content},
        )


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------


_SELECTOR_FAILURE_TYPES = frozenset(
    {
        "SelectorNotFoundException",
        "UiElementMissingException",
        "UiElementNotFoundException",
    }
)


def _is_selector_failure(bundle: FailureBundle) -> bool:
    if bundle.exception_type in _SELECTOR_FAILURE_TYPES:
        return True
    # Some runtime paths throw a generic Exception with selector text in the message.
    return bool(_SELECTOR_FRAGMENT_RE.search(bundle.exception_message))


def _parse_selector_fragment(msg: str) -> str | None:
    m = _SELECTOR_FRAGMENT_RE.search(msg)
    return m.group(0).strip() if m else None


def _parse_activity_hint(msg: str) -> str | None:
    m = _ACTIVITY_HINT_RE.search(msg)
    return m.group(1).strip() if m else None


def _find_matching_selector(
    *,
    xaml_docs: dict[str, XamlDocument],
    activity_display_name: str | None,
    broken_fragment: str | None,
) -> tuple[str, XamlDocument, ExtractedSelector] | None:
    """Locate the selector that produced the failure across every XAML file."""
    for path, doc in xaml_docs.items():
        for sel in extract_selectors(doc):
            if activity_display_name and sel.activity_display_name == activity_display_name:
                return path, doc, sel
            if broken_fragment and broken_fragment in sel.selector_xml:
                return path, doc, sel
    return None
