"""Tests for Document Understanding XAML activity generators."""

from __future__ import annotations

import xml.etree.ElementTree as ET

from rpa_architect.du.activity_gen import (
    generate_digitize_activity,
    generate_export_activity,
    generate_extract_activity,
    generate_validation_station_activity,
)


def _wrap(xml_fragment: str) -> ET.Element:
    """Wrap a fragment in a root element so it can be parsed."""
    wrapped = (
        '<root xmlns:ui="http://schemas.uipath.com/workflow/activities"'
        ' xmlns:uidu="http://schemas.uipath.com/workflow/activities/intelligentocr"'
        ' xmlns:x="http://schemas.microsoft.com/winfx/2006/xaml">'
        f"{xml_fragment}"
        "</root>"
    )
    return ET.fromstring(wrapped)


def test_digitize_activity_is_valid_xml_fragment() -> None:
    xml = generate_digitize_activity(
        in_document_path="in_DocumentPath",
        out_dom="documentObjectModel",
        out_text="documentText",
    )
    root = _wrap(xml)
    assert root is not None
    assert len(list(root)) >= 1


def test_digitize_activity_references_input_document_path_var() -> None:
    xml = generate_digitize_activity(
        in_document_path="in_DocumentPath",
        out_dom="documentObjectModel",
        out_text="documentText",
    )
    assert "in_DocumentPath" in xml


def test_digitize_activity_writes_dom_and_text_outputs() -> None:
    xml = generate_digitize_activity(
        in_document_path="in_DocumentPath",
        out_dom="documentObjectModel",
        out_text="documentText",
    )
    assert "documentObjectModel" in xml
    assert "documentText" in xml


def test_extract_activity_targets_public_du_endpoint() -> None:
    xml = generate_extract_activity(
        endpoint_url="https://du.uipath.com/document/invoices",
        api_key_asset="DUApiKey",
        in_dom="documentObjectModel",
        in_text="documentText",
        in_taxonomy_path="DocumentProcessing/taxonomy.json",
        out_results="extractionResults",
    )
    assert "du.uipath.com" in xml
    assert "extractionResults" in xml


def test_extract_activity_uses_taxonomy_path() -> None:
    xml = generate_extract_activity(
        endpoint_url="https://du.uipath.com/document/invoices",
        api_key_asset="DUApiKey",
        in_dom="documentObjectModel",
        in_text="documentText",
        in_taxonomy_path="DocumentProcessing/taxonomy.json",
        out_results="extractionResults",
    )
    assert "taxonomy.json" in xml


def test_validation_station_activity_writes_validated_results() -> None:
    xml = generate_validation_station_activity(
        in_results="extractionResults",
        out_results="validatedResults",
    )
    assert "extractionResults" in xml
    assert "validatedResults" in xml


def test_export_activity_writes_dataset_output() -> None:
    xml = generate_export_activity(
        in_results="validatedResults",
        out_dataset="extractedDataSet",
    )
    assert "extractedDataSet" in xml
