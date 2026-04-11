"""Tests for Document Understanding taxonomy JSON serialization."""

from __future__ import annotations

import json

from rpa_architect.du.taxonomy import build_invoice_taxonomy
from rpa_architect.du.taxonomy_gen import serialize_taxonomy


def test_serialize_taxonomy_returns_valid_json() -> None:
    tax = build_invoice_taxonomy()
    out = serialize_taxonomy(tax)
    # Must be valid JSON.
    parsed = json.loads(out)
    assert isinstance(parsed, dict)


def test_serialize_taxonomy_has_documenttypes_key() -> None:
    tax = build_invoice_taxonomy()
    parsed = json.loads(serialize_taxonomy(tax))
    assert "DocumentTypes" in parsed
    assert isinstance(parsed["DocumentTypes"], list)
    assert len(parsed["DocumentTypes"]) >= 1


def test_serialize_taxonomy_invoice_uses_pascalcase_field_keys() -> None:
    """The IXP taxonomy.json schema expects PascalCase keys."""
    tax = build_invoice_taxonomy()
    parsed = json.loads(serialize_taxonomy(tax))
    invoice = parsed["DocumentTypes"][0]
    assert invoice["Name"] == "Invoice"
    assert "Fields" in invoice
    field = invoice["Fields"][0]
    assert "FieldName" in field
    assert "FieldType" in field


def test_serialize_taxonomy_includes_invoice_field_names() -> None:
    tax = build_invoice_taxonomy()
    parsed = json.loads(serialize_taxonomy(tax))
    invoice = parsed["DocumentTypes"][0]
    field_names = {f["FieldName"] for f in invoice["Fields"]}
    assert "VendorName" in field_names
    assert "InvoiceNumber" in field_names
    assert "TotalAmount" in field_names
    assert "LineItems" in field_names


def test_serialize_taxonomy_lineitems_is_table_with_columns() -> None:
    tax = build_invoice_taxonomy()
    parsed = json.loads(serialize_taxonomy(tax))
    invoice = parsed["DocumentTypes"][0]
    line_items = next(f for f in invoice["Fields"] if f["FieldName"] == "LineItems")
    assert line_items["FieldType"] == "Table"
    assert "Columns" in line_items
    assert len(line_items["Columns"]) > 0
    col = line_items["Columns"][0]
    assert "ColumnName" in col


def test_serialize_taxonomy_invoicedate_field_type_is_date() -> None:
    tax = build_invoice_taxonomy()
    parsed = json.loads(serialize_taxonomy(tax))
    invoice = parsed["DocumentTypes"][0]
    field = next(f for f in invoice["Fields"] if f["FieldName"] == "InvoiceDate")
    assert field["FieldType"] == "Date"
