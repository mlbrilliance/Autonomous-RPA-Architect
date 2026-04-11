"""Tests for the enterprise BPMN + DMN generator."""

from __future__ import annotations

import xml.etree.ElementTree as ET

from rpa_architect.codegen.enterprise_bpmn_gen import (
    generate_invoice_processing_bpmn,
    generate_invoice_rules_dmn,
)


def test_bpmn_is_valid_xml() -> None:
    xml = generate_invoice_processing_bpmn()
    root = ET.fromstring(xml)
    assert root.tag.endswith("definitions")


def test_bpmn_has_all_expected_tasks() -> None:
    xml = generate_invoice_processing_bpmn()
    root = ET.fromstring(xml)
    task_ids = [
        el.get("id")
        for el in root.iter()
        if el.tag.endswith("}serviceTask")
        or el.tag.endswith("}userTask")
        or el.tag.endswith("}businessRuleTask")
    ]
    for expected in (
        "Task_ReceiveBatch",
        "Task_DU",
        "Task_Rules",
        "Task_CreateBill",
        "Task_Notify",
        "Task_LogRejection",
        "Task_HumanValidation",
        "Task_ManagerApproval",
    ):
        assert expected in task_ids, f"missing {expected}: {task_ids}"


def test_bpmn_du_task_has_agent_extension() -> None:
    xml = generate_invoice_processing_bpmn()
    assert "agentType" in xml
    assert "du.uipath.com" in xml
    assert 'confidenceThreshold="0.80"' in xml


def test_bpmn_has_two_gateways_and_two_end_events() -> None:
    xml = generate_invoice_processing_bpmn()
    root = ET.fromstring(xml)
    gateways = [e for e in root.iter() if e.tag.endswith("}exclusiveGateway")]
    ends = [e for e in root.iter() if e.tag.endswith("}endEvent")]
    assert len(gateways) == 2
    assert len(ends) == 2


def test_bpmn_has_flow_from_rules_to_gateway() -> None:
    xml = generate_invoice_processing_bpmn()
    root = ET.fromstring(xml)
    flows = [e for e in root.iter() if e.tag.endswith("}sequenceFlow")]
    srcs_targets = {(e.get("sourceRef"), e.get("targetRef")) for e in flows}
    assert ("Task_Rules", "Gateway_Verdict") in srcs_targets
    assert ("Gateway_Verdict", "Task_CreateBill") in srcs_targets
    assert ("Task_CreateBill", "Task_Notify") in srcs_targets


def test_dmn_is_valid_xml() -> None:
    xml = generate_invoice_rules_dmn()
    root = ET.fromstring(xml)
    assert root.tag.endswith("definitions")


def test_dmn_has_decision_table_with_inputs_and_outputs() -> None:
    xml = generate_invoice_rules_dmn()
    root = ET.fromstring(xml)
    inputs = [e for e in root.iter() if e.tag.endswith("}input")]
    outputs = [e for e in root.iter() if e.tag.endswith("}output")]
    rules = [e for e in root.iter() if e.tag.endswith("}rule")]
    assert len(inputs) == 5   # Currency, IsDuplicate, IsNewVendor, AmountUsd, Confidence
    assert len(outputs) == 2  # Verdict, Reason
    assert len(rules) >= 6    # at least 6 decision rows


def test_dmn_encodes_auto_process_as_default() -> None:
    xml = generate_invoice_rules_dmn()
    assert "AutoProcess" in xml
    assert "FlagForReview" in xml
    assert "Reject" in xml


def test_dmn_first_hit_policy() -> None:
    xml = generate_invoice_rules_dmn()
    assert 'hitPolicy="FIRST"' in xml
