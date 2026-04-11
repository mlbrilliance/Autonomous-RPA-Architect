"""Tests for REFramework + project.json integration with Document Understanding."""

from __future__ import annotations

from rpa_architect.assembler.project_json_gen import generate_project_json
from rpa_architect.assembler.reframework_gen import generate_reframework_xaml
from rpa_architect.ir.schema import (
    DocumentUnderstandingSpec,
    ProcessIR,
    Step,
    SystemInfo,
    Transaction,
)


def _make_ir_with_du() -> ProcessIR:
    return ProcessIR(
        process_name="OdooInvoiceProcessing",
        process_type="transactional",
        systems=[
            SystemInfo(
                name="Odoo",
                type="web",
                url="http://localhost:8069",
                login_required=True,
            )
        ],
        transactions=[
            Transaction(
                name="ProcessInvoice",
                steps=[
                    Step(
                        id="S001",
                        type="ui_flow",
                        description="Create vendor bill in Odoo",
                    )
                ],
                business_rules=[],
            )
        ],
        document_understanding=DocumentUnderstandingSpec(
            document_type="Invoice",
            extraction_endpoint="https://du.uipath.com/document/invoices",
            confidence_threshold=0.8,
        ),
    )


def _make_ir_without_du() -> ProcessIR:
    return ProcessIR(
        process_name="NoDU",
        systems=[],
        transactions=[],
    )


def test_reframework_files_include_du_subflow_when_du_present() -> None:
    ir = _make_ir_with_du()
    files = generate_reframework_xaml(ir)
    assert "Framework/DocumentUnderstandingFlow.xaml" in files


def test_reframework_files_exclude_du_subflow_when_no_du_spec() -> None:
    ir = _make_ir_without_du()
    files = generate_reframework_xaml(ir)
    assert "Framework/DocumentUnderstandingFlow.xaml" not in files


def test_process_xaml_invokes_du_subflow_when_du_present() -> None:
    ir = _make_ir_with_du()
    files = generate_reframework_xaml(ir)
    process = files["Framework/Process.xaml"]
    assert "DocumentUnderstandingFlow" in process


def test_du_subflow_xaml_is_non_empty() -> None:
    ir = _make_ir_with_du()
    files = generate_reframework_xaml(ir)
    xaml = files["Framework/DocumentUnderstandingFlow.xaml"]
    assert len(xaml) > 100  # arbitrary nonzero
    assert "in_DocumentPath" in xaml


def test_project_json_includes_intelligent_ocr_when_du_present() -> None:
    ir = _make_ir_with_du()
    json_str = generate_project_json(ir)
    assert "UiPath.IntelligentOCR.Activities" in json_str


def test_project_json_includes_du_ml_when_du_present() -> None:
    ir = _make_ir_with_du()
    json_str = generate_project_json(ir)
    assert "UiPath.DocumentUnderstanding" in json_str


def test_project_json_excludes_intelligent_ocr_when_no_du() -> None:
    ir = _make_ir_without_du()
    json_str = generate_project_json(ir)
    assert "UiPath.IntelligentOCR.Activities" not in json_str
