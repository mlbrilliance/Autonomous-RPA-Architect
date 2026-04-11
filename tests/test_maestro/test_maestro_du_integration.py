"""Tests for Maestro planner + BPMN integration with Document Understanding."""

from __future__ import annotations

import xml.etree.ElementTree as ET

from rpa_architect.ir.schema import (
    DocumentUnderstandingSpec,
    ProcessIR,
    Step,
    SystemInfo,
    Transaction,
)
from rpa_architect.maestro.bpmn_generator import generate_bpmn
from rpa_architect.maestro.maestro_planner import plan_maestro


def _make_du_ir() -> ProcessIR:
    return ProcessIR(
        process_name="OdooInvoiceProcessing",
        process_type="transactional",
        systems=[SystemInfo(name="Odoo", type="web")],
        transactions=[
            Transaction(
                name="ProcessInvoice",
                steps=[
                    Step(
                        id="S001",
                        type="ui_flow",
                        description="Create vendor bill",
                    )
                ],
                business_rules=[],
            )
        ],
        document_understanding=DocumentUnderstandingSpec(
            document_type="Invoice",
            confidence_threshold=0.8,
        ),
    )


def _make_no_du_ir() -> ProcessIR:
    return ProcessIR(
        process_name="NoDU",
        process_type="transactional",
        systems=[SystemInfo(name="Web", type="web")],
        transactions=[
            Transaction(
                name="T1",
                steps=[Step(id="S1", type="ui_flow", description="Click")],
                business_rules=[],
            )
        ],
    )


def test_plan_includes_document_understanding_service_task_when_du_present() -> None:
    ir = _make_du_ir()
    plan = plan_maestro(ir)
    task_names = [t.name for t in plan.bpmn_tasks]
    assert any("Document" in n for n in task_names), f"got: {task_names}"


def test_plan_includes_validation_user_task_when_du_present() -> None:
    ir = _make_du_ir()
    plan = plan_maestro(ir)
    user_task_names = [t.name for t in plan.user_tasks]
    assert any("Valid" in n or "Validation" in n for n in user_task_names), (
        f"got: {user_task_names}"
    )


def test_plan_omits_du_tasks_when_no_du_spec() -> None:
    ir = _make_no_du_ir()
    plan = plan_maestro(ir)
    task_names = [t.name for t in plan.bpmn_tasks]
    user_task_names = [t.name for t in plan.user_tasks]
    assert not any("Document Understanding" in n for n in task_names)
    assert not any("Document Validation" in n for n in user_task_names)


def test_bpmn_xml_contains_document_understanding_when_du_present() -> None:
    ir = _make_du_ir()
    bpmn_xml = generate_bpmn(ir, [])
    assert "Document" in bpmn_xml


def test_bpmn_xml_contains_user_task_for_validation_when_du_present() -> None:
    ir = _make_du_ir()
    bpmn_xml = generate_bpmn(ir, [])
    root = ET.fromstring(bpmn_xml)
    assert root is not None
    assert "userTask" in bpmn_xml


def test_bpmn_xml_well_formed_when_du_present() -> None:
    ir = _make_du_ir()
    bpmn_xml = generate_bpmn(ir, [])
    root = ET.fromstring(bpmn_xml)
    assert root.tag.endswith("definitions")
