"""Tests for parsing the Odoo invoice processing PDD."""

from __future__ import annotations

from pathlib import Path

import pytest

from rpa_architect.ir.schema import DocumentUnderstandingSpec, ProcessIR
from rpa_architect.maestro.maestro_planner import _step_is_agent_candidate
from rpa_architect.parser.pdd_parser import parse_pdd

PDD_PATH = (
    Path(__file__).parent.parent / "fixtures" / "pdds" / "odoo_invoice_processing.md"
)


@pytest.fixture(scope="module")
def odoo_ir() -> ProcessIR:
    return parse_pdd(PDD_PATH)


def test_pdd_file_exists() -> None:
    assert PDD_PATH.exists()


def test_parse_extracts_process_name(odoo_ir: ProcessIR) -> None:
    assert odoo_ir.process_name == "OdooInvoiceProcessing"


def test_parse_extracts_transactional_type(odoo_ir: ProcessIR) -> None:
    assert odoo_ir.process_type == "transactional"


def test_parse_extracts_odoo_system(odoo_ir: ProcessIR) -> None:
    odoo = next((s for s in odoo_ir.systems if s.name == "Odoo"), None)
    assert odoo is not None
    assert odoo.type == "web"
    assert odoo.login_required is True


def test_parse_extracts_credentials(odoo_ir: ProcessIR) -> None:
    cred_names = {c.name for c in odoo_ir.credentials}
    assert "OdooCredential" in cred_names
    assert "DUApiKey" in cred_names
    assert "OdooInvoices" in cred_names


def test_parse_extracts_du_spec_present(odoo_ir: ProcessIR) -> None:
    assert odoo_ir.document_understanding is not None
    assert isinstance(odoo_ir.document_understanding, DocumentUnderstandingSpec)


def test_parse_extracts_du_invoice_document_type(odoo_ir: ProcessIR) -> None:
    spec = odoo_ir.document_understanding
    assert spec is not None
    assert spec.document_type == "Invoice"


def test_parse_extracts_du_endpoint(odoo_ir: ProcessIR) -> None:
    spec = odoo_ir.document_understanding
    assert spec is not None
    assert "du.uipath.com" in spec.extraction_endpoint


def test_parse_extracts_du_confidence_threshold(odoo_ir: ProcessIR) -> None:
    spec = odoo_ir.document_understanding
    assert spec is not None
    assert spec.confidence_threshold == 0.8


def test_parse_extracts_du_field_list(odoo_ir: ProcessIR) -> None:
    spec = odoo_ir.document_understanding
    assert spec is not None
    assert "VendorName" in spec.fields
    assert "TotalAmount" in spec.fields
    assert "LineItems" in spec.fields


def test_parse_extracts_du_api_key_asset(odoo_ir: ProcessIR) -> None:
    spec = odoo_ir.document_understanding
    assert spec is not None
    assert spec.api_key_asset == "DUApiKey"


def test_parse_extracts_steps(odoo_ir: ProcessIR) -> None:
    txn_steps = odoo_ir.transactions[0].steps
    step_ids = {s.id for s in txn_steps}
    assert {"S001", "S002", "S003", "S004", "S005", "S006", "S007"}.issubset(step_ids)


def test_step_s004_is_classified_as_agent_candidate(odoo_ir: ProcessIR) -> None:
    """S004 mentions 'classify ... LLM agent', so the maestro planner
    should detect it as an agent task candidate."""
    s004 = next(s for s in odoo_ir.transactions[0].steps if s.id == "S004")
    agent_type = _step_is_agent_candidate(s004)
    assert agent_type is not None


def test_parse_extracts_business_rules(odoo_ir: ProcessIR) -> None:
    rules = odoo_ir.transactions[0].business_rules
    rule_ids = {r.id for r in rules}
    assert {"BR001", "BR002", "BR003"}.issubset(rule_ids)


def test_parse_business_rule_has_outcome(odoo_ir: ProcessIR) -> None:
    rules = odoo_ir.transactions[0].business_rules
    br001 = next(r for r in rules if r.id == "BR001")
    assert br001.outcome == "business_exception"
    br002 = next(r for r in rules if r.id == "BR002")
    assert br002.outcome == "route"
    br003 = next(r for r in rules if r.id == "BR003")
    assert br003.outcome == "escalate"


def test_parse_extracts_config(odoo_ir: ProcessIR) -> None:
    assert odoo_ir.config.get("MaxRetryNumber") == "3"
    assert odoo_ir.config.get("ConfidenceThreshold") == "0.8"
    assert odoo_ir.config.get("OrchestratorQueueName") == "OdooInvoices"


def test_parse_step_actions_for_login(odoo_ir: ProcessIR) -> None:
    s001 = next(s for s in odoo_ir.transactions[0].steps if s.id == "S001")
    actions = s001.actions
    assert len(actions) >= 3
    action_types = [a.action for a in actions]
    assert "type_into" in action_types
    assert "click" in action_types
