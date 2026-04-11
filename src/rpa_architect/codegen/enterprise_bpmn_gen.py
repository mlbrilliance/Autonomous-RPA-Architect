"""Generate real BPMN 2.0 + DMN 1.3 design assets for Studio Web import.

These are NOT bundled inside the .nupkg (that was earlier fakery —
Orchestrator ignores extra files). They're written as sibling
design-time artifacts that a human can upload via Studio Web's
Maestro designer.

The BPMN diagram mirrors the real enterprise pipeline in the C#
state machine:

    Start → Receive Invoice Batch
         → Document Understanding (agent:// marker)
         → Gateway: confidence < threshold?
            ├─ YES → Human Validation (User Task, Action Center)
            └─ NO  → Business Rule Task (DMN)
                     → Gateway: verdict
                        ├─ AutoProcess → Create Vendor Bill in Odoo
                        │                → Send Confirmation Email
                        │                → End
                        ├─ FlagForReview → Create Manager Approval Task
                        │                   → Create Vendor Bill
                        │                   → End
                        └─ Reject → Log Exception → End

The DMN decision table encodes the 4-rule business logic in a single
tabular format that business analysts can edit in Studio Web without
touching C#.
"""

from __future__ import annotations

import xml.etree.ElementTree as ET


_BPMN_NS = "http://www.omg.org/spec/BPMN/20100524/MODEL"
_DI_NS = "http://www.omg.org/spec/DD/20100524/DI"
_DC_NS = "http://www.omg.org/spec/DD/20100524/DC"
_BPMNDI_NS = "http://www.omg.org/spec/BPMN/20100524/DI"
_DMN_NS = "https://www.omg.org/spec/DMN/20191111/MODEL/"


def generate_invoice_processing_bpmn(process_name: str = "InvoiceProcessingFlow") -> str:
    """Return a complete BPMN 2.0 XML document for the invoice pipeline."""
    ET.register_namespace("bpmn", _BPMN_NS)
    ET.register_namespace("bpmndi", _BPMNDI_NS)
    ET.register_namespace("dc", _DC_NS)
    ET.register_namespace("di", _DI_NS)

    defs = ET.Element(
        f"{{{_BPMN_NS}}}definitions",
        {
            "id": "Definitions_InvoiceProcessingFlow",
            "targetNamespace": "http://uipath.com/invoice-processing-factory",
        },
    )
    proc = ET.SubElement(
        defs,
        f"{{{_BPMN_NS}}}process",
        {"id": f"Process_{process_name}", "name": process_name, "isExecutable": "true"},
    )

    def _el(tag: str, attrs: dict[str, str]) -> ET.Element:
        return ET.SubElement(proc, f"{{{_BPMN_NS}}}{tag}", attrs)

    # Events
    _el("startEvent", {"id": "Start_1", "name": "Invoice batch arrives"})
    _el("endEvent", {"id": "End_Success", "name": "Batch processed"})
    _el("endEvent", {"id": "End_Reject", "name": "Batch rejected"})

    # Service tasks
    _el("serviceTask", {
        "id": "Task_ReceiveBatch",
        "name": "Receive Invoice Batch",
        "implementation": "uipath://queue/OdooInvoices",
    })
    agent_task = _el("serviceTask", {
        "id": "Task_DU",
        "name": "Document Understanding",
        "implementation": "agent://du.extractor",
    })
    # Agent extension metadata
    ext_el = ET.SubElement(agent_task, f"{{{_BPMN_NS}}}extensionElements")
    agent_config = ET.SubElement(ext_el, "agentConfiguration")
    agent_config.set("agentType", "extraction")
    agent_config.set("model", "du.uipath.com/invoices")
    agent_config.set("fallbackToHuman", "true")
    agent_config.set("confidenceThreshold", "0.80")

    _el("businessRuleTask", {
        "id": "Task_Rules",
        "name": "Evaluate Business Rules",
        "decisionRef": "Decision_InvoiceRules",
    })
    _el("serviceTask", {
        "id": "Task_CreateBill",
        "name": "Create Vendor Bill in Odoo",
        "implementation": "uipath://process/OdooInvoiceProcessing",
    })
    _el("serviceTask", {
        "id": "Task_Notify",
        "name": "Send Confirmation Email",
        "implementation": "uipath://email/smtp",
    })
    _el("serviceTask", {
        "id": "Task_LogRejection",
        "name": "Log Rejection",
        "implementation": "uipath://logger",
    })

    # User task — Action Center (only available on Enterprise tier).
    _el("userTask", {
        "id": "Task_HumanValidation",
        "name": "Human Validation (Action Center)",
    })
    _el("userTask", {
        "id": "Task_ManagerApproval",
        "name": "Manager Approval (mail.activity)",
    })

    # Gateways
    _el("exclusiveGateway", {"id": "Gateway_Confidence", "name": "Confidence ≥ 0.8?"})
    _el("exclusiveGateway", {"id": "Gateway_Verdict", "name": "Rule verdict?"})

    # Sequence flows
    flows = [
        ("F1", "Start_1", "Task_ReceiveBatch", None),
        ("F2", "Task_ReceiveBatch", "Task_DU", None),
        ("F3", "Task_DU", "Gateway_Confidence", None),
        ("F_HV", "Gateway_Confidence", "Task_HumanValidation", "confidence < 0.8"),
        ("F_HV_back", "Task_HumanValidation", "Task_Rules", None),
        ("F_Rules", "Gateway_Confidence", "Task_Rules", "confidence >= 0.8"),
        ("F_RulesVerdict", "Task_Rules", "Gateway_Verdict", None),
        ("F_Auto", "Gateway_Verdict", "Task_CreateBill", "verdict == AutoProcess"),
        ("F_Flag", "Gateway_Verdict", "Task_ManagerApproval", "verdict == FlagForReview"),
        ("F_Flag2Bill", "Task_ManagerApproval", "Task_CreateBill", None),
        ("F_Reject", "Gateway_Verdict", "Task_LogRejection", "verdict == Reject"),
        ("F_Reject2End", "Task_LogRejection", "End_Reject", None),
        ("F_BillNotify", "Task_CreateBill", "Task_Notify", None),
        ("F_NotifyEnd", "Task_Notify", "End_Success", None),
    ]
    for fid, src, tgt, cond in flows:
        attrs = {"id": fid, "sourceRef": src, "targetRef": tgt}
        flow_el = _el("sequenceFlow", attrs)
        if cond:
            cond_el = ET.SubElement(flow_el, f"{{{_BPMN_NS}}}conditionExpression")
            cond_el.text = cond

    ET.indent(defs, space="  ")
    return (
        '<?xml version="1.0" encoding="utf-8"?>\n'
        + ET.tostring(defs, encoding="unicode")
    )


def generate_invoice_rules_dmn(decision_name: str = "InvoiceRulesDecision") -> str:
    """Return a DMN 1.3 decision table encoding the 4 business rules."""
    ET.register_namespace("dmn", _DMN_NS)
    defs = ET.Element(
        f"{{{_DMN_NS}}}definitions",
        {
            "id": "Definitions_InvoiceRules",
            "name": "Invoice Processing Rules",
            "namespace": "http://uipath.com/invoice-processing-factory/rules",
        },
    )
    decision = ET.SubElement(
        defs,
        f"{{{_DMN_NS}}}decision",
        {"id": f"Decision_{decision_name}", "name": decision_name},
    )
    table = ET.SubElement(
        decision,
        f"{{{_DMN_NS}}}decisionTable",
        {"id": "Table_1", "hitPolicy": "FIRST"},
    )
    # Inputs
    inputs = [
        ("Currency", "string"),
        ("IsDuplicate", "boolean"),
        ("IsNewVendor", "boolean"),
        ("AmountUsd", "number"),
        ("Confidence", "number"),
    ]
    for name, type_ in inputs:
        input_el = ET.SubElement(table, f"{{{_DMN_NS}}}input", {"id": f"in_{name}", "label": name})
        expr_el = ET.SubElement(input_el, f"{{{_DMN_NS}}}inputExpression", {"id": f"ie_{name}", "typeRef": type_})
        txt_el = ET.SubElement(expr_el, f"{{{_DMN_NS}}}text")
        txt_el.text = name

    # Outputs
    outputs = [("Verdict", "string"), ("Reason", "string")]
    for name, type_ in outputs:
        out_el = ET.SubElement(
            table, f"{{{_DMN_NS}}}output",
            {"id": f"out_{name}", "label": name, "typeRef": type_}
        )

    # Rows (hit policy FIRST — first matching rule wins)
    rows = [
        # Currency not in whitelist → Reject
        (['not("USD","EUR","GBP")', "-", "-", "-", "-"], ["Reject", '"Currency not in whitelist"']),
        # Duplicate → Reject
        (["-", "true", "-", "-", "-"], ["Reject", '"Duplicate invoice detected"']),
        # Confidence < 0.8 → FlagForReview
        (["-", "-", "-", "-", "< 0.8"], ["FlagForReview", '"Low DU confidence"']),
        # Amount > $10,000 → FlagForReview
        (["-", "-", "-", "> 10000", "-"], ["FlagForReview", '"Amount exceeds manager threshold"']),
        # New vendor → FlagForReview
        (["-", "-", "true", "-", "-"], ["FlagForReview", '"New vendor — KYC required"']),
        # Amount > $2,500 (demo threshold) → FlagForReview
        (["-", "-", "-", "> 2500", "-"], ["FlagForReview", '"Amount exceeds demo threshold"']),
        # Default → AutoProcess
        (["-", "-", "-", "-", "-"], ["AutoProcess", '"All checks passed"']),
    ]
    for i, (inputs_vals, outputs_vals) in enumerate(rows, start=1):
        rule_el = ET.SubElement(table, f"{{{_DMN_NS}}}rule", {"id": f"Rule_{i}"})
        for val in inputs_vals:
            inp = ET.SubElement(rule_el, f"{{{_DMN_NS}}}inputEntry")
            txt = ET.SubElement(inp, f"{{{_DMN_NS}}}text")
            txt.text = val
        for val in outputs_vals:
            out = ET.SubElement(rule_el, f"{{{_DMN_NS}}}outputEntry")
            txt = ET.SubElement(out, f"{{{_DMN_NS}}}text")
            txt.text = val

    ET.indent(defs, space="  ")
    return (
        '<?xml version="1.0" encoding="utf-8"?>\n'
        + ET.tostring(defs, encoding="unicode")
    )
