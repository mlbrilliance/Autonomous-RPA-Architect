"""Pydantic v2 Intermediate Representation (IR) models for RPA processes.

These models capture the full semantics of a Process Design Document in a
structured, machine-readable form that can be validated, transformed, and
used to generate UiPath projects.
"""

from __future__ import annotations

from typing import Any, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field


class UIAction(BaseModel):
    """A single UI interaction step."""

    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "action": "click",
                    "target": "Login Button",
                    "selector_hint": "<html app='chrome.exe' /><webctrl tag='button' id='loginBtn' />",
                    "confidence": 0.85,
                },
                {
                    "action": "type_into",
                    "target": "Username Field",
                    "value": "{{username}}",
                    "selector_hint": "<webctrl tag='input' name='user' />",
                    "confidence": 0.9,
                },
            ]
        }
    )

    action: Literal[
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
    ] = Field(description="Type of UI action to perform.")
    target: str = Field(description="Human-readable description of the UI element target.")
    value: Optional[str] = Field(default=None, description="Value to type, select, or use.")
    selector_hint: Optional[str] = Field(
        default=None,
        description="UiPath-style selector hint extracted or inferred from the PDD.",
    )
    confidence: float = Field(
        default=0.5,
        ge=0.0,
        le=1.0,
        description="Confidence that this action was correctly extracted (0.0-1.0).",
    )


class DataField(BaseModel):
    """A single field in a data contract."""

    name: str = Field(description="Field name.")
    type: str = Field(
        default="String",
        description="Data type (String, Int32, Boolean, DateTime, DataTable, etc.).",
    )
    required: bool = Field(default=True, description="Whether the field is required.")
    description: Optional[str] = Field(default=None, description="Field description.")
    validation_rules: list[str] = Field(
        default_factory=list,
        description="Validation rules or constraints for this field.",
    )


class DataContract(BaseModel):
    """A contract describing expected input or output data for a transaction."""

    fields: list[DataField] = Field(
        default_factory=list, description="Fields in this data contract."
    )


class BusinessRule(BaseModel):
    """A business rule that governs process behavior."""

    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "id": "BR001",
                    "condition": "Invoice amount exceeds $10,000",
                    "outcome": "route",
                    "reason": "High-value invoices require manager approval.",
                    "parameters": {"route_to": "ManagerApprovalQueue"},
                }
            ]
        }
    )

    id: str = Field(description="Unique business rule identifier.")
    condition: str = Field(description="Human-readable condition expression.")
    outcome: Literal[
        "business_exception",
        "system_exception",
        "skip",
        "retry",
        "route",
        "escalate",
    ] = Field(description="What happens when the condition is met.")
    reason: Optional[str] = Field(default=None, description="Explanation of the rule.")
    parameters: dict[str, Any] = Field(
        default_factory=dict,
        description="Additional parameters for the outcome (e.g., retry count, queue name).",
    )


class Step(BaseModel):
    """A single process step within a transaction."""

    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "id": "S001",
                    "type": "login_sequence",
                    "system_ref": "SAP_GUI",
                    "description": "Log into SAP using stored credentials.",
                    "actions": [
                        {
                            "action": "type_into",
                            "target": "Username field",
                            "value": "{{sap_user}}",
                            "confidence": 0.9,
                        },
                        {
                            "action": "type_into",
                            "target": "Password field",
                            "value": "{{sap_pass}}",
                            "confidence": 0.9,
                        },
                        {
                            "action": "click",
                            "target": "Login button",
                            "confidence": 0.85,
                        },
                    ],
                }
            ]
        }
    )

    id: str = Field(description="Unique step identifier (e.g., S001).")
    type: Literal[
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
    ] = Field(description="Category of this step.")
    system_ref: Optional[str] = Field(
        default=None,
        description="Reference to a system name defined in ProcessIR.systems.",
    )
    actions: list[UIAction] = Field(
        default_factory=list, description="Ordered list of UI actions in this step."
    )
    parameters: dict[str, Any] = Field(
        default_factory=dict,
        description="Step-specific parameters (e.g., URL, query, timeout).",
    )
    uncertainty: Optional[str] = Field(
        default=None,
        description="Description of ambiguity or uncertainty in the PDD for this step.",
    )
    substeps: list[Step] = Field(
        default_factory=list,
        description="Nested substeps for compound steps (decision branches, loop bodies).",
    )
    description: Optional[str] = Field(
        default=None, description="Human-readable description of what this step does."
    )


class ExceptionCategory(BaseModel):
    """A category of exception that can occur in the process."""

    name: str = Field(description="Exception category name (e.g., InvalidInvoice).")
    type: Literal["business", "system"] = Field(
        description="Whether this is a business or system exception."
    )
    retry_count: int = Field(
        default=0,
        ge=0,
        description="Number of retries before escalation.",
    )
    description: Optional[str] = Field(
        default=None, description="Description of when this exception occurs."
    )


class Transaction(BaseModel):
    """A transaction item representing one unit of work in the process."""

    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "name": "ProcessInvoice",
                    "input_contract": {
                        "fields": [
                            {"name": "InvoiceNumber", "type": "String", "required": True},
                            {"name": "Amount", "type": "Decimal", "required": True},
                        ]
                    },
                    "output_contract": {
                        "fields": [
                            {"name": "Status", "type": "String", "required": True},
                        ]
                    },
                    "steps": [],
                    "business_rules": [],
                }
            ]
        }
    )

    name: str = Field(description="Transaction name (e.g., ProcessInvoice).")
    input_contract: Optional[DataContract] = Field(
        default=None, description="Expected input data schema."
    )
    output_contract: Optional[DataContract] = Field(
        default=None, description="Expected output data schema."
    )
    steps: list[Step] = Field(
        default_factory=list, description="Ordered process steps for this transaction."
    )
    business_rules: list[BusinessRule] = Field(
        default_factory=list, description="Business rules governing this transaction."
    )


class SystemInfo(BaseModel):
    """An application or system involved in the process."""

    name: str = Field(description="System display name.")
    type: Literal[
        "web", "desktop", "api", "database", "excel", "email", "sap", "mainframe"
    ] = Field(description="Type of system/application.")
    url: Optional[str] = Field(default=None, description="URL or connection string.")
    login_required: bool = Field(
        default=False, description="Whether authentication is needed."
    )


class CredentialInfo(BaseModel):
    """A credential or asset stored in UiPath Orchestrator."""

    name: str = Field(description="Credential/asset name.")
    type: Literal["credential", "asset", "queue"] = Field(
        description="Type of Orchestrator resource."
    )
    orchestrator_path: Optional[str] = Field(
        default=None,
        description="Full Orchestrator path (e.g., folder/asset_name).",
    )
    description: Optional[str] = Field(
        default=None, description="What this credential is used for."
    )


class DocumentUnderstandingSpec(BaseModel):
    """Document Understanding configuration for a process.

    When set on :class:`ProcessIR`, the generator emits an IXP-style
    ``Framework/DocumentUnderstandingFlow.xaml`` subflow, a
    ``DocumentProcessing/taxonomy.json`` file, and registers the
    UiPath.IntelligentOCR + DocumentUnderstanding NuGet dependencies in
    project.json. The Maestro planner injects a Document Understanding
    service task plus an Action Center validation user task gated on the
    confidence threshold.
    """

    enabled: bool = Field(default=True, description="Whether DU is enabled.")
    document_type: str = Field(
        default="Invoice",
        description="Document content type (Invoice, Receipt, PurchaseOrder, ...).",
    )
    extraction_endpoint: str = Field(
        default="https://du.uipath.com/document/invoices",
        description="DU extraction endpoint URL (defaults to public Invoice model).",
    )
    api_key_asset: str = Field(
        default="DUApiKey",
        description="Orchestrator asset name holding the DU API key.",
    )
    confidence_threshold: float = Field(
        default=0.8,
        ge=0.0,
        le=1.0,
        description="Minimum confidence required to skip Action Center validation.",
    )
    fields: list[str] = Field(
        default_factory=list,
        description="Field names to extract. Empty = use the default Invoice taxonomy.",
    )


class ProcessIR(BaseModel):
    """Root Intermediate Representation of an RPA process.

    This is the complete, structured representation of a process extracted
    from a Process Design Document. It serves as the canonical input to
    the UiPath project generator.
    """

    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "process_name": "InvoiceProcessing",
                    "process_type": "transactional",
                    "description": "Automated invoice processing from email to ERP entry.",
                    "systems": [
                        {"name": "Outlook", "type": "desktop", "login_required": True},
                        {"name": "SAP_GUI", "type": "sap", "url": "sap://prod", "login_required": True},
                    ],
                    "credentials": [
                        {"name": "SAP_Cred", "type": "credential", "orchestrator_path": "Production/SAP_ServiceAccount"},
                    ],
                    "transactions": [
                        {
                            "name": "ProcessInvoice",
                            "steps": [],
                            "business_rules": [],
                        }
                    ],
                    "config": {"MaxRetryNumber": "3", "LogLevel": "Info"},
                    "exception_categories": [
                        {"name": "InvalidInvoice", "type": "business", "retry_count": 0},
                    ],
                }
            ]
        }
    )

    process_name: str = Field(description="Name of the RPA process.")
    process_type: Literal["transactional", "linear", "event_driven"] = Field(
        default="transactional",
        description="Process execution pattern.",
    )
    description: Optional[str] = Field(
        default=None, description="High-level process description."
    )
    systems: list[SystemInfo] = Field(
        default_factory=list,
        description="Applications and systems used by the process.",
    )
    credentials: list[CredentialInfo] = Field(
        default_factory=list,
        description="Orchestrator credentials and assets required.",
    )
    transactions: list[Transaction] = Field(
        default_factory=list,
        description="Transaction items (units of work).",
    )
    config: dict[str, str] = Field(
        default_factory=dict,
        description="Configuration entries (maps to UiPath Config.xlsx).",
    )
    exception_categories: list[ExceptionCategory] = Field(
        default_factory=list,
        description="Exception categories for the process.",
    )
    metadata: dict[str, Any] = Field(
        default_factory=dict,
        description="Additional metadata (author, version, extraction date, etc.).",
    )
    document_understanding: Optional[DocumentUnderstandingSpec] = Field(
        default=None,
        description="Document Understanding (IXP) configuration. None disables DU.",
    )
