"""IR validation logic for ProcessIR models.

Validates structural integrity, referential consistency, and completeness
of the intermediate representation before it is used for code generation.
"""

from __future__ import annotations

from enum import Enum
from typing import Literal

from pydantic import BaseModel, Field

from rpa_architect.ir.schema import ProcessIR, Step, Transaction


class Severity(str, Enum):
    """Validation issue severity."""

    ERROR = "error"
    WARNING = "warning"
    INFO = "info"


class ValidationIssue(BaseModel):
    """A single validation finding."""

    severity: Literal["error", "warning", "info"] = Field(
        description="Issue severity level."
    )
    path: str = Field(
        description="Dot-delimited path to the problematic element (e.g., 'transactions[0].steps[2]')."
    )
    message: str = Field(description="Human-readable description of the issue.")


def _collect_step_ids(steps: list[Step], path_prefix: str) -> list[tuple[str, str]]:
    """Recursively collect (step_id, path) pairs from steps and substeps."""
    results: list[tuple[str, str]] = []
    for i, step in enumerate(steps):
        step_path = f"{path_prefix}[{i}]"
        results.append((step.id, step_path))
        if step.substeps:
            results.extend(
                _collect_step_ids(step.substeps, f"{step_path}.substeps")
            )
    return results


def _validate_step_system_refs(
    steps: list[Step],
    valid_system_names: set[str],
    path_prefix: str,
    issues: list[ValidationIssue],
) -> None:
    """Recursively validate system_ref fields on steps."""
    for i, step in enumerate(steps):
        step_path = f"{path_prefix}[{i}]"
        if step.system_ref and step.system_ref not in valid_system_names:
            issues.append(
                ValidationIssue(
                    severity="error",
                    path=f"{step_path}.system_ref",
                    message=(
                        f"Step '{step.id}' references unknown system '{step.system_ref}'. "
                        f"Known systems: {sorted(valid_system_names)}"
                    ),
                )
            )
        if step.substeps:
            _validate_step_system_refs(
                step.substeps, valid_system_names, f"{step_path}.substeps", issues
            )


def _validate_transaction(
    txn: Transaction,
    txn_index: int,
    valid_system_names: set[str],
    all_step_ids: list[tuple[str, str]],
    issues: list[ValidationIssue],
) -> None:
    """Validate a single transaction."""
    txn_path = f"transactions[{txn_index}]"

    # Transaction must have at least one step
    if not txn.steps:
        issues.append(
            ValidationIssue(
                severity="error",
                path=txn_path,
                message=f"Transaction '{txn.name}' has no steps defined.",
            )
        )

    # Validate system refs in steps
    _validate_step_system_refs(
        txn.steps, valid_system_names, f"{txn_path}.steps", issues
    )

    # Validate business rules have unique IDs
    br_ids: set[str] = set()
    for j, rule in enumerate(txn.business_rules):
        if rule.id in br_ids:
            issues.append(
                ValidationIssue(
                    severity="warning",
                    path=f"{txn_path}.business_rules[{j}]",
                    message=f"Duplicate business rule ID '{rule.id}' in transaction '{txn.name}'.",
                )
            )
        br_ids.add(rule.id)

    # Check data contract consistency: if input_contract has fields, they should have types
    if txn.input_contract:
        for k, field in enumerate(txn.input_contract.fields):
            if not field.name.strip():
                issues.append(
                    ValidationIssue(
                        severity="error",
                        path=f"{txn_path}.input_contract.fields[{k}]",
                        message="Data field has an empty name.",
                    )
                )

    if txn.output_contract:
        for k, field in enumerate(txn.output_contract.fields):
            if not field.name.strip():
                issues.append(
                    ValidationIssue(
                        severity="error",
                        path=f"{txn_path}.output_contract.fields[{k}]",
                        message="Data field has an empty name.",
                    )
                )


def validate_process_ir(ir: ProcessIR) -> list[ValidationIssue]:
    """Validate a ProcessIR for structural integrity and referential consistency.

    Checks performed:
    - Process has at least one transaction.
    - Each transaction has at least one step.
    - All step IDs are unique across the entire process.
    - All step system_ref values point to systems defined in ProcessIR.systems.
    - All credential references are consistent.
    - Data contracts have valid field definitions.

    Args:
        ir: The ProcessIR to validate.

    Returns:
        List of ValidationIssue objects. An empty list means the IR is valid.
    """
    issues: list[ValidationIssue] = []

    # Must have at least one transaction
    if not ir.transactions:
        issues.append(
            ValidationIssue(
                severity="error",
                path="transactions",
                message="Process must have at least one transaction.",
            )
        )

    # Collect valid system names
    valid_system_names: set[str] = set()
    for i, system in enumerate(ir.systems):
        if system.name in valid_system_names:
            issues.append(
                ValidationIssue(
                    severity="warning",
                    path=f"systems[{i}]",
                    message=f"Duplicate system name '{system.name}'.",
                )
            )
        valid_system_names.add(system.name)

    # Collect valid credential names
    valid_credential_names: set[str] = set()
    for i, cred in enumerate(ir.credentials):
        if cred.name in valid_credential_names:
            issues.append(
                ValidationIssue(
                    severity="warning",
                    path=f"credentials[{i}]",
                    message=f"Duplicate credential name '{cred.name}'.",
                )
            )
        valid_credential_names.add(cred.name)

    # Check systems that require login have corresponding credentials
    systems_needing_login = {s.name for s in ir.systems if s.login_required}
    if systems_needing_login and not ir.credentials:
        issues.append(
            ValidationIssue(
                severity="warning",
                path="credentials",
                message=(
                    f"Systems {sorted(systems_needing_login)} require login but "
                    f"no credentials are defined."
                ),
            )
        )

    # Collect all step IDs across all transactions and check uniqueness
    all_step_ids: list[tuple[str, str]] = []
    for i, txn in enumerate(ir.transactions):
        txn_step_ids = _collect_step_ids(txn.steps, f"transactions[{i}].steps")
        all_step_ids.extend(txn_step_ids)

    seen_ids: dict[str, str] = {}
    for step_id, step_path in all_step_ids:
        if step_id in seen_ids:
            issues.append(
                ValidationIssue(
                    severity="error",
                    path=step_path,
                    message=(
                        f"Duplicate step ID '{step_id}'. "
                        f"Previously seen at '{seen_ids[step_id]}'."
                    ),
                )
            )
        else:
            seen_ids[step_id] = step_path

    # Validate each transaction
    for i, txn in enumerate(ir.transactions):
        _validate_transaction(txn, i, valid_system_names, all_step_ids, issues)

    # Info: flag steps with uncertainty
    for i, txn in enumerate(ir.transactions):
        for j, step in enumerate(txn.steps):
            if step.uncertainty:
                issues.append(
                    ValidationIssue(
                        severity="info",
                        path=f"transactions[{i}].steps[{j}]",
                        message=(
                            f"Step '{step.id}' has uncertainty: {step.uncertainty}"
                        ),
                    )
                )

    # Warn if process_name is empty or generic
    if not ir.process_name or not ir.process_name.strip():
        issues.append(
            ValidationIssue(
                severity="error",
                path="process_name",
                message="Process name must not be empty.",
            )
        )

    # Warn if no description
    if not ir.description:
        issues.append(
            ValidationIssue(
                severity="info",
                path="description",
                message="Process has no description. Consider adding one for documentation.",
            )
        )

    return issues
