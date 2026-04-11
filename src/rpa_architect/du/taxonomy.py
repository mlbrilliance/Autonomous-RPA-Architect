"""Pydantic models for UiPath Document Understanding taxonomies.

These mirror the structure of UiPath's IXP ``taxonomy.json`` schema while
remaining easy to construct programmatically. The :func:`serialize_taxonomy`
function in :mod:`rpa_architect.du.taxonomy_gen` converts these to the
on-disk JSON format consumed by the IntelligentOCR activities.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

FieldType = Literal["string", "date", "number", "currency", "table", "boolean"]


class TableColumn(BaseModel):
    """A column inside a table-typed extraction field."""

    name: str = Field(description="Column name as it appears in the extracted dataset.")
    column_type: FieldType = Field(
        default="string",
        description="Column data type.",
    )


class ExtractionField(BaseModel):
    """A single field to extract from a document."""

    model_config = ConfigDict(frozen=False)

    name: str = Field(description="Field name (used as key in the extracted dictionary).")
    field_type: FieldType = Field(
        default="string",
        description="Data type of the extracted value.",
    )
    required: bool = Field(default=True, description="Whether the field is required.")
    description: str | None = Field(
        default=None, description="Human-readable description shown in the validation station."
    )
    columns: list[TableColumn] = Field(
        default_factory=list,
        description="Columns for table-typed fields. Empty for scalar fields.",
    )


class DocumentType(BaseModel):
    """A document content type (e.g., Invoice, Receipt, PurchaseOrder)."""

    name: str = Field(description="Display name of the document type.")
    document_type_id: str | None = Field(
        default=None,
        description="Stable identifier (e.g., 'uipath.invoice'). Defaults to a slug of the name.",
    )
    fields: list[ExtractionField] = Field(
        default_factory=list,
        description="Extraction fields belonging to this document type.",
    )


class DocumentTaxonomy(BaseModel):
    """A complete taxonomy describing one or more document types."""

    document_types: list[DocumentType] = Field(default_factory=list)


def build_invoice_taxonomy() -> DocumentTaxonomy:
    """Return the canonical Invoice taxonomy matching the public DU model.

    The fields here mirror the schema returned by ``du.uipath.com``'s
    pre-trained ``invoices`` model, so the same taxonomy can be used both
    for offline validation and live extraction calls.
    """
    invoice = DocumentType(
        name="Invoice",
        document_type_id="uipath.invoice",
        fields=[
            ExtractionField(
                name="VendorName",
                field_type="string",
                description="Legal name of the supplier issuing the invoice.",
            ),
            ExtractionField(
                name="InvoiceNumber",
                field_type="string",
                description="Vendor-assigned invoice identifier.",
            ),
            ExtractionField(
                name="InvoiceDate",
                field_type="date",
                description="Date the invoice was issued.",
            ),
            ExtractionField(
                name="TotalAmount",
                field_type="number",
                description="Total amount due (including taxes).",
            ),
            ExtractionField(
                name="Currency",
                field_type="string",
                description="ISO-4217 currency code (USD, EUR, GBP, ...).",
            ),
            ExtractionField(
                name="LineItems",
                field_type="table",
                description="Itemized line items.",
                columns=[
                    TableColumn(name="Description", column_type="string"),
                    TableColumn(name="Quantity", column_type="number"),
                    TableColumn(name="UnitPrice", column_type="number"),
                    TableColumn(name="LineTotal", column_type="number"),
                ],
            ),
        ],
    )
    return DocumentTaxonomy(document_types=[invoice])
