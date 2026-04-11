"""Known UiPath activity-to-NuGet-package mappings and default versions."""
from __future__ import annotations

# Activity name -> NuGet package ID
ACTIVITY_PACKAGE_MAP: dict[str, str] = {
    # Core activities (built into UiPath.System.Activities)
    "Assign": "UiPath.System.Activities",
    "If": "UiPath.System.Activities",
    "ForEach": "UiPath.System.Activities",
    "While": "UiPath.System.Activities",
    "DoWhile": "UiPath.System.Activities",
    "Switch": "UiPath.System.Activities",
    "Sequence": "UiPath.System.Activities",
    "Flowchart": "UiPath.System.Activities",
    "StateMachine": "UiPath.System.Activities",
    "TryCatch": "UiPath.System.Activities",
    "Throw": "UiPath.System.Activities",
    "Rethrow": "UiPath.System.Activities",
    "RetryScope": "UiPath.System.Activities",
    "Parallel": "UiPath.System.Activities",
    "ParallelForEach": "UiPath.System.Activities",
    "Delay": "UiPath.System.Activities",
    "InvokeWorkflowFile": "UiPath.System.Activities",
    "InvokeCode": "UiPath.System.Activities",
    "InvokeMethod": "UiPath.System.Activities",
    "LogMessage": "UiPath.System.Activities",
    "Comment": "UiPath.System.Activities",
    "KillProcess": "UiPath.System.Activities",
    "TerminateWorkflow": "UiPath.System.Activities",
    "ShouldStop": "UiPath.System.Activities",
    "Break": "UiPath.System.Activities",
    "Continue": "UiPath.System.Activities",
    "MultipleAssign": "UiPath.System.Activities",
    "MessageBox": "UiPath.System.Activities",
    "InputDialog": "UiPath.System.Activities",
    "BuildDataTable": "UiPath.System.Activities",
    "AddDataRow": "UiPath.System.Activities",
    "AddDataColumn": "UiPath.System.Activities",
    "FilterDataTable": "UiPath.System.Activities",
    "SortDataTable": "UiPath.System.Activities",
    "JoinDataTables": "UiPath.System.Activities",
    "LookupDataTable": "UiPath.System.Activities",
    "MergeDataTable": "UiPath.System.Activities",
    "OutputDataTable": "UiPath.System.Activities",
    "RemoveDataColumn": "UiPath.System.Activities",
    "RemoveDuplicateRows": "UiPath.System.Activities",
    "GenerateDataTable": "UiPath.System.Activities",
    "ReadTextFile": "UiPath.System.Activities",
    "WriteTextFile": "UiPath.System.Activities",
    "CopyFile": "UiPath.System.Activities",
    "MoveFile": "UiPath.System.Activities",
    "DeleteFile": "UiPath.System.Activities",
    "CreateDirectory": "UiPath.System.Activities",
    "PathExists": "UiPath.System.Activities",
    "DeserializeJson": "UiPath.System.Activities",

    # UI Automation (UiPath.UIAutomation.Activities — renamed from UIAutomationNext in 25.10)
    "NClick": "UiPath.UIAutomation.Activities",
    "NTypeInto": "UiPath.UIAutomation.Activities",
    "NGetText": "UiPath.UIAutomation.Activities",
    "NSelectItem": "UiPath.UIAutomation.Activities",
    "NCheck": "UiPath.UIAutomation.Activities",
    "NHover": "UiPath.UIAutomation.Activities",
    "NDoubleClick": "UiPath.UIAutomation.Activities",
    "NRightClick": "UiPath.UIAutomation.Activities",
    "NKeyboardShortcuts": "UiPath.UIAutomation.Activities",
    "NMouseScroll": "UiPath.UIAutomation.Activities",
    "NCheckState": "UiPath.UIAutomation.Activities",
    "NApplicationCard": "UiPath.UIAutomation.Activities",
    "NExtractData": "UiPath.UIAutomation.Activities",
    "TakeScreenshot": "UiPath.UIAutomation.Activities",
    "WaitScreenReady": "UiPath.UIAutomation.Activities",

    # Excel (UiPath.Excel.Activities)
    "ReadRange": "UiPath.Excel.Activities",
    "WriteRange": "UiPath.Excel.Activities",
    "AppendRange": "UiPath.Excel.Activities",
    "WriteCell": "UiPath.Excel.Activities",
    "ReadCell": "UiPath.Excel.Activities",
    "ExcelApplicationScope": "UiPath.Excel.Activities",

    # Mail (UiPath.Mail.Activities)
    "GetIMAPMailMessages": "UiPath.Mail.Activities",
    "SendSMTPMailMessage": "UiPath.Mail.Activities",
    "GetOutlookMailMessages": "UiPath.Mail.Activities",
    "SendOutlookMailMessage": "UiPath.Mail.Activities",
    "SaveMailAttachments": "UiPath.Mail.Activities",

    # PDF (UiPath.PDF.Activities)
    "ReadPDFText": "UiPath.PDF.Activities",
    "ReadPDFWithOCR": "UiPath.PDF.Activities",

    # Database (UiPath.Database.Activities)
    "DatabaseConnect": "UiPath.Database.Activities",
    "ExecuteQuery": "UiPath.Database.Activities",
    "ExecuteNonQuery": "UiPath.Database.Activities",
    "DatabaseDisconnect": "UiPath.Database.Activities",

    # Web API / HTTP
    "HttpClient": "UiPath.WebAPI.Activities",

    # CSV
    "ReadCSV": "UiPath.CSV.Activities",
    "WriteCSV": "UiPath.CSV.Activities",

    # Orchestrator
    "AddQueueItem": "UiPath.System.Activities",
    "BulkAddQueueItems": "UiPath.System.Activities",
    "GetQueueItem": "UiPath.System.Activities",
    "GetRobotAsset": "UiPath.System.Activities",
    "GetRobotCredential": "UiPath.System.Activities",
    "SetTransactionStatus": "UiPath.System.Activities",
}

# Default package versions (offline fallback, based on UiPath Studio 25.10)
DEFAULT_VERSIONS: dict[str, str] = {
    "UiPath.System.Activities": "25.10.0",
    "UiPath.UIAutomation.Activities": "25.10.16",
    "UiPath.Excel.Activities": "3.2.1",
    "UiPath.Mail.Activities": "2.3.10",
    "UiPath.PDF.Activities": "3.22.0",
    "UiPath.Database.Activities": "1.10.1",
    "UiPath.WebAPI.Activities": "2.3.1",
    "UiPath.CSV.Activities": "1.5.1",
    "UiPath.Testing.Activities": "25.10.0",
    "UiPath.ComplexScenarios.Activities": "1.5.1",
    "UiPath.Persistence.Activities": "3.0.2",
    "UiPath.Form.Activities": "25.10.0",
    "UiPath.SAP.BAPI.Activities": "2.3.1",
    "UiPath.Word.Activities": "2.2.0",
    "UiPath.Presentations.Activities": "2.2.1",
    "UiPath.Cryptography.Activities": "1.6.1",
    "UiPath.IntelligentOCR.Activities": "6.16.0",
}

# Alias for backward compatibility (UIAutomationNext was renamed to UIAutomation in 25.10)
_PACKAGE_ALIASES: dict[str, str] = {
    "UiPath.UIAutomationNext.Activities": "UiPath.UIAutomation.Activities",
}

# Standard packages always included in a new project
STANDARD_PACKAGES: list[str] = [
    "UiPath.System.Activities",
    "UiPath.UIAutomation.Activities",
]

def resolve_package_alias(package_id: str) -> str:
    """Resolve a package alias to its current canonical name.

    Handles the UIAutomationNext → UIAutomation rename.
    """
    return _PACKAGE_ALIASES.get(package_id, package_id)


def get_package_for_activity(activity_name: str) -> str | None:
    """Get the NuGet package ID for a given activity name."""
    return ACTIVITY_PACKAGE_MAP.get(activity_name)


def get_required_packages(activities: list[str]) -> set[str]:
    """Get the set of required NuGet packages for a list of activity names."""
    packages = set(STANDARD_PACKAGES)
    for activity in activities:
        pkg = get_package_for_activity(activity)
        if pkg:
            packages.add(pkg)
    return packages


def get_default_version(package_id: str) -> str:
    """Get the default fallback version for a package.

    Resolves aliases before looking up the version.
    """
    canonical = resolve_package_alias(package_id)
    return DEFAULT_VERSIONS.get(canonical, "1.0.0")
