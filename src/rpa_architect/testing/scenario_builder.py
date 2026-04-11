"""Test scenario builder for RPA processes.

Analyzes the ProcessIR to generate structured test scenarios covering
happy paths, business exception paths, system exception paths, and
edge cases.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from rpa_architect.ir.schema import ProcessIR, Transaction


class TestScenario(BaseModel):
    """A test scenario describing a specific execution path through the process."""

    name: str = Field(description="Short scenario identifier.")
    description: str = Field(description="Human-readable scenario description.")
    path_type: Literal["happy", "business_exception", "system_exception", "edge_case"] = Field(
        description="Category of execution path this scenario exercises.",
    )
    steps: list[str] = Field(
        default_factory=list,
        description="Ordered list of step descriptions to execute.",
    )
    expected_outcome: str = Field(
        default="",
        description="Expected result when this scenario completes.",
    )


def _build_happy_path(transaction: Transaction) -> TestScenario:
    """Build a happy-path scenario from a transaction's steps."""
    step_descriptions: list[str] = []
    for step in transaction.steps:
        desc = step.description or f"Execute step {step.id} ({step.type})"
        step_descriptions.append(desc)

    return TestScenario(
        name=f"HappyPath_{transaction.name}",
        description=(
            f"Verify successful end-to-end processing of '{transaction.name}' "
            f"with valid input data and all systems available."
        ),
        path_type="happy",
        steps=step_descriptions,
        expected_outcome=(
            f"Transaction '{transaction.name}' completes successfully. "
            f"Output data matches expected contract."
        ),
    )


def _build_business_exception_scenarios(
    transaction: Transaction,
) -> list[TestScenario]:
    """Build one scenario per business rule that can raise a business exception."""
    scenarios: list[TestScenario] = []

    for rule in transaction.business_rules:
        if rule.outcome not in ("business_exception", "skip", "route", "escalate"):
            continue

        steps = [
            f"Set up data so that condition is met: {rule.condition}",
            f"Execute transaction '{transaction.name}' with triggering data",
            f"Verify {rule.outcome} is raised/handled",
        ]

        reason_text = f" Reason: {rule.reason}" if rule.reason else ""

        scenarios.append(
            TestScenario(
                name=f"BusinessException_{transaction.name}_{rule.id}",
                description=(
                    f"Verify business rule {rule.id} triggers {rule.outcome} "
                    f"when: {rule.condition}.{reason_text}"
                ),
                path_type="business_exception",
                steps=steps,
                expected_outcome=(
                    f"Business rule {rule.id} fires. "
                    f"Outcome: {rule.outcome}. "
                    f"Transaction item is marked accordingly in Orchestrator."
                ),
            )
        )

    return scenarios


def _build_system_exception_scenarios(
    transaction: Transaction,
    ir: ProcessIR,
) -> list[TestScenario]:
    """Build system exception scenarios for each system the transaction touches."""
    # Collect unique systems referenced by steps
    system_refs: set[str] = set()
    for step in transaction.steps:
        if step.system_ref:
            system_refs.add(step.system_ref)

    scenarios: list[TestScenario] = []

    for sys_ref in sorted(system_refs):
        # Find retry config from exception categories
        retry_count = 0
        for exc_cat in ir.exception_categories:
            if exc_cat.type == "system":
                retry_count = max(retry_count, exc_cat.retry_count)

        max_retry = ir.config.get("MaxRetryNumber", str(retry_count))

        scenarios.append(
            TestScenario(
                name=f"SystemException_{transaction.name}_{sys_ref}",
                description=(
                    f"Verify system exception handling when '{sys_ref}' is "
                    f"unavailable or returns an error during '{transaction.name}'."
                ),
                path_type="system_exception",
                steps=[
                    f"Simulate '{sys_ref}' being unavailable or timing out",
                    f"Execute transaction '{transaction.name}'",
                    "Verify system exception is caught and retry logic activates",
                    f"After {max_retry} retries, verify transaction is marked as failed",
                ],
                expected_outcome=(
                    f"System exception is raised. "
                    f"Transaction is retried up to {max_retry} times. "
                    f"After exhausting retries, status is set to Failed."
                ),
            )
        )

    return scenarios


def _build_edge_case_scenarios(transaction: Transaction) -> list[TestScenario]:
    """Build edge-case scenarios based on data contracts."""
    scenarios: list[TestScenario] = []

    # Empty input scenario
    if transaction.input_contract and transaction.input_contract.fields:
        required_fields = [
            f for f in transaction.input_contract.fields if f.required
        ]

        if required_fields:
            field_names = ", ".join(f.name for f in required_fields)
            scenarios.append(
                TestScenario(
                    name=f"EdgeCase_{transaction.name}_MissingRequiredFields",
                    description=(
                        f"Verify handling when required fields are missing: "
                        f"{field_names}."
                    ),
                    path_type="edge_case",
                    steps=[
                        "Provide transaction item with missing required fields",
                        f"Execute transaction '{transaction.name}'",
                        "Verify appropriate validation error or business exception",
                    ],
                    expected_outcome=(
                        "Business exception is raised due to missing required "
                        "input data. Transaction is not processed."
                    ),
                )
            )

        # Empty string / null values
        scenarios.append(
            TestScenario(
                name=f"EdgeCase_{transaction.name}_EmptyValues",
                description=(
                    f"Verify handling of empty/null values in transaction "
                    f"'{transaction.name}' input data."
                ),
                path_type="edge_case",
                steps=[
                    "Provide transaction item with empty string values for all fields",
                    f"Execute transaction '{transaction.name}'",
                    "Verify graceful handling of empty values",
                ],
                expected_outcome=(
                    "Process handles empty values gracefully, either by "
                    "raising a business exception or applying default values."
                ),
            )
        )

    return scenarios


def build_scenarios(ir: ProcessIR) -> list[TestScenario]:
    """Build comprehensive test scenarios from the ProcessIR.

    Generates scenarios covering:
    - Happy path: one per transaction
    - Business exception: one per business rule with exception/skip/route/escalate outcome
    - System exception: one per system referenced in each transaction
    - Edge case: missing required fields, empty values

    Args:
        ir: The ProcessIR describing the RPA process.

    Returns:
        List of TestScenario objects covering all identified test paths.
    """
    scenarios: list[TestScenario] = []

    for transaction in ir.transactions:
        # Happy path
        scenarios.append(_build_happy_path(transaction))

        # Business exception scenarios
        scenarios.extend(_build_business_exception_scenarios(transaction))

        # System exception scenarios
        scenarios.extend(_build_system_exception_scenarios(transaction, ir))

        # Edge case scenarios
        scenarios.extend(_build_edge_case_scenarios(transaction))

    return scenarios
