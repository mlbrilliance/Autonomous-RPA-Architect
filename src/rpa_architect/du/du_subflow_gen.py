"""Generator for ``Framework/DocumentUnderstandingFlow.xaml``.

Composes the DigitizeDocument → MachineLearningExtractor → PresentValidationStation
→ ExportExtractionResults activity chain into a single, invokable workflow with
arguments ``in_DocumentPath`` (String), ``out_ExtractedFields``
(``Dictionary<String, Object>``), and ``out_Confidence`` (Double).
"""

from __future__ import annotations

from rpa_architect.du.activity_gen import (
    generate_digitize_activity,
    generate_export_activity,
    generate_extract_activity,
    generate_validation_station_activity,
)

_TAXONOMY_PATH = "DocumentProcessing/taxonomy.json"


def generate_du_subflow_xaml(
    document_type: str = "Invoice",
    extraction_endpoint: str = "https://du.uipath.com/document/invoices",
    api_key_asset: str = "DUApiKey",
    taxonomy_path: str = _TAXONOMY_PATH,
) -> str:
    """Generate the complete ``DocumentUnderstandingFlow.xaml`` content."""
    digitize = generate_digitize_activity(
        in_document_path="in_DocumentPath",
        out_dom="documentObjectModel",
        out_text="documentText",
    )
    extract = generate_extract_activity(
        endpoint_url=extraction_endpoint,
        api_key_asset=api_key_asset,
        in_dom="documentObjectModel",
        in_text="documentText",
        in_taxonomy_path=taxonomy_path,
        out_results="extractionResults",
    )
    validate = generate_validation_station_activity(
        in_results="extractionResults",
        out_results="validatedResults",
    )
    export = generate_export_activity(
        in_results="validatedResults",
        out_dataset="extractedDataSet",
    )

    return (
        '<?xml version="1.0" encoding="utf-8"?>\n'
        '<Activity'
        ' x:Class="DocumentUnderstandingFlow"'
        ' xmlns="http://schemas.microsoft.com/netfx/2009/xaml/activities"'
        ' xmlns:mc="http://schemas.openxmlformats.org/markup-compatibility/2006"'
        ' xmlns:sap2010="http://schemas.microsoft.com/netfx/2010/xaml/activities/presentation"'
        ' xmlns:scg="clr-namespace:System.Collections.Generic;assembly=mscorlib"'
        ' xmlns:sys="clr-namespace:System;assembly=mscorlib"'
        ' xmlns:ui="http://schemas.uipath.com/workflow/activities"'
        ' xmlns:uidu="http://schemas.uipath.com/workflow/activities/intelligentocr"'
        ' xmlns:x="http://schemas.microsoft.com/winfx/2006/xaml">\n'
        '  <x:Members>\n'
        '    <x:Property Name="in_DocumentPath" Type="InArgument(x:String)" />\n'
        '    <x:Property Name="out_ExtractedFields"'
        ' Type="OutArgument(scg:Dictionary(x:String, x:Object))" />\n'
        '    <x:Property Name="out_Confidence" Type="OutArgument(x:Double)" />\n'
        '  </x:Members>\n'
        f'  <Sequence DisplayName="Document Understanding ({document_type})">\n'
        '    <Sequence.Variables>\n'
        '      <Variable x:TypeArguments="x:Object" Name="documentObjectModel" />\n'
        '      <Variable x:TypeArguments="x:String" Name="documentText" />\n'
        '      <Variable x:TypeArguments="x:Object" Name="extractionResults" />\n'
        '      <Variable x:TypeArguments="x:Object" Name="validatedResults" />\n'
        '      <Variable x:TypeArguments="x:Object" Name="extractedDataSet" />\n'
        '    </Sequence.Variables>\n'
        f'    {digitize}\n'
        f'    {extract}\n'
        f'    {validate}\n'
        f'    {export}\n'
        '    <ui:LogMessage DisplayName="Log Document Understanding Complete"'
        ' Level="Info"'
        f' Message="[&quot;Document Understanding for {document_type} complete&quot;]" />\n'
        '  </Sequence>\n'
        '</Activity>\n'
    )
