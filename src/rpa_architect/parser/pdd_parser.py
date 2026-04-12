"""PDD Parser Aggregator — unified entry point for PDD → ProcessIR conversion.

Supports structured Markdown PDDs directly (no LLM required), and
delegates .pdf/.docx to existing parsers + LLM extractor.
"""

from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import Any

from rpa_architect.ir.schema import (
    BusinessRule,
    CredentialInfo,
    DocumentUnderstandingSpec,
    ProcessIR,
    Step,
    SystemInfo,
    Transaction,
    UIAction,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def parse_pdd(path: Path | str) -> ProcessIR:
    """Parse a PDD file into a ProcessIR.

    Args:
        path: Path to the PDD file (.md, .pdf, or .docx).

    Returns:
        Validated ProcessIR ready for code generation.

    Raises:
        FileNotFoundError: If the PDD file does not exist.
        ValueError: If the file format is unsupported or parsing fails.
    """
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"PDD not found: {path}")

    ext = path.suffix.lower()
    if ext == ".md":
        return _parse_markdown_pdd(path)
    elif ext in (".pdf", ".docx"):
        return _parse_with_llm(path, ext)
    else:
        raise ValueError(f"Unsupported PDD format: {ext}")


# ---------------------------------------------------------------------------
# Markdown PDD Parser (no LLM required)
# ---------------------------------------------------------------------------

def _parse_markdown_table(text: str) -> list[dict[str, str]]:
    """Parse a markdown table block into a list of row dicts."""
    lines = [ln.strip() for ln in text.strip().splitlines() if ln.strip()]
    if len(lines) < 3:
        return []

    # Find header row (first line with |)
    header_line = lines[0]
    headers = [h.strip() for h in header_line.strip("|").split("|")]

    rows: list[dict[str, str]] = []
    for line in lines[2:]:  # skip header + separator
        if "|" not in line:
            continue
        cells = [c.strip() for c in line.strip("|").split("|")]
        if len(cells) >= len(headers):
            rows.append({h: cells[i] for i, h in enumerate(headers)})
    return rows


def _extract_section(content: str, heading: str) -> str:
    """Extract content under a ## heading up to the next ## heading."""
    pattern = rf"^## {re.escape(heading)}\s*\n(.*?)(?=\n## |\Z)"
    match = re.search(pattern, content, re.DOTALL | re.MULTILINE | re.IGNORECASE)
    return match.group(1).strip() if match else ""


def _extract_subsections(section_text: str, level: str = "###") -> dict[str, str]:
    """Extract all subsections at a given heading level."""
    pattern = rf"^{re.escape(level)} (.+?)\s*\n(.*?)(?=\n{re.escape(level)} |\Z)"
    return {
        m.group(1).strip(): m.group(2).strip()
        for m in re.finditer(pattern, section_text, re.DOTALL | re.MULTILINE)
    }


def _find_table_in_text(text: str) -> str:
    """Find the first markdown table in a text block."""
    lines = text.splitlines()
    table_lines: list[str] = []
    in_table = False
    for line in lines:
        stripped = line.strip()
        if stripped.startswith("|") and "|" in stripped[1:]:
            in_table = True
            table_lines.append(stripped)
        elif in_table:
            break
    return "\n".join(table_lines)


def _parse_markdown_pdd(path: Path) -> ProcessIR:
    """Parse a structured Markdown PDD into ProcessIR without LLM."""
    content = path.read_text(encoding="utf-8")

    # --- Process Overview ---
    overview = _extract_section(content, "Process Overview")
    process_name = _extract_field(overview, "Name")
    process_type = _extract_field(overview, "Type") or "transactional"
    description = _extract_field(overview, "Description")
    topology_raw = _extract_field(overview, "Topology") or "single"
    if topology_raw not in ("single", "dispatcher_performer_reporter"):
        topology_raw = "single"

    # --- Systems ---
    systems_text = _extract_section(content, "Systems")
    table_text = _find_table_in_text(systems_text)
    systems = []
    for row in _parse_markdown_table(table_text):
        login_val = row.get("Login Required", "No").strip().lower()
        systems.append(SystemInfo(
            name=row.get("Name", ""),
            type=row.get("Type", "web").lower(),
            url=row.get("URL", ""),
            login_required=login_val in ("yes", "true", "1"),
        ))

    # --- Credentials ---
    creds_text = _extract_section(content, "Credentials")
    table_text = _find_table_in_text(creds_text)
    credentials = []
    for row in _parse_markdown_table(table_text):
        credentials.append(CredentialInfo(
            name=row.get("Name", ""),
            type=row.get("Type", "credential"),
            orchestrator_path=row.get("Orchestrator Path", ""),
            description=row.get("Description", ""),
        ))

    # --- Steps (global section) ---
    steps_text = _extract_section(content, "Steps")
    table_text = _find_table_in_text(steps_text)
    steps_by_id: dict[str, Step] = {}
    for row in _parse_markdown_table(table_text):
        step_id = row.get("ID", "")
        params: dict[str, Any] = {}
        if row.get("URL"):
            params["url"] = row["URL"]
        step = Step(
            id=step_id,
            type=row.get("Type", "ui_flow"),
            system_ref=row.get("System", ""),
            description=row.get("Description", ""),
            parameters=params,
            actions=[],
        )
        steps_by_id[step_id] = step

    # --- Actions (per-step subsections) ---
    actions_text = _extract_section(content, "Actions")
    action_subsections = _extract_subsections(actions_text)
    for subsection_name, subsection_text in action_subsections.items():
        # Extract step ID from subsection name like "S001 Actions"
        step_id_match = re.match(r"(S\d+)", subsection_name)
        if not step_id_match:
            continue
        step_id = step_id_match.group(1)
        if step_id not in steps_by_id:
            continue

        table_text = _find_table_in_text(subsection_text)
        for row in _parse_markdown_table(table_text):
            confidence = 0.5
            try:
                confidence = float(row.get("Confidence", "0.5"))
            except (ValueError, TypeError):
                pass
            steps_by_id[step_id].actions.append(UIAction(
                action=row.get("Action", "click"),
                target=row.get("Target", ""),
                value=row.get("Value", "") or None,
                confidence=confidence,
            ))

    # --- Transactions ---
    txn_text = _extract_section(content, "Transactions")
    txn_subsections = _extract_subsections(txn_text)
    transactions = []
    for txn_name, txn_content in txn_subsections.items():
        # All steps belong to this transaction (simple case)
        txn_steps = list(steps_by_id.values())
        transactions.append(Transaction(
            name=txn_name,
            steps=txn_steps,
            business_rules=[],
        ))

    # If no transaction subsections found, create a default one
    if not transactions and steps_by_id:
        transactions.append(Transaction(
            name="DefaultTransaction",
            steps=list(steps_by_id.values()),
            business_rules=[],
        ))

    # --- Configuration ---
    config_text = _extract_section(content, "Configuration")
    table_text = _find_table_in_text(config_text)
    config: dict[str, str] = {}
    for row in _parse_markdown_table(table_text):
        name = row.get("Name", "")
        value = row.get("Value", "")
        if name:
            config[name] = value

    # --- Document Understanding ---
    du_spec = _extract_du_spec(content)

    # --- Business Rules (attached to first/all transactions) ---
    business_rules = _extract_business_rules(content)
    if business_rules and transactions:
        # Attach to the first transaction by default.
        transactions[0] = transactions[0].model_copy(
            update={"business_rules": business_rules}
        )

    ir = ProcessIR(
        process_name=process_name,
        process_type=process_type,
        description=description,
        systems=systems,
        credentials=credentials,
        transactions=transactions,
        exception_categories=[],
        config=config,
        document_understanding=du_spec,
        process_topology=topology_raw,  # type: ignore[arg-type]
    )

    # Validate round-trip
    ir.model_validate(ir.model_dump())
    logger.info(
        "Parsed PDD '%s': %d systems, %d transactions, %d steps, %d config entries",
        process_name, len(systems), len(transactions),
        len(steps_by_id), len(config),
    )
    return ir


def _extract_du_spec(content: str) -> DocumentUnderstandingSpec | None:
    """Extract a ``DocumentUnderstandingSpec`` from a ``## Document Understanding`` section.

    Returns ``None`` if the section is absent.
    """
    section = _extract_section(content, "Document Understanding")
    if not section:
        return None

    document_type = _extract_field(section, "Document Type") or "Invoice"
    endpoint = (
        _extract_field(section, "Endpoint")
        or "https://du.uipath.com/document/invoices"
    )
    api_key_asset = _extract_field(section, "API Key Asset") or "DUApiKey"

    threshold_str = _extract_field(section, "Confidence Threshold") or "0.8"
    try:
        confidence_threshold = float(threshold_str)
    except (ValueError, TypeError):
        confidence_threshold = 0.8

    fields_str = _extract_field(section, "Fields") or ""
    fields = [f.strip() for f in fields_str.split(",") if f.strip()]

    return DocumentUnderstandingSpec(
        enabled=True,
        document_type=document_type,
        extraction_endpoint=endpoint,
        api_key_asset=api_key_asset,
        confidence_threshold=confidence_threshold,
        fields=fields,
    )


_VALID_BR_OUTCOMES = {
    "business_exception",
    "system_exception",
    "skip",
    "retry",
    "route",
    "escalate",
}


def _extract_business_rules(content: str) -> list[BusinessRule]:
    """Extract a list of :class:`BusinessRule` from the ``## Business Rules`` table."""
    section = _extract_section(content, "Business Rules")
    if not section:
        return []

    table_text = _find_table_in_text(section)
    rules: list[BusinessRule] = []
    for row in _parse_markdown_table(table_text):
        rule_id = row.get("ID", "").strip()
        if not rule_id:
            continue
        outcome = row.get("Outcome", "").strip().lower()
        if outcome not in _VALID_BR_OUTCOMES:
            outcome = "business_exception"

        # Parse parameters as a JSON-ish dict if possible.
        params_text = row.get("Parameters", "").strip()
        params: dict[str, Any] = {}
        if params_text and params_text != "{}":
            try:
                import json

                params = json.loads(params_text)
            except (json.JSONDecodeError, ValueError):
                params = {"raw": params_text}

        rules.append(
            BusinessRule(
                id=rule_id,
                condition=row.get("Condition", "").strip(),
                outcome=outcome,  # type: ignore[arg-type]
                reason=row.get("Reason", "").strip() or None,
                parameters=params,
            )
        )
    return rules


def _extract_field(text: str, field_name: str) -> str:
    """Extract a field value like '- **Name:** value' or 'Name: value'."""
    # Try bold markdown format first: **Name:** value
    pattern = rf"\*\*{re.escape(field_name)}:\*\*\s*(.+)"
    match = re.search(pattern, text, re.IGNORECASE)
    if match:
        return match.group(1).strip()
    # Try plain format: Name: value
    pattern = rf"^[-*]?\s*{re.escape(field_name)}:\s*(.+)"
    match = re.search(pattern, text, re.IGNORECASE | re.MULTILINE)
    if match:
        return match.group(1).strip()
    return ""


# ---------------------------------------------------------------------------
# PDF/DOCX delegation (requires LLM)
# ---------------------------------------------------------------------------

def _parse_with_llm(path: Path, ext: str) -> ProcessIR:
    """Delegate to existing parsers for binary PDD formats."""
    if ext == ".pdf":
        from rpa_architect.parser.pdf_parser import PdfParser
        parser = PdfParser()
    elif ext == ".docx":
        from rpa_architect.parser.docx_parser import DocxParser
        parser = DocxParser()
    else:
        raise ValueError(f"Unsupported format: {ext}")

    pdd_content = parser.parse(path)

    from rpa_architect.parser.llm_extractor import extract_ir
    return extract_ir(pdd_content)
