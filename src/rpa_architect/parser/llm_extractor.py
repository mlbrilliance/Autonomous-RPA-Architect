"""LLM-based semantic extraction from PDD content to ProcessIR.

Uses structured output (JSON schema enforcement) with multi-pass extraction:
1. Metadata pass: process name, type, description, systems, credentials
2. Transactions pass: transaction names, data contracts
3. Steps pass: detailed steps with UI actions for each transaction
4. Business rules pass: rules, exceptions, decision logic

Ambiguous or unclear elements are flagged via the ``uncertainty`` field on steps.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, Protocol, runtime_checkable

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
from rpa_architect.parser.base import PddContent

logger = logging.getLogger(__name__)

# Path to the prompt template
PROMPT_TEMPLATE_PATH = Path(__file__).parent.parent.parent.parent / "knowledge" / "prompts" / "pdd_to_ir.md"


@runtime_checkable
class LLMClient(Protocol):
    """Protocol for LLM client used by the extractor.

    Implementations must provide an async method that sends a prompt
    and returns a structured JSON response.
    """

    async def generate_json(
        self,
        system_prompt: str,
        user_prompt: str,
        json_schema: dict[str, Any] | None = None,
        temperature: float = 0.0,
        max_tokens: int = 4096,
    ) -> dict[str, Any]:
        """Generate a structured JSON response from the LLM.

        Args:
            system_prompt: System-level instructions.
            user_prompt: User-level prompt with the content to process.
            json_schema: Optional JSON schema to enforce on the output.
            temperature: Sampling temperature.
            max_tokens: Maximum tokens in the response.

        Returns:
            Parsed JSON dictionary from the LLM response.
        """
        ...


def _load_prompt_template() -> str:
    """Load the PDD-to-IR prompt template from disk.

    Falls back to a built-in default if the file is not found.
    """
    if PROMPT_TEMPLATE_PATH.exists():
        return PROMPT_TEMPLATE_PATH.read_text(encoding="utf-8")

    return _DEFAULT_SYSTEM_PROMPT


_DEFAULT_SYSTEM_PROMPT = """\
You are an expert RPA process analyst. Your task is to extract structured process
information from a Process Design Document (PDD) and convert it into a precise
Intermediate Representation (IR) format.

RULES:
- Extract ALL information present in the document. Do not invent steps that aren't described.
- For each step, identify the target system/application and the specific UI actions.
- If something is ambiguous or unclear in the document, set the "uncertainty" field
  on the step to describe what is unclear.
- Use the exact field names and enum values from the provided JSON schema.
- Selector hints should be inferred from screenshots or descriptions when possible.
- Set confidence scores: 0.9+ for explicitly described actions, 0.5-0.8 for inferred
  actions, below 0.5 for guesses.
- Business rules should capture all conditional logic, exception handling, and routing.
"""


def _serialize_pdd_content(content: PddContent) -> str:
    """Serialize PDD content into a text format suitable for LLM input."""
    parts: list[str] = []

    # Document metadata
    if content.metadata:
        parts.append("=== DOCUMENT METADATA ===")
        for key, value in content.metadata.items():
            parts.append(f"{key}: {value}")
        parts.append("")

    # Text sections
    if content.sections:
        parts.append("=== DOCUMENT CONTENT ===")
        for section in content.sections:
            indent = "#" * section.level
            if section.title:
                parts.append(f"{indent} {section.title}")
            if section.content:
                parts.append(section.content)
            parts.append("")

    # Tables
    if content.tables:
        parts.append("=== TABLES ===")
        for i, table in enumerate(content.tables):
            if table.caption:
                parts.append(f"Table {i + 1}: {table.caption}")
            else:
                parts.append(f"Table {i + 1}:")

            if table.headers:
                parts.append(" | ".join(table.headers))
                parts.append(" | ".join("---" for _ in table.headers))

            for row in table.rows:
                parts.append(" | ".join(row))
            parts.append("")

    # Image references (we note their existence; actual images may be sent separately)
    if content.images:
        parts.append(f"=== IMAGES: {len(content.images)} screenshots/figures embedded ===")
        parts.append("")

    return "\n".join(parts)


def _build_metadata_schema() -> dict[str, Any]:
    """Build JSON schema for the metadata extraction pass."""
    return {
        "type": "object",
        "properties": {
            "process_name": {"type": "string"},
            "process_type": {
                "type": "string",
                "enum": ["transactional", "linear", "event_driven"],
            },
            "description": {"type": "string"},
            "systems": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "name": {"type": "string"},
                        "type": {
                            "type": "string",
                            "enum": [
                                "web", "desktop", "api", "database",
                                "excel", "email", "sap", "mainframe",
                            ],
                        },
                        "url": {"type": ["string", "null"]},
                        "login_required": {"type": "boolean"},
                    },
                    "required": ["name", "type"],
                },
            },
            "credentials": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "name": {"type": "string"},
                        "type": {
                            "type": "string",
                            "enum": ["credential", "asset", "queue"],
                        },
                        "orchestrator_path": {"type": ["string", "null"]},
                        "description": {"type": ["string", "null"]},
                    },
                    "required": ["name", "type"],
                },
            },
        },
        "required": ["process_name", "process_type", "description", "systems", "credentials"],
    }


def _build_transactions_schema() -> dict[str, Any]:
    """Build JSON schema for the transaction extraction pass."""
    field_schema = {
        "type": "object",
        "properties": {
            "name": {"type": "string"},
            "type": {"type": "string"},
            "required": {"type": "boolean"},
            "description": {"type": ["string", "null"]},
            "validation_rules": {"type": "array", "items": {"type": "string"}},
        },
        "required": ["name"],
    }
    contract_schema = {
        "type": ["object", "null"],
        "properties": {
            "fields": {"type": "array", "items": field_schema},
        },
    }
    return {
        "type": "object",
        "properties": {
            "transactions": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "name": {"type": "string"},
                        "input_contract": contract_schema,
                        "output_contract": contract_schema,
                    },
                    "required": ["name"],
                },
            },
        },
        "required": ["transactions"],
    }


def _build_steps_schema() -> dict[str, Any]:
    """Build JSON schema for the step extraction pass."""
    action_schema = {
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "enum": [
                    "click", "type_into", "get_text", "select_item",
                    "check", "uncheck", "hover", "extract_data",
                    "wait_element", "keyboard_shortcut", "scroll", "drag_drop",
                ],
            },
            "target": {"type": "string"},
            "value": {"type": ["string", "null"]},
            "selector_hint": {"type": ["string", "null"]},
            "confidence": {"type": "number"},
        },
        "required": ["action", "target"],
    }

    step_schema: dict[str, Any] = {
        "type": "object",
        "properties": {
            "id": {"type": "string"},
            "type": {
                "type": "string",
                "enum": [
                    "open_application", "login_sequence", "ui_flow",
                    "data_operation", "api_call", "decision", "loop",
                    "close_application", "wait", "navigate",
                    "extract_data", "transform_data",
                ],
            },
            "system_ref": {"type": ["string", "null"]},
            "actions": {"type": "array", "items": action_schema},
            "parameters": {"type": "object"},
            "uncertainty": {"type": ["string", "null"]},
            "description": {"type": ["string", "null"]},
            "substeps": {"type": "array", "items": {"type": "object"}},
        },
        "required": ["id", "type"],
    }

    return {
        "type": "object",
        "properties": {
            "transaction_name": {"type": "string"},
            "steps": {"type": "array", "items": step_schema},
        },
        "required": ["transaction_name", "steps"],
    }


def _build_rules_schema() -> dict[str, Any]:
    """Build JSON schema for the business rules extraction pass."""
    return {
        "type": "object",
        "properties": {
            "transaction_name": {"type": "string"},
            "business_rules": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "id": {"type": "string"},
                        "condition": {"type": "string"},
                        "outcome": {
                            "type": "string",
                            "enum": [
                                "business_exception", "system_exception",
                                "skip", "retry", "route", "escalate",
                            ],
                        },
                        "reason": {"type": ["string", "null"]},
                        "parameters": {"type": "object"},
                    },
                    "required": ["id", "condition", "outcome"],
                },
            },
            "exception_categories": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "name": {"type": "string"},
                        "type": {"type": "string", "enum": ["business", "system"]},
                        "retry_count": {"type": "integer"},
                        "description": {"type": ["string", "null"]},
                    },
                    "required": ["name", "type"],
                },
            },
        },
        "required": ["transaction_name", "business_rules", "exception_categories"],
    }


def _parse_steps(raw_steps: list[dict[str, Any]]) -> list[Step]:
    """Parse raw step dictionaries into Step models, handling nested substeps."""
    steps: list[Step] = []
    for raw in raw_steps:
        # Parse actions
        actions = [
            UIAction(
                action=a["action"],
                target=a.get("target", ""),
                value=a.get("value"),
                selector_hint=a.get("selector_hint"),
                confidence=a.get("confidence", 0.5),
            )
            for a in raw.get("actions", [])
        ]

        # Parse substeps recursively
        substeps = _parse_steps(raw.get("substeps", []))

        steps.append(
            Step(
                id=raw.get("id", ""),
                type=raw.get("type", "ui_flow"),
                system_ref=raw.get("system_ref"),
                actions=actions,
                parameters=raw.get("parameters", {}),
                uncertainty=raw.get("uncertainty"),
                substeps=substeps,
                description=raw.get("description"),
            )
        )
    return steps


async def extract_ir(content: PddContent, llm_client: LLMClient) -> ProcessIR:
    """Extract a ProcessIR from parsed PDD content using multi-pass LLM extraction.

    Pass 1 - Metadata: Extract process name, type, description, systems, credentials.
    Pass 2 - Transactions: Extract transaction definitions and data contracts.
    Pass 3 - Steps: For each transaction, extract detailed process steps with UI actions.
    Pass 4 - Business Rules: For each transaction, extract business rules and exceptions.

    Args:
        content: Parsed PDD content from a PddParser.
        llm_client: An LLM client implementing the LLMClient protocol.

    Returns:
        Complete ProcessIR extracted from the document.
    """
    system_prompt = _load_prompt_template()
    pdd_text = _serialize_pdd_content(content)

    # ---- Pass 1: Metadata ----
    logger.info("Pass 1/4: Extracting process metadata...")
    metadata_result = await llm_client.generate_json(
        system_prompt=system_prompt,
        user_prompt=(
            "Extract the process metadata from this PDD document. "
            "Identify the process name, type (transactional/linear/event_driven), "
            "description, all systems/applications used, and credentials needed.\n\n"
            f"{pdd_text}"
        ),
        json_schema=_build_metadata_schema(),
        temperature=0.0,
        max_tokens=2048,
    )

    process_name = metadata_result.get("process_name", "UnknownProcess")
    process_type = metadata_result.get("process_type", "transactional")
    description = metadata_result.get("description", "")

    systems = [
        SystemInfo(
            name=s["name"],
            type=s.get("type", "web"),
            url=s.get("url"),
            login_required=s.get("login_required", False),
        )
        for s in metadata_result.get("systems", [])
    ]

    credentials = [
        CredentialInfo(
            name=c["name"],
            type=c.get("type", "credential"),
            orchestrator_path=c.get("orchestrator_path"),
            description=c.get("description"),
        )
        for c in metadata_result.get("credentials", [])
    ]

    # ---- Pass 2: Transactions ----
    logger.info("Pass 2/4: Extracting transactions and data contracts...")
    txn_result = await llm_client.generate_json(
        system_prompt=system_prompt,
        user_prompt=(
            "Extract the transaction items (units of work) from this PDD document. "
            "For each transaction, identify the name, input data contract (fields the "
            "transaction receives), and output data contract (fields it produces).\n\n"
            f"Process: {process_name}\n"
            f"Systems: {', '.join(s.name for s in systems)}\n\n"
            f"{pdd_text}"
        ),
        json_schema=_build_transactions_schema(),
        temperature=0.0,
        max_tokens=4096,
    )

    transactions: list[Transaction] = []
    for txn_raw in txn_result.get("transactions", []):
        input_contract = None
        output_contract = None

        if txn_raw.get("input_contract") and txn_raw["input_contract"].get("fields"):
            input_contract = DataContract(
                fields=[
                    DataField(
                        name=f["name"],
                        type=f.get("type", "String"),
                        required=f.get("required", True),
                        description=f.get("description"),
                        validation_rules=f.get("validation_rules", []),
                    )
                    for f in txn_raw["input_contract"]["fields"]
                ]
            )

        if txn_raw.get("output_contract") and txn_raw["output_contract"].get("fields"):
            output_contract = DataContract(
                fields=[
                    DataField(
                        name=f["name"],
                        type=f.get("type", "String"),
                        required=f.get("required", True),
                        description=f.get("description"),
                        validation_rules=f.get("validation_rules", []),
                    )
                    for f in txn_raw["output_contract"]["fields"]
                ]
            )

        transactions.append(
            Transaction(
                name=txn_raw.get("name", "UnnamedTransaction"),
                input_contract=input_contract,
                output_contract=output_contract,
                steps=[],
                business_rules=[],
            )
        )

    # If no transactions found, create a default one
    if not transactions:
        logger.warning("No transactions found; creating a default transaction.")
        transactions.append(
            Transaction(name="MainTransaction", steps=[], business_rules=[])
        )

    # ---- Pass 3: Steps (per transaction) ----
    logger.info("Pass 3/4: Extracting process steps for each transaction...")
    for txn in transactions:
        steps_result = await llm_client.generate_json(
            system_prompt=system_prompt,
            user_prompt=(
                f"Extract the detailed process steps for the transaction '{txn.name}' "
                f"from this PDD document. For each step, identify:\n"
                f"- Step ID and type\n"
                f"- Target system (must be one of: {', '.join(s.name for s in systems)})\n"
                f"- UI actions with targets, values, and selector hints\n"
                f"- Any sub-steps for decisions or loops\n"
                f"- Flag anything unclear with the 'uncertainty' field\n\n"
                f"Process: {process_name}\n"
                f"Transaction: {txn.name}\n\n"
                f"{pdd_text}"
            ),
            json_schema=_build_steps_schema(),
            temperature=0.0,
            max_tokens=8192,
        )

        txn.steps = _parse_steps(steps_result.get("steps", []))

    # ---- Pass 4: Business Rules (per transaction) ----
    logger.info("Pass 4/4: Extracting business rules and exception categories...")
    all_exception_categories: list[ExceptionCategory] = []
    seen_exception_names: set[str] = set()

    for txn in transactions:
        rules_result = await llm_client.generate_json(
            system_prompt=system_prompt,
            user_prompt=(
                f"Extract the business rules and exception categories for the "
                f"transaction '{txn.name}' from this PDD document. Identify:\n"
                f"- Conditional logic and decision rules\n"
                f"- Exception handling (business vs system exceptions)\n"
                f"- Retry policies, routing rules, escalation paths\n\n"
                f"Process: {process_name}\n"
                f"Transaction: {txn.name}\n"
                f"Steps: {json.dumps([s.model_dump() for s in txn.steps], default=str)[:2000]}\n\n"
                f"{pdd_text}"
            ),
            json_schema=_build_rules_schema(),
            temperature=0.0,
            max_tokens=4096,
        )

        txn.business_rules = [
            BusinessRule(
                id=r["id"],
                condition=r["condition"],
                outcome=r["outcome"],
                reason=r.get("reason"),
                parameters=r.get("parameters", {}),
            )
            for r in rules_result.get("business_rules", [])
        ]

        for exc_raw in rules_result.get("exception_categories", []):
            exc_name = exc_raw["name"]
            if exc_name not in seen_exception_names:
                all_exception_categories.append(
                    ExceptionCategory(
                        name=exc_name,
                        type=exc_raw.get("type", "business"),
                        retry_count=exc_raw.get("retry_count", 0),
                        description=exc_raw.get("description"),
                    )
                )
                seen_exception_names.add(exc_name)

    # Assemble the final ProcessIR
    process_ir = ProcessIR(
        process_name=process_name,
        process_type=process_type,
        description=description,
        systems=systems,
        credentials=credentials,
        transactions=transactions,
        config={},
        exception_categories=all_exception_categories,
        metadata={
            "source_type": "pdd",
            "extraction_method": "llm_multi_pass",
            "document_metadata": content.metadata,
        },
    )

    logger.info(
        "Extraction complete: %s with %d transactions, %d total steps",
        process_name,
        len(transactions),
        sum(len(t.steps) for t in transactions),
    )

    return process_ir
