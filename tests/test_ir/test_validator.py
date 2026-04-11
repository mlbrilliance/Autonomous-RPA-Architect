"""Tests for IR validation logic."""

from __future__ import annotations

import pytest

from rpa_architect.ir.schema import (
    BusinessRule,
    ProcessIR,
    Step,
    SystemInfo,
    Transaction,
    UIAction,
)
from rpa_architect.ir.validator import ValidationIssue, validate_process_ir


class TestValidIR:
    """Test that valid IRs pass validation."""

    def test_valid_ir_passes(self, sample_ir: ProcessIR) -> None:
        issues = validate_process_ir(sample_ir)
        errors = [i for i in issues if i.severity == "error"]
        assert len(errors) == 0, f"Unexpected errors: {[e.message for e in errors]}"


class TestEmptyTransactions:
    """Test that IR with no transactions produces an error."""

    def test_empty_transactions_fails(self) -> None:
        ir = ProcessIR(
            process_name="EmptyProcess",
            description="A process with no transactions.",
        )
        issues = validate_process_ir(ir)
        errors = [i for i in issues if i.severity == "error"]
        assert any("at least one transaction" in e.message for e in errors)


class TestDuplicateStepIds:
    """Test that duplicate step IDs are detected."""

    def test_duplicate_step_ids(self) -> None:
        ir = ProcessIR(
            process_name="DuplicateSteps",
            description="Test duplicate step IDs.",
            systems=[SystemInfo(name="WebApp", type="web")],
            transactions=[
                Transaction(
                    name="Txn1",
                    steps=[
                        Step(id="S001", type="ui_flow", system_ref="WebApp"),
                        Step(id="S001", type="data_operation"),  # duplicate
                    ],
                ),
            ],
        )
        issues = validate_process_ir(ir)
        errors = [i for i in issues if i.severity == "error"]
        assert any("Duplicate step ID" in e.message and "S001" in e.message for e in errors)


class TestInvalidSystemReference:
    """Test that referencing a non-existent system is flagged."""

    def test_invalid_system_reference(self) -> None:
        ir = ProcessIR(
            process_name="BadSystemRef",
            description="Step references unknown system.",
            systems=[SystemInfo(name="WebApp", type="web")],
            transactions=[
                Transaction(
                    name="Txn1",
                    steps=[
                        Step(id="S001", type="ui_flow", system_ref="NonExistentSystem"),
                    ],
                ),
            ],
        )
        issues = validate_process_ir(ir)
        errors = [i for i in issues if i.severity == "error"]
        assert any(
            "unknown system" in e.message.lower() and "NonExistentSystem" in e.message
            for e in errors
        )


class TestEmptySteps:
    """Test that a transaction with no steps produces an error."""

    def test_empty_steps_fails(self) -> None:
        ir = ProcessIR(
            process_name="NoStepsProcess",
            description="Transaction with no steps.",
            transactions=[
                Transaction(name="EmptyTxn", steps=[]),
            ],
        )
        issues = validate_process_ir(ir)
        errors = [i for i in issues if i.severity == "error"]
        assert any("no steps" in e.message.lower() for e in errors)


class TestValidationIssueSeverity:
    """Check error vs warning classification."""

    def test_validation_issue_severity(self) -> None:
        """Info-level issues should be reported for steps with uncertainty."""
        ir = ProcessIR(
            process_name="UncertainProcess",
            description="Process with uncertain steps.",
            systems=[SystemInfo(name="App", type="web")],
            transactions=[
                Transaction(
                    name="Txn1",
                    steps=[
                        Step(
                            id="S001",
                            type="ui_flow",
                            system_ref="App",
                            uncertainty="PDD does not specify which button to click.",
                        ),
                    ],
                ),
            ],
        )
        issues = validate_process_ir(ir)
        info_issues = [i for i in issues if i.severity == "info"]
        assert any("uncertainty" in i.message.lower() for i in info_issues)

    def test_warning_for_missing_credentials(self) -> None:
        """Systems requiring login but no credentials should produce a warning."""
        ir = ProcessIR(
            process_name="NoCredentials",
            description="Systems need login but no creds defined.",
            systems=[
                SystemInfo(name="SAP", type="sap", login_required=True),
            ],
            credentials=[],
            transactions=[
                Transaction(
                    name="Txn1",
                    steps=[
                        Step(id="S001", type="login_sequence", system_ref="SAP"),
                    ],
                ),
            ],
        )
        issues = validate_process_ir(ir)
        warnings = [i for i in issues if i.severity == "warning"]
        assert any("login" in w.message.lower() or "credentials" in w.message.lower() for w in warnings)

    def test_validation_issue_model(self) -> None:
        """ValidationIssue model fields are correct."""
        issue = ValidationIssue(
            severity="error",
            path="transactions[0].steps[1]",
            message="Something went wrong.",
        )
        assert issue.severity == "error"
        assert issue.path == "transactions[0].steps[1]"
        assert issue.message == "Something went wrong."
