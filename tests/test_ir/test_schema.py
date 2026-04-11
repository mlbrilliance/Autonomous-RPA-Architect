"""Tests for IR schema Pydantic models."""

from __future__ import annotations

import json

import pytest

from rpa_architect.ir.schema import (
    BusinessRule,
    CredentialInfo,
    DataContract,
    DataField,
    ExceptionCategory,
    ProcessIR,
    Step,
    SystemInfo,
    Transaction,
    UIAction,
)


class TestProcessIRCreation:
    """Test creating ProcessIR with all required fields."""

    def test_process_ir_creation(self, sample_ir: ProcessIR) -> None:
        assert sample_ir.process_name == "InvoiceProcessing"
        assert sample_ir.process_type == "transactional"
        assert sample_ir.description is not None
        assert len(sample_ir.systems) == 2
        assert len(sample_ir.credentials) == 1
        assert len(sample_ir.transactions) == 1
        assert len(sample_ir.config) >= 1
        assert len(sample_ir.exception_categories) == 1
        assert sample_ir.metadata["author"] == "Test Suite"

    def test_process_ir_minimal(self) -> None:
        """ProcessIR with only the required field (process_name)."""
        ir = ProcessIR(process_name="MinimalProcess")
        assert ir.process_name == "MinimalProcess"
        assert ir.process_type == "transactional"
        assert ir.systems == []
        assert ir.transactions == []
        assert ir.config == {}
        assert ir.metadata == {}


class TestProcessIRSerialization:
    """Test JSON round-trip serialization."""

    def test_process_ir_serialization(self, sample_ir: ProcessIR) -> None:
        json_str = sample_ir.model_dump_json()
        restored = ProcessIR.model_validate_json(json_str)

        assert restored.process_name == sample_ir.process_name
        assert restored.process_type == sample_ir.process_type
        assert len(restored.transactions) == len(sample_ir.transactions)
        assert len(restored.systems) == len(sample_ir.systems)
        assert restored.config == sample_ir.config

    def test_round_trip_preserves_nested(self, sample_ir: ProcessIR) -> None:
        json_str = sample_ir.model_dump_json()
        restored = ProcessIR.model_validate_json(json_str)

        orig_txn = sample_ir.transactions[0]
        rest_txn = restored.transactions[0]

        assert rest_txn.name == orig_txn.name
        assert len(rest_txn.steps) == len(orig_txn.steps)
        assert rest_txn.steps[0].id == orig_txn.steps[0].id
        assert len(rest_txn.business_rules) == len(orig_txn.business_rules)

    def test_from_json_file(self) -> None:
        """Load from the sample fixture JSON file."""
        fixture_path = (
            Path(__file__).parent.parent / "fixtures" / "sample_irs" / "simple_queue_performer.json"
        )
        with open(fixture_path) as f:
            data = json.load(f)
        ir = ProcessIR.model_validate(data)
        assert ir.process_name == "InvoiceProcessing"
        assert len(ir.transactions) == 1
        assert len(ir.transactions[0].steps) == 4


from pathlib import Path


class TestStepTypes:
    """Verify all step type literals work."""

    @pytest.mark.parametrize(
        "step_type",
        [
            "open_application",
            "login_sequence",
            "ui_flow",
            "data_operation",
            "api_call",
            "decision",
            "loop",
            "close_application",
            "wait",
            "navigate",
            "extract_data",
            "transform_data",
        ],
    )
    def test_step_types(self, step_type: str) -> None:
        step = Step(id="S001", type=step_type)
        assert step.type == step_type

    def test_invalid_step_type(self) -> None:
        with pytest.raises(Exception):
            Step(id="S001", type="invalid_type")


class TestUIActionTypes:
    """Verify all action type literals work."""

    @pytest.mark.parametrize(
        "action_type",
        [
            "click",
            "type_into",
            "get_text",
            "select_item",
            "check",
            "uncheck",
            "hover",
            "extract_data",
            "wait_element",
            "keyboard_shortcut",
            "scroll",
            "drag_drop",
        ],
    )
    def test_ui_action_types(self, action_type: str) -> None:
        action = UIAction(action=action_type, target="Test Target")
        assert action.action == action_type

    def test_invalid_action_type(self) -> None:
        with pytest.raises(Exception):
            UIAction(action="invalid_action", target="Test")


class TestBusinessRuleOutcomes:
    """Verify all outcome literals."""

    @pytest.mark.parametrize(
        "outcome",
        ["business_exception", "system_exception", "skip", "retry", "route", "escalate"],
    )
    def test_business_rule_outcomes(self, outcome: str) -> None:
        rule = BusinessRule(id="BR001", condition="test condition", outcome=outcome)
        assert rule.outcome == outcome

    def test_invalid_outcome(self) -> None:
        with pytest.raises(Exception):
            BusinessRule(id="BR001", condition="test", outcome="invalid")


class TestDataContract:
    """Test DataContract and DataField creation."""

    def test_data_contract_fields(self) -> None:
        contract = DataContract(
            fields=[
                DataField(name="InvoiceNumber", type="String", required=True, description="The invoice ID."),
                DataField(name="Amount", type="Decimal", required=True),
                DataField(name="Notes", type="String", required=False, validation_rules=["max_length:500"]),
            ]
        )
        assert len(contract.fields) == 3
        assert contract.fields[0].name == "InvoiceNumber"
        assert contract.fields[0].type == "String"
        assert contract.fields[0].required is True
        assert contract.fields[0].description == "The invoice ID."
        assert contract.fields[2].validation_rules == ["max_length:500"]

    def test_empty_data_contract(self) -> None:
        contract = DataContract()
        assert contract.fields == []


class TestOptionalFields:
    """Verify optional fields default to None."""

    def test_optional_fields(self) -> None:
        step = Step(id="S001", type="ui_flow")
        assert step.system_ref is None
        assert step.uncertainty is None
        assert step.description is None
        assert step.actions == []
        assert step.substeps == []
        assert step.parameters == {}

    def test_ui_action_optional_fields(self) -> None:
        action = UIAction(action="click", target="Button")
        assert action.value is None
        assert action.selector_hint is None
        assert action.confidence == 0.5

    def test_process_ir_optional_fields(self) -> None:
        ir = ProcessIR(process_name="Test")
        assert ir.description is None
        assert ir.systems == []
        assert ir.credentials == []
        assert ir.transactions == []

    def test_credential_optional_fields(self) -> None:
        cred = CredentialInfo(name="TestCred", type="credential")
        assert cred.orchestrator_path is None
        assert cred.description is None

    def test_exception_category_optional(self) -> None:
        exc = ExceptionCategory(name="TestExc", type="business")
        assert exc.retry_count == 0
        assert exc.description is None


class TestProcessTypeEnum:
    """Verify all process_type literals."""

    @pytest.mark.parametrize(
        "process_type",
        ["transactional", "linear", "event_driven"],
    )
    def test_process_type_enum(self, process_type: str) -> None:
        ir = ProcessIR(process_name="Test", process_type=process_type)
        assert ir.process_type == process_type

    def test_default_process_type(self) -> None:
        ir = ProcessIR(process_name="Test")
        assert ir.process_type == "transactional"

    def test_invalid_process_type(self) -> None:
        with pytest.raises(Exception):
            ProcessIR(process_name="Test", process_type="batch")
