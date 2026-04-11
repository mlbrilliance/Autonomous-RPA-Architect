"""Test data generation based on DataContract definitions.

Generates valid, invalid, and edge-case test data sets that can be used
to populate Orchestrator queues or test harnesses.
"""

from __future__ import annotations

import random
from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field

from rpa_architect.ir.schema import DataContract, DataField


class TestDataSet(BaseModel):
    """A named set of test data for a specific scenario."""

    name: str = Field(description="Test data set name.")
    data: list[dict[str, Any]] = Field(
        default_factory=list,
        description="List of data records (each is a field_name -> value dict).",
    )
    scenario: str = Field(
        default="valid",
        description="Scenario type: valid, invalid, edge_case, boundary.",
    )


def _generate_valid_value(field: DataField) -> Any:
    """Generate a valid value for a data field based on its type."""
    field_type = field.type.lower()
    name_lower = field.name.lower()

    # Infer from field name for common patterns
    if "email" in name_lower:
        return "test.user@example.com"
    if "phone" in name_lower or "tel" in name_lower:
        return "+1-555-0100"
    if "date" in name_lower or field_type in ("datetime", "date"):
        return datetime.now().strftime("%Y-%m-%d")
    if "url" in name_lower:
        return "https://example.com/resource"
    if "amount" in name_lower or "price" in name_lower or "cost" in name_lower:
        return round(random.uniform(10.0, 10000.0), 2)

    # Type-based generation
    if field_type in ("string", "str"):
        return f"Test_{field.name}_Value"
    if field_type in ("int32", "int", "integer", "int64"):
        return random.randint(1, 9999)
    if field_type in ("decimal", "double", "float"):
        return round(random.uniform(1.0, 9999.99), 2)
    if field_type in ("boolean", "bool"):
        return True
    if field_type in ("datatable", "list", "array"):
        return []

    # Default to string
    return f"Test_{field.name}"


def _generate_invalid_value(field: DataField) -> Any:
    """Generate an invalid value for a data field."""
    field_type = field.type.lower()
    name_lower = field.name.lower()

    if "email" in name_lower:
        return "not-an-email"
    if "phone" in name_lower or "tel" in name_lower:
        return "abc-not-a-phone"
    if "date" in name_lower or field_type in ("datetime", "date"):
        return "not-a-date"

    if field_type in ("int32", "int", "integer", "int64"):
        return "not_a_number"
    if field_type in ("decimal", "double", "float"):
        return "NaN_string"
    if field_type in ("boolean", "bool"):
        return "maybe"

    # For strings, use excessively long value
    return "X" * 5000


def _generate_edge_value(field: DataField) -> Any:
    """Generate an edge-case value for a data field."""
    field_type = field.type.lower()
    name_lower = field.name.lower()

    if "email" in name_lower:
        return "a@b.c"
    if "phone" in name_lower or "tel" in name_lower:
        return "0"
    if "date" in name_lower or field_type in ("datetime", "date"):
        return "1900-01-01"

    if field_type in ("int32", "int", "integer", "int64"):
        return 0
    if field_type in ("decimal", "double", "float"):
        return 0.0
    if field_type in ("string", "str"):
        return ""
    if field_type in ("boolean", "bool"):
        return False

    return None


def _generate_boundary_value(field: DataField) -> Any:
    """Generate a boundary-condition value for a data field."""
    field_type = field.type.lower()

    if field_type in ("int32", "int", "integer"):
        return 2_147_483_647  # Int32.MaxValue
    if field_type in ("int64",):
        return 9_223_372_036_854_775_807
    if field_type in ("decimal", "double", "float"):
        return 99999999.99
    if field_type in ("string", "str"):
        # Max typical field length
        return "A" * 255
    if field_type in ("datetime", "date"):
        return "9999-12-31"

    return _generate_valid_value(field)


def generate_test_data(
    contract: DataContract,
    scenario: str = "valid",
    *,
    count: int = 3,
) -> dict[str, Any]:
    """Generate test data based on a DataContract definition.

    Produces a TestDataSet with multiple records appropriate for the
    requested scenario type.

    Args:
        contract: The DataContract defining expected fields and types.
        scenario: One of 'valid', 'invalid', 'edge_case', 'boundary'.
        count: Number of data records to generate.

    Returns:
        Dictionary representation of a TestDataSet with generated records.
    """
    records: list[dict[str, Any]] = []

    generator_map = {
        "valid": _generate_valid_value,
        "invalid": _generate_invalid_value,
        "edge_case": _generate_edge_value,
        "boundary": _generate_boundary_value,
    }

    generator = generator_map.get(scenario, _generate_valid_value)

    for i in range(count):
        record: dict[str, Any] = {}
        for field in contract.fields:
            if scenario == "invalid" and not field.required and i == 0:
                # For first invalid record, skip optional fields entirely
                continue
            record[field.name] = generator(field)
        records.append(record)

    # For invalid scenario, also add a record with missing required fields
    if scenario == "invalid" and contract.fields:
        missing_record: dict[str, Any] = {}
        for field in contract.fields:
            if not field.required:
                missing_record[field.name] = _generate_valid_value(field)
            # Intentionally skip required fields
        records.append(missing_record)

    dataset = TestDataSet(
        name=f"{scenario}_data",
        data=records,
        scenario=scenario,
    )

    return dataset.model_dump()
