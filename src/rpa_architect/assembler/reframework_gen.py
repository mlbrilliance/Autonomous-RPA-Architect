"""REFramework XAML generation for UiPath projects.

Generates the full set of REFramework workflow files (Main.xaml,
InitAllSettings.xaml, Process.xaml, etc.) using Jinja2 templates
or built-in defaults.
"""

from __future__ import annotations

import logging
from typing import Any, Protocol, runtime_checkable

from rpa_architect.du.du_subflow_gen import generate_du_subflow_xaml
from rpa_architect.ir.schema import ProcessIR

logger = logging.getLogger(__name__)

# REFramework file names (always generated)
REFRAMEWORK_FILES = [
    "Main.xaml",
    "Framework/InitAllSettings.xaml",
    "Framework/InitAllApplications.xaml",
    "Framework/GetTransactionData.xaml",
    "Framework/Process.xaml",
    "Framework/SetTransactionStatus.xaml",
    "Framework/EndProcess.xaml",
    "Framework/CloseAllApplications.xaml",
    "Framework/KillAllProcesses.xaml",
]

# Files generated only when ProcessIR.document_understanding is set.
DU_FILES = [
    "Framework/DocumentUnderstandingFlow.xaml",
]


@runtime_checkable
class TemplateEngine(Protocol):
    """Protocol for a Jinja2-compatible template engine."""

    def render(self, template_name: str, **context: Any) -> str: ...


def _default_xaml_header(display_name: str) -> str:
    """Generate a standard XAML activity header."""
    return (
        '<?xml version="1.0" encoding="utf-8"?>\n'
        '<Activity mc:Ignorable="sap sap2010 sads"'
        ' x:Class="Main"'
        ' xmlns="http://schemas.microsoft.com/netfx/2009/xaml/activities"'
        ' xmlns:mc="http://schemas.openxmlformats.org/markup-compatibility/2006"'
        ' xmlns:sap="http://schemas.microsoft.com/netfx/2009/xaml/activities/presentation"'
        ' xmlns:sap2010="http://schemas.microsoft.com/netfx/2010/xaml/activities/presentation"'
        ' xmlns:sads="http://schemas.microsoft.com/netfx/2010/xaml/activities/debugger"'
        ' xmlns:scg="clr-namespace:System.Collections.Generic;assembly=mscorlib"'
        ' xmlns:ui="http://schemas.uipath.com/workflow/activities"'
        ' xmlns:x="http://schemas.microsoft.com/winfx/2006/xaml">\n'
    )


def _default_xaml_footer() -> str:
    """Generate a standard XAML closing tag."""
    return "</Activity>\n"


def _generate_main_xaml(ir: ProcessIR) -> str:
    """Generate Main.xaml -- the REFramework state machine entry point."""
    return (
        f"{_default_xaml_header('Main')}"
        f'  <sap2010:WorkflowViewState.ViewStateManager>\n'
        f'    <sap2010:ViewStateManager />\n'
        f'  </sap2010:WorkflowViewState.ViewStateManager>\n'
        f'  <!-- REFramework State Machine for: {ir.process_name} -->\n'
        f'  <!-- States: Init, GetTransactionData, Process, EndProcess -->\n'
        f'  <StateMachine DisplayName="REFramework">\n'
        f'    <!-- Init State -->\n'
        f'    <State DisplayName="Init" />\n'
        f'    <!-- Get Transaction Data State -->\n'
        f'    <State DisplayName="Get Transaction Data" />\n'
        f'    <!-- Process Transaction State -->\n'
        f'    <State DisplayName="Process Transaction" />\n'
        f'    <!-- End Process State -->\n'
        f'    <State DisplayName="End Process" />\n'
        f'  </StateMachine>\n'
        f"{_default_xaml_footer()}"
    )


def _generate_init_all_settings(ir: ProcessIR) -> str:
    """Generate InitAllSettings.xaml."""
    config_path = ir.config.get("ExcelSettingsFilePath", "Data\\\\Config.xlsx")
    return (
        f"{_default_xaml_header('InitAllSettings')}"
        f'  <Sequence DisplayName="Init All Settings">\n'
        f'    <!-- Read Config.xlsx and populate config dictionary -->\n'
        f'    <!-- Config path: {config_path} -->\n'
        f'    <!-- Process: {ir.process_name} -->\n'
        f'    <ui:LogMessage DisplayName="Log Init Settings"'
        f' Level="Info"'
        f' Message="[&quot;Initializing settings for {ir.process_name}&quot;]" />\n'
        f'  </Sequence>\n'
        f"{_default_xaml_footer()}"
    )


def _generate_init_all_applications(ir: ProcessIR) -> str:
    """Generate InitAllApplications.xaml."""
    lines = [
        _default_xaml_header("InitAllApplications"),
        '  <Sequence DisplayName="Init All Applications">\n',
    ]

    for system in ir.systems:
        lines.append(
            f'    <!-- Open {system.name} ({system.type}) -->\n'
        )
        if system.login_required:
            cred_name = "TODO_CREDENTIAL"
            for cred in ir.credentials:
                if cred.type == "credential" and system.name.lower() in cred.name.lower():
                    cred_name = cred.name
                    break
            lines.append(
                f'    <!-- Login required. Credential: {cred_name} -->\n'
            )

    lines.append('  </Sequence>\n')
    lines.append(_default_xaml_footer())
    return "".join(lines)


def _generate_get_transaction_data(ir: ProcessIR) -> str:
    """Generate GetTransactionData.xaml."""
    queue_name = "TODO_QUEUE_NAME"
    for cred in ir.credentials:
        if cred.type == "queue":
            queue_name = cred.name
            break

    return (
        f"{_default_xaml_header('GetTransactionData')}"
        f'  <Sequence DisplayName="Get Transaction Data">\n'
        f'    <!-- Get transaction item from Orchestrator queue: {queue_name} -->\n'
        f'    <!-- Process type: {ir.process_type} -->\n'
        f'    <ui:LogMessage DisplayName="Log Get Transaction Data"'
        f' Level="Info"'
        f' Message="[&quot;Getting transaction data from {queue_name}&quot;]" />\n'
        f'  </Sequence>\n'
        f"{_default_xaml_footer()}"
    )


def _generate_process(ir: ProcessIR) -> str:
    """Generate Process.xaml -- the main transaction processing workflow."""
    lines = [
        _default_xaml_header("Process"),
        '  <Sequence DisplayName="Process Transaction">\n',
        f'    <!-- Process: {ir.process_name} -->\n',
    ]

    # Inject DocumentUnderstandingFlow invocation before business logic when DU is set.
    if ir.document_understanding is not None and ir.document_understanding.enabled:
        lines.append(
            '    <!-- Document Understanding subflow: extract structured fields from input PDF -->\n'
        )
        lines.append(
            '    <ui:InvokeWorkflowFile DisplayName="Invoke DocumentUnderstandingFlow"'
            ' WorkflowFileName="Framework\\DocumentUnderstandingFlow.xaml">\n'
        )
        lines.append('      <ui:InvokeWorkflowFile.Arguments>\n')
        lines.append(
            '        <InArgument x:Key="in_DocumentPath" x:TypeArguments="x:String">'
            '[in_TransactionItem.SpecificContent("DocumentPath").ToString()]</InArgument>\n'
        )
        lines.append(
            '        <OutArgument x:Key="out_ExtractedFields"'
            ' x:TypeArguments="scg:Dictionary(x:String, x:Object)">[ExtractedFields]</OutArgument>\n'
        )
        lines.append(
            '        <OutArgument x:Key="out_Confidence" x:TypeArguments="x:Double">'
            '[ExtractionConfidence]</OutArgument>\n'
        )
        lines.append('      </ui:InvokeWorkflowFile.Arguments>\n')
        lines.append('    </ui:InvokeWorkflowFile>\n')

    for transaction in ir.transactions:
        lines.append(
            f'    <!-- Transaction: {transaction.name} -->\n'
        )
        for step in transaction.steps:
            desc = step.description or step.type
            lines.append(
                f'    <!-- Step {step.id}: {desc} -->\n'
            )
            for action in step.actions:
                lines.append(
                    f'    <!-- Action: {action.action} on "{action.target}" -->\n'
                )

    lines.append('  </Sequence>\n')
    lines.append(_default_xaml_footer())
    return "".join(lines)


def _generate_document_understanding_flow(ir: ProcessIR) -> str:
    """Generate Framework/DocumentUnderstandingFlow.xaml from the DU spec."""
    spec = ir.document_understanding
    if spec is None:
        # Defensive: only called when caller has confirmed DU is enabled.
        return generate_du_subflow_xaml()
    return generate_du_subflow_xaml(
        document_type=spec.document_type,
        extraction_endpoint=spec.extraction_endpoint,
        api_key_asset=spec.api_key_asset,
    )


def _generate_set_transaction_status(ir: ProcessIR) -> str:
    """Generate SetTransactionStatus.xaml."""
    return (
        f"{_default_xaml_header('SetTransactionStatus')}"
        f'  <Sequence DisplayName="Set Transaction Status">\n'
        f'    <!-- Set Orchestrator queue item status -->\n'
        f'    <!-- Handle: Success, BusinessException, SystemException -->\n'
        f'    <ui:LogMessage DisplayName="Log Transaction Status"'
        f' Level="Info"'
        f' Message="[&quot;Setting transaction status&quot;]" />\n'
        f'  </Sequence>\n'
        f"{_default_xaml_footer()}"
    )


def _generate_end_process(ir: ProcessIR) -> str:
    """Generate EndProcess.xaml."""
    return (
        f"{_default_xaml_header('EndProcess')}"
        f'  <Sequence DisplayName="End Process">\n'
        f'    <!-- Final cleanup and summary logging -->\n'
        f'    <ui:LogMessage DisplayName="Log End Process"'
        f' Level="Info"'
        f' Message="[&quot;{ir.process_name} completed&quot;]" />\n'
        f'  </Sequence>\n'
        f"{_default_xaml_footer()}"
    )


def _generate_close_all_applications(ir: ProcessIR) -> str:
    """Generate CloseAllApplications.xaml."""
    lines = [
        _default_xaml_header("CloseAllApplications"),
        '  <Sequence DisplayName="Close All Applications">\n',
    ]

    for system in ir.systems:
        lines.append(
            f'    <!-- Close {system.name} ({system.type}) -->\n'
        )

    lines.append('  </Sequence>\n')
    lines.append(_default_xaml_footer())
    return "".join(lines)


def _generate_kill_all_processes(ir: ProcessIR) -> str:
    """Generate KillAllProcesses.xaml."""
    lines = [
        _default_xaml_header("KillAllProcesses"),
        '  <Sequence DisplayName="Kill All Processes">\n',
    ]

    # Add kill process activities for known application types
    app_executables: dict[str, str] = {
        "web": "chrome.exe",
        "excel": "EXCEL.EXE",
        "email": "OUTLOOK.EXE",
        "sap": "saplogon.exe",
    }

    for system in ir.systems:
        exe = app_executables.get(system.type, f"TODO_{system.name}.exe")
        lines.append(
            f'    <!-- Kill {system.name}: {exe} -->\n'
        )

    lines.append('  </Sequence>\n')
    lines.append(_default_xaml_footer())
    return "".join(lines)


# Map filenames to generator functions
_GENERATORS: dict[str, Any] = {
    "Main.xaml": _generate_main_xaml,
    "Framework/InitAllSettings.xaml": _generate_init_all_settings,
    "Framework/InitAllApplications.xaml": _generate_init_all_applications,
    "Framework/GetTransactionData.xaml": _generate_get_transaction_data,
    "Framework/Process.xaml": _generate_process,
    "Framework/SetTransactionStatus.xaml": _generate_set_transaction_status,
    "Framework/EndProcess.xaml": _generate_end_process,
    "Framework/CloseAllApplications.xaml": _generate_close_all_applications,
    "Framework/KillAllProcesses.xaml": _generate_kill_all_processes,
    "Framework/DocumentUnderstandingFlow.xaml": _generate_document_understanding_flow,
}


def generate_reframework_xaml(
    ir: ProcessIR,
    template_engine: TemplateEngine | None = None,
) -> dict[str, str]:
    """Generate all REFramework XAML workflow files.

    If a template_engine is provided, attempts to render each file from
    a Jinja2 template named ``{filename}.j2``. Falls back to built-in
    generators if the template is not found or no engine is provided.

    Args:
        ir: The ProcessIR describing the process.
        template_engine: Optional Jinja2-compatible template engine.
            If provided, will try to load templates named after each
            XAML file (e.g., ``Main.xaml.j2``).

    Returns:
        Dictionary mapping filename -> XAML content string.
    """
    results: dict[str, str] = {}

    # Derive template context variables from IR
    queue_name = ""
    for cred in ir.credentials:
        if cred.type == "queue":
            queue_name = cred.name
            break
    if not queue_name:
        queue_name = ir.config.get("OrchestratorQueueName", "")

    # Build workflow_names from transactions (for Process.xaml template)
    workflow_names = [t.name for t in ir.transactions]

    # Build process_names for KillAllProcesses template
    app_executables: dict[str, str] = {
        "web": "chrome",
        "excel": "EXCEL",
        "email": "OUTLOOK",
        "sap": "saplogon",
        "desktop": "notepad",
    }
    process_names = [
        app_executables.get(s.type, s.name) for s in ir.systems
    ]

    # Build the file list, conditionally including DU subflow.
    file_list = list(REFRAMEWORK_FILES)
    if ir.document_understanding is not None and ir.document_understanding.enabled:
        file_list.extend(DU_FILES)

    for filename in file_list:
        # Try template engine first
        if template_engine is not None:
            # Templates are flat files — strip directory prefix
            bare_name = filename.split("/")[-1]
            template_name = f"{bare_name}.j2"
            try:
                content = template_engine.render(
                    template_name,
                    ir=ir,
                    process_name=ir.process_name,
                    project_name=ir.process_name,
                    process_type=ir.process_type,
                    systems=ir.systems,
                    credentials=ir.credentials,
                    transactions=ir.transactions,
                    config=ir.config,
                    exception_categories=ir.exception_categories,
                    max_retries=ir.config.get("MaxRetryNumber", 3),
                    queue_name=queue_name,
                    transaction_fields=[],
                    workflow_names=workflow_names,
                    process_names=process_names,
                    send_notification=False,
                )
                results[filename] = content
                logger.debug("Rendered %s from template %s.", filename, template_name)
                continue
            except Exception as exc:
                logger.debug(
                    "Template '%s' not available (%s); using built-in generator.",
                    template_name,
                    exc,
                )

        # Fall back to built-in generator
        generator = _GENERATORS.get(filename)
        if generator:
            results[filename] = generator(ir)
        else:
            logger.warning("No generator found for %s.", filename)

    logger.info("Generated %d REFramework XAML files.", len(results))
    return results
