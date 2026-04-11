"""Shared pytest fixtures for the rpa_architect test suite."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock

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
from rpa_architect.parser.base import PddContent, PddSection, PddTable


@pytest.fixture
def sample_ir() -> ProcessIR:
    """A complete ProcessIR for a simple invoice queue processing bot.

    Scenario: open web app, extract invoice data, validate, post to ERP.
    """
    return ProcessIR(
        process_name="InvoiceProcessing",
        process_type="transactional",
        description="Automated invoice processing from web portal to ERP.",
        systems=[
            SystemInfo(
                name="InvoicePortal",
                type="web",
                url="https://invoices.example.com",
                login_required=True,
            ),
            SystemInfo(
                name="ERPSystem",
                type="web",
                url="https://erp.example.com",
                login_required=True,
            ),
        ],
        credentials=[
            CredentialInfo(
                name="InvoicePortal_Cred",
                type="credential",
                orchestrator_path="Production/InvoicePortal_ServiceAccount",
                description="Service account for the invoice web portal.",
            ),
        ],
        transactions=[
            Transaction(
                name="ProcessInvoice",
                input_contract=DataContract(
                    fields=[
                        DataField(name="InvoiceNumber", type="String", required=True),
                        DataField(name="Amount", type="Decimal", required=True),
                        DataField(name="VendorName", type="String", required=True),
                    ]
                ),
                output_contract=DataContract(
                    fields=[
                        DataField(name="Status", type="String", required=True),
                        DataField(name="ERPReference", type="String", required=False),
                    ]
                ),
                steps=[
                    Step(
                        id="S001",
                        type="open_application",
                        system_ref="InvoicePortal",
                        description="Open the invoice web portal.",
                        actions=[
                            UIAction(
                                action="click",
                                target="Invoice Queue Tab",
                                selector_hint="<html app='chrome.exe' /><webctrl tag='a' innertext='Invoice Queue' />",
                                confidence=0.9,
                            ),
                        ],
                        parameters={"url": "https://invoices.example.com/queue"},
                    ),
                    Step(
                        id="S002",
                        type="extract_data",
                        system_ref="InvoicePortal",
                        description="Extract invoice details from the queue item.",
                        actions=[
                            UIAction(
                                action="get_text",
                                target="Invoice Number Field",
                                selector_hint="<html app='chrome.exe' /><webctrl tag='span' id='invoiceNum' />",
                                confidence=0.85,
                            ),
                            UIAction(
                                action="get_text",
                                target="Amount Field",
                                confidence=0.6,
                            ),
                        ],
                    ),
                    Step(
                        id="S003",
                        type="data_operation",
                        description="Validate extracted invoice data.",
                        parameters={"validation_type": "business_rules"},
                    ),
                    Step(
                        id="S004",
                        type="ui_flow",
                        system_ref="ERPSystem",
                        description="Post invoice data to the ERP system.",
                        actions=[
                            UIAction(
                                action="type_into",
                                target="Invoice Number Input",
                                value="{{InvoiceNumber}}",
                                selector_hint="<html app='chrome.exe' /><webctrl tag='input' name='inv_num' />",
                                confidence=0.8,
                            ),
                            UIAction(
                                action="click",
                                target="Submit Button",
                                selector_hint="<html app='chrome.exe' /><webctrl tag='button' id='submitBtn' />",
                                confidence=0.9,
                            ),
                        ],
                    ),
                ],
                business_rules=[
                    BusinessRule(
                        id="BR001",
                        condition="Invoice amount exceeds $10,000",
                        outcome="route",
                        reason="High-value invoices require manager approval.",
                        parameters={"route_to": "ManagerApprovalQueue"},
                    ),
                    BusinessRule(
                        id="BR002",
                        condition="Vendor is not in approved vendor list",
                        outcome="business_exception",
                        reason="Only approved vendors can be processed.",
                    ),
                ],
            ),
        ],
        config={
            "MaxRetryNumber": "3",
            "LogLevel": "Info",
            "InvoicePortalUrl": "https://invoices.example.com",
            "HighValueThreshold": "10000",
        },
        exception_categories=[
            ExceptionCategory(
                name="InvalidInvoice",
                type="business",
                retry_count=0,
                description="Invoice data is invalid.",
            ),
        ],
        metadata={"author": "Test Suite", "version": "1.0"},
    )


@pytest.fixture
def sample_pdd_content() -> PddContent:
    """PddContent with text sections and tables from a sample PDD."""
    return PddContent(
        sections=[
            PddSection(
                title="Process Overview",
                content="This process automates invoice processing from the web portal to the ERP system.",
                level=1,
                page_number=1,
            ),
            PddSection(
                title="Step-by-Step Instructions",
                content="1. Open the Invoice Portal.\n2. Extract invoice data.\n3. Validate data.\n4. Post to ERP.",
                level=2,
                page_number=2,
            ),
            PddSection(
                title="Business Rules",
                content="Invoices over $10,000 require manager approval. Unapproved vendors are rejected.",
                level=2,
                page_number=3,
            ),
        ],
        tables=[
            PddTable(
                headers=["Field", "Type", "Required"],
                rows=[
                    ["InvoiceNumber", "String", "Yes"],
                    ["Amount", "Decimal", "Yes"],
                    ["VendorName", "String", "Yes"],
                ],
                caption="Invoice Data Fields",
                page_number=2,
            ),
        ],
        metadata={"title": "Invoice Processing PDD", "author": "Business Analyst"},
    )


@pytest.fixture
def tmp_output_dir(tmp_path: Path) -> Path:
    """Temporary directory for generated output files."""
    output = tmp_path / "output"
    output.mkdir()
    return output


@pytest.fixture
def mock_llm_client() -> AsyncMock:
    """Async mock LLM client that returns canned responses."""
    client = AsyncMock()
    client.generate.return_value = {
        "content": '{"process_name": "TestProcess", "transactions": []}',
        "model": "mock-model",
        "usage": {"input_tokens": 100, "output_tokens": 50},
    }
    client.generate_structured.return_value = {
        "process_name": "TestProcess",
        "process_type": "transactional",
        "transactions": [],
    }
    return client


@pytest.fixture
def sample_transaction() -> Transaction:
    """A single Transaction fixture for focused testing."""
    return Transaction(
        name="ProcessInvoice",
        input_contract=DataContract(
            fields=[
                DataField(name="InvoiceNumber", type="String", required=True),
                DataField(name="Amount", type="Decimal", required=True),
            ]
        ),
        steps=[
            Step(
                id="S001",
                type="open_application",
                system_ref="WebApp",
                description="Open the web application.",
                actions=[
                    UIAction(action="click", target="Login Button", confidence=0.9),
                ],
            ),
            Step(
                id="S002",
                type="extract_data",
                description="Extract data from the page.",
                actions=[
                    UIAction(action="get_text", target="Data Field", confidence=0.8),
                ],
            ),
        ],
        business_rules=[
            BusinessRule(
                id="BR001",
                condition="Amount > 10000",
                outcome="route",
                reason="Requires approval.",
            ),
        ],
    )


@pytest.fixture
def sample_business_rules() -> list[BusinessRule]:
    """A list of BusinessRule fixtures covering different outcomes."""
    return [
        BusinessRule(
            id="BR001",
            condition="Invoice amount exceeds $10,000",
            outcome="route",
            reason="High-value invoices require manager approval.",
            parameters={"route_to": "ManagerApprovalQueue"},
        ),
        BusinessRule(
            id="BR002",
            condition="Vendor is not in approved vendor list",
            outcome="business_exception",
            reason="Only approved vendors can be processed.",
        ),
        BusinessRule(
            id="BR003",
            condition="ERP system is unavailable",
            outcome="system_exception",
            reason="Cannot connect to ERP.",
            parameters={"retry_count": 3},
        ),
        BusinessRule(
            id="BR004",
            condition="Duplicate invoice detected",
            outcome="skip",
            reason="Invoice already processed.",
        ),
        BusinessRule(
            id="BR005",
            condition="Network timeout during posting",
            outcome="retry",
            reason="Transient network error.",
            parameters={"max_retries": 3},
        ),
        BusinessRule(
            id="BR006",
            condition="Invoice flagged for audit",
            outcome="escalate",
            reason="Audit team must review.",
        ),
    ]
