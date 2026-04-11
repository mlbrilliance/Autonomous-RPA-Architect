"""UiPath Document Understanding (IXP) generation module.

Generates taxonomy.json, activity XAML fragments, and the
DocumentUnderstandingFlow.xaml subflow for invoice extraction
via the public ``du.uipath.com`` endpoint.
"""

from rpa_architect.du.activity_gen import (
    generate_digitize_activity,
    generate_export_activity,
    generate_extract_activity,
    generate_validation_station_activity,
)
from rpa_architect.du.du_subflow_gen import generate_du_subflow_xaml
from rpa_architect.du.taxonomy import (
    DocumentTaxonomy,
    DocumentType,
    ExtractionField,
    build_invoice_taxonomy,
)
from rpa_architect.du.taxonomy_gen import serialize_taxonomy

__all__ = [
    "DocumentTaxonomy",
    "DocumentType",
    "ExtractionField",
    "build_invoice_taxonomy",
    "serialize_taxonomy",
    "generate_digitize_activity",
    "generate_extract_activity",
    "generate_validation_station_activity",
    "generate_export_activity",
    "generate_du_subflow_xaml",
]
