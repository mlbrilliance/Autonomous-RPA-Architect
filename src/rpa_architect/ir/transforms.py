"""IR transformation utilities.

Provides normalization and enrichment passes that clean up and augment
the raw ProcessIR extracted from a PDD before code generation.
"""

from __future__ import annotations

import re
from copy import deepcopy

from rpa_architect.ir.schema import (
    ProcessIR,
    Step,
    SystemInfo,
)


def _to_pascal_case(name: str) -> str:
    """Convert a string to PascalCase.

    Handles snake_case, kebab-case, space-separated, and already-PascalCase strings.

    >>> _to_pascal_case("process_invoice")
    'ProcessInvoice'
    >>> _to_pascal_case("get-text-from-field")
    'GetTextFromField'
    >>> _to_pascal_case("already PascalCase")
    'AlreadyPascalCase'
    """
    # Split on underscores, hyphens, spaces, and camelCase boundaries
    tokens = re.split(r"[_\-\s]+", name)
    # Further split on camelCase boundaries within each token
    expanded: list[str] = []
    for token in tokens:
        parts = re.sub(r"([a-z])([A-Z])", r"\1 \2", token).split()
        expanded.extend(parts)
    return "".join(word.capitalize() for word in expanded if word)


def _ensure_step_ids(steps: list[Step], prefix: str = "S") -> list[Step]:
    """Ensure all steps have unique IDs, generating them if missing."""
    counter = 1
    existing_ids: set[str] = set()

    # First pass: collect existing IDs
    def _collect_ids(step_list: list[Step]) -> None:
        nonlocal existing_ids
        for step in step_list:
            if step.id:
                existing_ids.add(step.id)
            if step.substeps:
                _collect_ids(step.substeps)

    _collect_ids(steps)

    # Second pass: assign IDs where missing
    def _assign_ids(step_list: list[Step]) -> list[Step]:
        nonlocal counter
        result: list[Step] = []
        for step in step_list:
            step_data = step.model_dump()
            if not step_data["id"] or not step_data["id"].strip():
                while f"{prefix}{counter:03d}" in existing_ids:
                    counter += 1
                step_data["id"] = f"{prefix}{counter:03d}"
                existing_ids.add(step_data["id"])
                counter += 1
            if step_data["substeps"]:
                step_data["substeps"] = [
                    s.model_dump()
                    for s in _assign_ids(
                        [Step(**sub) for sub in step_data["substeps"]]
                    )
                ]
            result.append(Step(**step_data))
        return result

    return _assign_ids(steps)


def _deduplicate_systems(systems: list[SystemInfo]) -> list[SystemInfo]:
    """Remove duplicate systems, keeping the most complete entry for each name."""
    seen: dict[str, SystemInfo] = {}
    for system in systems:
        key = system.name.lower().strip()
        if key not in seen:
            seen[key] = system
        else:
            # Keep the entry with more information
            existing = seen[key]
            merged_data = existing.model_dump()
            new_data = system.model_dump()
            for field_name, value in new_data.items():
                if value and not merged_data.get(field_name):
                    merged_data[field_name] = value
            # Prefer login_required = True if either has it
            if system.login_required:
                merged_data["login_required"] = True
            seen[key] = SystemInfo(**merged_data)
    return list(seen.values())


def normalize_ir(ir: ProcessIR) -> ProcessIR:
    """Normalize an IR for consistency.

    Transformations applied:
    - Process name, transaction names, and system names converted to PascalCase.
    - All steps get unique IDs assigned if missing.
    - Duplicate systems are merged.

    Args:
        ir: The ProcessIR to normalize.

    Returns:
        A new, normalized ProcessIR instance.
    """
    data = deepcopy(ir.model_dump())

    # Normalize process name
    data["process_name"] = _to_pascal_case(data["process_name"])

    # Normalize and deduplicate systems
    systems = [SystemInfo(**s) for s in data.get("systems", [])]
    for system in systems:
        system_data = system.model_dump()
        system_data["name"] = _to_pascal_case(system_data["name"])
        systems[systems.index(system)] = SystemInfo(**system_data)
    deduped = _deduplicate_systems(systems)
    data["systems"] = [s.model_dump() for s in deduped]

    # Build old-name -> new-name mapping for system refs
    original_systems = [SystemInfo(**s) for s in ir.model_dump().get("systems", [])]
    name_map: dict[str, str] = {}
    for orig in original_systems:
        pascal = _to_pascal_case(orig.name)
        name_map[orig.name] = pascal

    # Normalize transactions
    for txn_data in data.get("transactions", []):
        txn_data["name"] = _to_pascal_case(txn_data["name"])

        # Ensure step IDs and normalize system refs
        steps = [Step(**s) for s in txn_data.get("steps", [])]
        steps = _ensure_step_ids(steps)

        def _update_system_refs(step_list: list[Step]) -> list[Step]:
            result = []
            for step in step_list:
                step_data = step.model_dump()
                if step_data.get("system_ref") and step_data["system_ref"] in name_map:
                    step_data["system_ref"] = name_map[step_data["system_ref"]]
                if step_data["substeps"]:
                    step_data["substeps"] = [
                        s.model_dump()
                        for s in _update_system_refs(
                            [Step(**sub) for sub in step_data["substeps"]]
                        )
                    ]
                result.append(Step(**step_data))
            return result

        steps = _update_system_refs(steps)
        txn_data["steps"] = [s.model_dump() for s in steps]

    # Normalize credential names
    for cred_data in data.get("credentials", []):
        cred_data["name"] = _to_pascal_case(cred_data["name"])

    # Normalize exception category names
    for exc_data in data.get("exception_categories", []):
        exc_data["name"] = _to_pascal_case(exc_data["name"])

    return ProcessIR(**data)


def enrich_ir(ir: ProcessIR) -> ProcessIR:
    """Enrich an IR with inferred defaults and missing information.

    Transformations applied:
    - Infer missing exception categories from business rules.
    - Add default ReFramework config entries if not present.
    - Infer credential types from context (login steps -> credential, data refs -> asset).

    Args:
        ir: The ProcessIR to enrich.

    Returns:
        A new, enriched ProcessIR instance.
    """
    data = deepcopy(ir.model_dump())

    # --- Infer exception categories from business rules ---
    existing_exc_names = {exc["name"].lower() for exc in data.get("exception_categories", [])}

    for txn_data in data.get("transactions", []):
        for rule_data in txn_data.get("business_rules", []):
            outcome = rule_data.get("outcome", "")
            if outcome == "business_exception":
                # Derive category name from the rule condition
                cat_name = _to_pascal_case(rule_data.get("id", "BusinessException"))
                if cat_name.lower() not in existing_exc_names:
                    data.setdefault("exception_categories", []).append(
                        {
                            "name": cat_name,
                            "type": "business",
                            "retry_count": 0,
                            "description": rule_data.get("reason", rule_data.get("condition", "")),
                        }
                    )
                    existing_exc_names.add(cat_name.lower())
            elif outcome == "system_exception":
                cat_name = _to_pascal_case(rule_data.get("id", "SystemException"))
                if cat_name.lower() not in existing_exc_names:
                    retry_count = rule_data.get("parameters", {}).get("retry_count", 3)
                    data.setdefault("exception_categories", []).append(
                        {
                            "name": cat_name,
                            "type": "system",
                            "retry_count": int(retry_count),
                            "description": rule_data.get("reason", rule_data.get("condition", "")),
                        }
                    )
                    existing_exc_names.add(cat_name.lower())

    # Ensure base exception categories exist
    for base_cat in [
        {"name": "BusinessRuleException", "type": "business", "retry_count": 0,
         "description": "General business rule violation."},
        {"name": "SystemException", "type": "system", "retry_count": 3,
         "description": "General system/application error."},
    ]:
        if base_cat["name"].lower() not in existing_exc_names:
            data.setdefault("exception_categories", []).append(base_cat)
            existing_exc_names.add(base_cat["name"].lower())

    # --- Add default ReFramework config entries ---
    default_config = {
        "MaxRetryNumber": "3",
        "LogLevel": "Info",
        "OrchestratorQueueName": "",
        "OrchestratorQueueFolder": "",
        "REFrameworkVersion": "2.0",
    }
    config = data.get("config", {})
    for key, default_val in default_config.items():
        if key not in config:
            config[key] = default_val
    data["config"] = config

    # --- Infer credential types ---
    systems_with_login = {s["name"] for s in data.get("systems", []) if s.get("login_required")}
    credentials = data.get("credentials", [])

    # Check if any systems need login but have no credential
    credential_names = {c["name"].lower() for c in credentials}
    for system_name in systems_with_login:
        # Look for an existing credential that might match
        possible_name = f"{system_name}_Cred"
        if possible_name.lower() not in credential_names:
            # Check if any credential description mentions this system
            found = False
            for cred in credentials:
                desc = (cred.get("description") or "").lower()
                if system_name.lower() in desc:
                    found = True
                    break
            if not found:
                credentials.append(
                    {
                        "name": possible_name,
                        "type": "credential",
                        "orchestrator_path": None,
                        "description": f"Auto-inferred credential for {system_name} login.",
                    }
                )
                credential_names.add(possible_name.lower())

    # Infer types for credentials that might be assets or queues based on naming
    for cred in credentials:
        name_lower = cred["name"].lower()
        if cred["type"] == "credential":
            # If the name suggests it's a queue
            if "queue" in name_lower:
                cred["type"] = "queue"
            # If the name suggests it's an asset (config value, not a login)
            elif any(kw in name_lower for kw in ("config", "setting", "url", "path", "threshold", "flag")):
                cred["type"] = "asset"

    data["credentials"] = credentials

    return ProcessIR(**data)
