"""Tests for Document Understanding taxonomy models."""

from __future__ import annotations

from rpa_architect.du.taxonomy import (
    DocumentTaxonomy,
    DocumentType,
    ExtractionField,
    build_invoice_taxonomy,
)


def test_extraction_field_defaults_required_true() -> None:
    field = ExtractionField(name="VendorName", field_type="string")
    assert field.required is True


def test_document_type_can_have_fields() -> None:
    dt = DocumentType(
        name="Invoice",
        fields=[
            ExtractionField(name="Total", field_type="number"),
        ],
    )
    assert dt.name == "Invoice"
    assert len(dt.fields) == 1


def test_invoice_taxonomy_returns_taxonomy_with_invoice_doctype() -> None:
    tax = build_invoice_taxonomy()
    assert isinstance(tax, DocumentTaxonomy)
    assert len(tax.document_types) == 1
    assert tax.document_types[0].name == "Invoice"


def test_invoice_taxonomy_has_required_fields() -> None:
    tax = build_invoice_taxonomy()
    invoice_dt = tax.document_types[0]
    field_names = {f.name for f in invoice_dt.fields}
    expected = {
        "VendorName",
        "InvoiceNumber",
        "InvoiceDate",
        "TotalAmount",
        "Currency",
        "LineItems",
    }
    assert expected.issubset(field_names)


def test_invoice_taxonomy_lineitems_is_table_type() -> None:
    tax = build_invoice_taxonomy()
    line_items = next(f for f in tax.document_types[0].fields if f.name == "LineItems")
    assert line_items.field_type == "table"


def test_invoice_taxonomy_invoicedate_is_date_type() -> None:
    tax = build_invoice_taxonomy()
    field = next(f for f in tax.document_types[0].fields if f.name == "InvoiceDate")
    assert field.field_type == "date"


def test_invoice_taxonomy_totalamount_is_number_type() -> None:
    tax = build_invoice_taxonomy()
    field = next(f for f in tax.document_types[0].fields if f.name == "TotalAmount")
    assert field.field_type == "number"
