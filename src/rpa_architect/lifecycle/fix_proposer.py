"""Generate and apply fix proposals based on diagnosis results."""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from rpa_architect.lifecycle.state import (
    DiagnosisResult,
    FixProposal,
    ProposedChange,
)

logger = logging.getLogger(__name__)


async def generate_fix_proposal(
    diagnosis: DiagnosisResult,
    project_dir: str,
    ir: dict[str, Any],
) -> FixProposal:
    """Generate a fix proposal based on the diagnosis category.

    Routes to category-specific fix strategies:
    - selector_drift → re-harvest selectors
    - code_bug → feed into codegen feedback loop
    - config_update / data_schema_change → modify Config.xlsx
    """
    strategy = _FIX_STRATEGIES.get(diagnosis.category, _propose_escalation)
    return await strategy(diagnosis, project_dir, ir)


async def apply_fix(
    fix_proposal: FixProposal,
    project_dir: str,
) -> None:
    """Apply a fix proposal's changes to the project directory."""
    project_path = Path(project_dir)

    for change in fix_proposal.changes:
        file_path = project_path / change.file_path

        if change.change_type == "add":
            file_path.parent.mkdir(parents=True, exist_ok=True)
            file_path.write_text(change.after or "", encoding="utf-8")
            logger.info("Added file: %s", change.file_path)

        elif change.change_type == "modify" and change.before and change.after:
            if file_path.exists():
                content = file_path.read_text(encoding="utf-8")
                content = content.replace(change.before, change.after)
                file_path.write_text(content, encoding="utf-8")
                logger.info("Modified file: %s", change.file_path)

        elif change.change_type == "delete":
            if file_path.exists():
                file_path.unlink()
                logger.info("Deleted file: %s", change.file_path)

        elif change.change_type == "config_update":
            await _apply_config_change(file_path, change)


# ---------------------------------------------------------------------------
# Category-specific fix strategies
# ---------------------------------------------------------------------------


async def _propose_selector_fix(
    diagnosis: DiagnosisResult,
    project_dir: str,
    ir: dict[str, Any],
) -> FixProposal:
    """Re-harvest selectors for drifted UI elements."""
    changes = []

    # Identify affected selector files in .objects/
    objects_dir = Path(project_dir) / ".objects"
    if objects_dir.is_dir():
        for json_file in objects_dir.rglob("*.json"):
            if json_file.name != "descriptor.json":
                changes.append(
                    ProposedChange(
                        file_path=str(json_file.relative_to(project_dir)),
                        change_type="modify",
                        description=f"Re-harvest selectors in {json_file.name}",
                    )
                )

    return FixProposal(
        diagnosis_ref=diagnosis.category,
        description="Re-harvest UI selectors to match current application state",
        changes=changes,
        risk_level="medium",
        requires_redeployment=True,
        test_plan=["Verify selectors match current UI", "Run smoke test against target system"],
    )


async def _propose_code_fix(
    diagnosis: DiagnosisResult,
    project_dir: str,
    ir: dict[str, Any],
) -> FixProposal:
    """Feed errors into the existing codegen feedback loop for code fixes."""
    changes = [
        ProposedChange(
            file_path=f,
            change_type="modify",
            description=f"Fix code bug: {diagnosis.root_cause}",
        )
        for f in diagnosis.affected_files
    ]

    return FixProposal(
        diagnosis_ref=diagnosis.category,
        description=f"Code fix: {diagnosis.root_cause}",
        changes=changes,
        risk_level="medium",
        requires_redeployment=True,
        test_plan=[
            "Compile with Roslyn validator",
            "Run XAML lint checks",
            "Run UiPath test cases",
        ],
    )


async def _propose_config_fix(
    diagnosis: DiagnosisResult,
    project_dir: str,
    ir: dict[str, Any],
) -> FixProposal:
    """Propose Config.xlsx or Orchestrator asset changes."""
    config_path = Path(project_dir) / "Data" / "Config.xlsx"
    changes = []

    if config_path.exists():
        changes.append(
            ProposedChange(
                file_path="Data/Config.xlsx",
                change_type="config_update",
                description=f"Update configuration: {diagnosis.root_cause}",
            )
        )

    return FixProposal(
        diagnosis_ref=diagnosis.category,
        description=f"Configuration update: {diagnosis.root_cause}",
        changes=changes,
        risk_level="low",
        requires_redeployment=True,
        test_plan=["Verify Config.xlsx values", "Run validation"],
    )


async def _propose_escalation(
    diagnosis: DiagnosisResult,
    project_dir: str,
    ir: dict[str, Any],
) -> FixProposal:
    """Escalate to human — no automated fix available."""
    return FixProposal(
        diagnosis_ref=diagnosis.category,
        description=f"Escalation required: {diagnosis.root_cause}",
        changes=[],
        risk_level="high",
        requires_redeployment=False,
        test_plan=["Manual investigation required"],
    )


_FIX_STRATEGIES = {
    "selector_drift": _propose_selector_fix,
    "code_bug": _propose_code_fix,
    "data_schema_change": _propose_config_fix,
    "system_timeout": _propose_escalation,
    "credential_expiry": _propose_escalation,
    "business_rule_violation": _propose_config_fix,
    "infrastructure": _propose_escalation,
    "unknown": _propose_escalation,
}


async def _apply_config_change(file_path: Path, change: ProposedChange) -> None:
    """Apply a configuration change to Config.xlsx."""
    if not file_path.exists():
        logger.warning("Config file not found: %s", file_path)
        return

    try:
        from rpa_architect.assembler.config_xlsx_gen import update_config_setting

        await update_config_setting(file_path, change.description)
        logger.info("Config updated: %s", change.description)
    except ImportError:
        logger.warning("Config updater not available for %s", file_path)
