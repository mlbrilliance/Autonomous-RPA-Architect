"""XAML fragment generators for UiPath Document Understanding activities.

Each function returns a stand-alone XAML element string that can be embedded
inside a Sequence in a ``Framework/DocumentUnderstandingFlow.xaml`` file.
The fragments use the ``uidu`` namespace prefix
(``http://schemas.uipath.com/workflow/activities/intelligentocr``).
"""

from __future__ import annotations


def generate_digitize_activity(
    in_document_path: str,
    out_dom: str,
    out_text: str,
) -> str:
    """Generate a ``DigitizeDocument`` activity fragment.

    Args:
        in_document_path: Name of the variable holding the document path.
        out_dom: Name of the variable to receive the DocumentObjectModel.
        out_text: Name of the variable to receive the extracted text.
    """
    return (
        '<uidu:DigitizeDocument'
        ' DisplayName="Digitize Document"'
        f' DocumentPath="[{in_document_path}]"'
        f' DocumentObjectModel="[{out_dom}]"'
        f' DocumentText="[{out_text}]"'
        ' />'
    )


def generate_extract_activity(
    endpoint_url: str,
    api_key_asset: str,
    in_dom: str,
    in_text: str,
    in_taxonomy_path: str,
    out_results: str,
) -> str:
    """Generate a ``MachineLearningExtractor`` activity fragment.

    Targets the public ``du.uipath.com`` endpoint by default. The API key
    is read at runtime from a UiPath Orchestrator asset named
    ``api_key_asset``.

    Args:
        endpoint_url: Full URL of the DU extraction endpoint.
        api_key_asset: Orchestrator asset name holding the DU API key.
        in_dom: Variable name of the DocumentObjectModel input.
        in_text: Variable name of the document text input.
        in_taxonomy_path: Path to ``DocumentProcessing/taxonomy.json``.
        out_results: Variable name to receive the extraction results.
    """
    return (
        '<uidu:MachineLearningExtractor'
        ' DisplayName="Extract Document Data"'
        f' Endpoint="{endpoint_url}"'
        f' ApiKeyAsset="{api_key_asset}"'
        f' TaxonomyFilePath="{in_taxonomy_path}"'
        f' DocumentObjectModel="[{in_dom}]"'
        f' DocumentText="[{in_text}]"'
        f' ExtractionResults="[{out_results}]"'
        ' />'
    )


def generate_validation_station_activity(
    in_results: str,
    out_results: str,
) -> str:
    """Generate a ``PresentValidationStation`` activity fragment.

    Hands the extraction results to a human in Action Center for review
    when confidence is below threshold. The validated results are written
    to ``out_results``.
    """
    return (
        '<uidu:PresentValidationStation'
        ' DisplayName="Present Validation Station"'
        f' ExtractionResults="[{in_results}]"'
        f' ValidatedResults="[{out_results}]"'
        ' />'
    )


def generate_export_activity(
    in_results: str,
    out_dataset: str,
) -> str:
    """Generate an ``ExportExtractionResults`` activity fragment.

    Converts the validated extraction results into a typed dataset that
    can be consumed by the rest of the workflow.
    """
    return (
        '<uidu:ExportExtractionResults'
        ' DisplayName="Export Extraction Results"'
        f' ExtractionResults="[{in_results}]"'
        f' Dataset="[{out_dataset}]"'
        ' />'
    )
