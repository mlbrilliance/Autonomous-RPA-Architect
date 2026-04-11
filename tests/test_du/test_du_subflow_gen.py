"""Tests for the DocumentUnderstandingFlow.xaml subflow generator."""

from __future__ import annotations

import xml.etree.ElementTree as ET

from rpa_architect.du.du_subflow_gen import generate_du_subflow_xaml


def _make_xaml() -> str:
    return generate_du_subflow_xaml(
        document_type="Invoice",
        extraction_endpoint="https://du.uipath.com/document/invoices",
        api_key_asset="DUApiKey",
    )


def test_subflow_is_well_formed_xml() -> None:
    xaml = _make_xaml()
    root = ET.fromstring(xaml)
    assert root is not None


def test_subflow_declares_in_document_path_argument() -> None:
    xaml = _make_xaml()
    assert "in_DocumentPath" in xaml


def test_subflow_declares_out_extracted_fields_argument() -> None:
    xaml = _make_xaml()
    assert "out_ExtractedFields" in xaml


def test_subflow_declares_out_confidence_argument() -> None:
    xaml = _make_xaml()
    assert "out_Confidence" in xaml


def test_subflow_chains_activities_in_correct_order() -> None:
    """Digitize must precede Extract which must precede Export."""
    xaml = _make_xaml()
    digitize_pos = xaml.find("DigitizeDocument")
    extract_pos = xaml.find("MachineLearningExtractor")
    validate_pos = xaml.find("PresentValidationStation")
    export_pos = xaml.find("ExportExtractionResults")
    assert digitize_pos >= 0, "no DigitizeDocument activity"
    assert extract_pos >= 0, "no MachineLearningExtractor activity"
    assert validate_pos >= 0, "no PresentValidationStation activity"
    assert export_pos >= 0, "no ExportExtractionResults activity"
    assert digitize_pos < extract_pos, "Digitize must come before Extract"
    assert extract_pos < validate_pos, "Extract must come before Validate"
    assert validate_pos < export_pos, "Validate must come before Export"


def test_subflow_references_extraction_endpoint() -> None:
    xaml = _make_xaml()
    assert "du.uipath.com" in xaml


def test_subflow_references_taxonomy_json() -> None:
    xaml = _make_xaml()
    assert "taxonomy.json" in xaml
