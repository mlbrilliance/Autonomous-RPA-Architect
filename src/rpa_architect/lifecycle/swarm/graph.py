"""Swarm orchestrator — parallel specialists, arbiter, staging, PR.

Modeled as a plain async class rather than a LangGraph sub-graph because
the work fans out to N specialists in one ``asyncio.gather`` call; a
LangGraph ``Send`` API equivalent would be nine nodes and four edges
for behavior that's four lines of Python. The main lifecycle graph
still calls into this orchestrator from a single node (see
:func:`swarm_node` in ``lifecycle.nodes``).

Fan-out shape:

    fetch_failure_bundle
          │
     parse_xaml_files    ← xaml_ast.read_xaml per file
          │
    gather([selector_repair, null_exception, timing_repair, business_rule])
          │
       arbiter
          │
    if winner has patches: staging_validator → (success?) → pr_opener
    else:                     requires_escalation = True
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from rpa_architect.lifecycle.state import (
    FailureBundle,
    FixCandidate,
    StagingResult,
)
from rpa_architect.lifecycle.swarm.arbiter import Arbiter, ArbiterVerdict
from rpa_architect.lifecycle.swarm.failure_bundle import FailureBundleFetcher
from rpa_architect.lifecycle.swarm.pr_opener import PROpener, PROpenResult
from rpa_architect.lifecycle.swarm.staging_validator import StagingValidator
from rpa_architect.xaml_ast import XamlDocument, XamlParseError, read_xaml

logger = logging.getLogger("rpa_architect.lifecycle.swarm.graph")


class SpecialistLike(Protocol):
    async def propose(
        self,
        bundle: FailureBundle,
        xaml_docs: dict[str, XamlDocument],
        *,
        target_url: str | None,
    ) -> FixCandidate | None: ...


class FetcherLike(Protocol):
    async def fetch(self, job_id: str) -> FailureBundle: ...


class StagerLike(Protocol):
    async def validate(
        self, bundle: FailureBundle, candidate: FixCandidate
    ) -> StagingResult: ...


class PROpenerLike(Protocol):
    def open(
        self,
        *,
        bundle: FailureBundle,
        candidate: FixCandidate,
        base_branch: str,
        staging_url: str,
    ) -> PROpenResult: ...


@dataclass
class SwarmVerdict:
    """Everything the lifecycle graph needs after a heal attempt."""

    bundle: FailureBundle
    arbiter_verdict: ArbiterVerdict
    staging: StagingResult | None
    staging_success: bool
    pr_url: str
    requires_escalation: bool
    candidates: list[FixCandidate]


@dataclass
class SwarmOrchestrator:
    """Driver that fans out to specialists and funnels the winner to PR."""

    fetcher: FetcherLike
    specialists: list[SpecialistLike]
    staging_validator: StagerLike
    pr_opener: PROpenerLike
    repo_root: Path
    base_branch: str
    target_url: str | None

    async def heal(self, *, job_id: str) -> SwarmVerdict:
        bundle = await self.fetcher.fetch(job_id)
        logger.info(
            "swarm: healing job=%s state=%s exception=%s",
            bundle.job_id,
            bundle.state,
            bundle.exception_type,
        )

        xaml_docs = _parse_all(bundle.xaml_files)
        candidates = await _gather_candidates(
            self.specialists, bundle, xaml_docs, self.target_url
        )
        verdict = Arbiter().arbitrate(candidates)

        if verdict.winner is None or not verdict.winner.patches:
            logger.info("swarm: no actionable candidate — escalating")
            return SwarmVerdict(
                bundle=bundle,
                arbiter_verdict=verdict,
                staging=None,
                staging_success=False,
                pr_url="",
                requires_escalation=True,
                candidates=candidates,
            )

        staging = await self.staging_validator.validate(bundle, verdict.winner)
        if not staging.success:
            logger.warning(
                "swarm: staging failed for %s — not opening PR (%s)",
                verdict.winner.specialist,
                staging.message,
            )
            return SwarmVerdict(
                bundle=bundle,
                arbiter_verdict=verdict,
                staging=staging,
                staging_success=False,
                pr_url="",
                requires_escalation=True,
                candidates=candidates,
            )

        pr_result = self.pr_opener.open(
            bundle=bundle,
            candidate=verdict.winner,
            base_branch=self.base_branch,
            staging_url=_staging_url_from_result(staging),
        )
        logger.info(
            "swarm: opened PR %s for job=%s specialist=%s",
            pr_result.pr_url,
            bundle.job_id,
            verdict.winner.specialist,
        )
        return SwarmVerdict(
            bundle=bundle,
            arbiter_verdict=verdict,
            staging=staging,
            staging_success=True,
            pr_url=pr_result.pr_url,
            requires_escalation=False,
            candidates=candidates,
        )


# ---------------------------------------------------------------------------
# factory for production assembly
# ---------------------------------------------------------------------------


def build_default_swarm(
    *,
    client,
    repo_root: Path,
    base_branch: str = "main",
    target_url: str | None = None,
    staging_folder: str = "Shared/Staging",
) -> SwarmOrchestrator:
    """Wire the standard four specialists + Orchestrator-backed fetcher.

    Importing inside the function avoids a hard dep on selector repair's
    ``Harvester`` implementation for callers that want to use a subset
    of specialists in tests.
    """
    from rpa_architect.lifecycle.swarm.selector_repair import SelectorRepairSpecialist
    from rpa_architect.lifecycle.swarm.specialists import (
        BusinessRuleSpecialist,
        NullExceptionSpecialist,
        TimingRepairSpecialist,
    )

    # Production harvester adapter lives in a lazy import inside a helper
    # so pure-Python unit tests of swarm.graph don't need Playwright.
    from rpa_architect.lifecycle.swarm.playwright_harvester import (
        PlaywrightHarvesterAdapter,
    )

    harvester = PlaywrightHarvesterAdapter()
    return SwarmOrchestrator(
        fetcher=FailureBundleFetcher(client),
        specialists=[
            SelectorRepairSpecialist(harvester=harvester),
            NullExceptionSpecialist(),
            TimingRepairSpecialist(),
            BusinessRuleSpecialist(),
        ],
        staging_validator=StagingValidator(client=client, staging_folder=staging_folder),
        pr_opener=PROpener(repo_root=repo_root),
        repo_root=repo_root,
        base_branch=base_branch,
        target_url=target_url,
    )


# ---------------------------------------------------------------------------
# internals
# ---------------------------------------------------------------------------


def _parse_all(xaml_files: dict[str, str]) -> dict[str, XamlDocument]:
    out: dict[str, XamlDocument] = {}
    for path, content in xaml_files.items():
        try:
            out[path] = read_xaml(content)
        except XamlParseError as exc:
            logger.warning("swarm: cannot parse %s: %s", path, exc)
    return out


async def _gather_candidates(
    specialists: list[SpecialistLike],
    bundle: FailureBundle,
    xaml_docs: dict[str, XamlDocument],
    target_url: str | None,
) -> list[FixCandidate]:
    results = await asyncio.gather(
        *(s.propose(bundle, xaml_docs, target_url=target_url) for s in specialists),
        return_exceptions=True,
    )
    candidates: list[FixCandidate] = []
    for i, r in enumerate(results):
        if isinstance(r, Exception):
            name = getattr(specialists[i], "name", f"specialist-{i}")
            logger.exception("specialist %s raised: %s", name, r)
            continue
        if r is not None:
            candidates.append(r)
    return candidates


def _staging_url_from_result(result: StagingResult) -> str:
    if not result.job_id:
        return ""
    return f"uipath-orchestrator://jobs/{result.job_id}"
