"""Serialize a :class:`DocumentTaxonomy` to UiPath IXP ``taxonomy.json``.

The on-disk format uses PascalCase keys and capitalised type names
(``Text``, ``Date``, ``Number``, ``Table``) so the output can be loaded
directly by ``UiPath.IntelligentOCR.Activities`` at runtime.
"""

from __future__ import annotations

import json
import re
from typing import Any

from rpa_architect.du.taxonomy import (
    DocumentTaxonomy,
    DocumentType,
    ExtractionField,
    TableColumn,
)

_TYPE_MAP: dict[str, str] = {
    "string": "Text",
    "date": "Date",
    "number": "Number",
    "currency": "Number",
    "table": "Table",
    "boolean": "Boolean",
}


def _ixp_type(field_type: str) -> str:
    return _TYPE_MAP.get(field_type, "Text")


def _slug(name: str) -> str:
    return re.sub(r"[^A-Za-z0-9_]+", "_", name).strip("_").lower()


def _column_to_dict(col: TableColumn) -> dict[str, Any]:
    return {
        "ColumnName": col.name,
        "ColumnType": _ixp_type(col.column_type),
    }


def _field_to_dict(field: ExtractionField) -> dict[str, Any]:
    out: dict[str, Any] = {
        "FieldName": field.name,
        "FieldType": _ixp_type(field.field_type),
        "MultiValue": field.field_type == "table",
        "Required": field.required,
    }
    if field.description:
        out["Description"] = field.description
    if field.field_type == "table":
        out["Columns"] = [_column_to_dict(c) for c in field.columns]
    return out


def _document_type_to_dict(dt: DocumentType) -> dict[str, Any]:
    return {
        "Name": dt.name,
        "DocumentTypeId": dt.document_type_id or f"uipath.{_slug(dt.name)}",
        "Fields": [_field_to_dict(f) for f in dt.fields],
    }


def serialize_taxonomy(taxonomy: DocumentTaxonomy, indent: int = 2) -> str:
    """Convert a :class:`DocumentTaxonomy` to an IXP-compatible JSON string."""
    payload = {
        "DocumentTypes": [_document_type_to_dict(dt) for dt in taxonomy.document_types],
    }
    return json.dumps(payload, indent=indent, ensure_ascii=False)
