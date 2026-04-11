"""Registry of valid UiPath activity types, namespaces, enums, and properties.

Based on UiPath Studio 24.10. Used by lint rules to detect hallucinated
activities, invalid enum values, and nonexistent properties.
"""

from __future__ import annotations

# ---------------------------------------------------------------------------
# Common UiPath XML namespace URIs
# ---------------------------------------------------------------------------

_NS_ACTIVITIES = "http://schemas.uipath.com/workflow/activities"
_NS_CORE = "clr-namespace:UiPath.Core.Activities;assembly=UiPath.Core.Activities"
_NS_SYSTEM = "clr-namespace:System.Activities.Statements;assembly=System.Activities"
_NS_SYSTEM_ACT = "clr-namespace:System.Activities;assembly=System.Activities"
_NS_UIPATH_MAIL = "clr-namespace:UiPath.Mail.Activities;assembly=UiPath.Mail.Activities"
_NS_UIPATH_EXCEL = "clr-namespace:UiPath.Excel.Activities;assembly=UiPath.Excel.Activities"
_NS_UIPATH_UI = "clr-namespace:UiPath.UIAutomation.Activities;assembly=UiPath.UIAutomation.Activities"
_NS_UIPATH_UI_N = "clr-namespace:UiPath.UIAutomationNext.Activities;assembly=UiPath.UIAutomationNext.Activities"
_NS_UIPATH_PDF = "clr-namespace:UiPath.PDF.Activities;assembly=UiPath.PDF.Activities"
_NS_UIPATH_WEB = "clr-namespace:UiPath.Web.Activities;assembly=UiPath.Web.Activities"
_NS_UIPATH_SYS = "clr-namespace:UiPath.Core.Activities;assembly=UiPath.System.Activities"
_NS_UIPATH_DT = "clr-namespace:UiPath.DataTableUtilities;assembly=UiPath.Activities"
_NS_UIPATH_ORCH = "clr-namespace:UiPath.Core.Activities;assembly=UiPath.OrchestratorActivities"
_NS_UIPATH_CSV = "clr-namespace:UiPath.CSV.Activities;assembly=UiPath.CSV.Activities"
_NS_UIPATH_CRED = "clr-namespace:UiPath.Credentials.Activities;assembly=UiPath.Credentials.Activities"
_NS_UIPATH_FILE = "clr-namespace:UiPath.Core.Activities;assembly=UiPath.System.Activities"

# ---------------------------------------------------------------------------
# VALID_ACTIVITIES: local name -> fully-qualified xmlns name
# ---------------------------------------------------------------------------

VALID_ACTIVITIES: dict[str, str] = {
    # ── UI Automation (Modern / Next) ──────────────────────────────────
    "NClick": _NS_UIPATH_UI_N,
    "NTypeInto": _NS_UIPATH_UI_N,
    "NGetText": _NS_UIPATH_UI_N,
    "NSelectItem": _NS_UIPATH_UI_N,
    "NCheck": _NS_UIPATH_UI_N,
    "NHover": _NS_UIPATH_UI_N,
    "NDoubleClick": _NS_UIPATH_UI_N,
    "NRightClick": _NS_UIPATH_UI_N,
    "NKeyboardShortcuts": _NS_UIPATH_UI_N,
    "NMouseScroll": _NS_UIPATH_UI_N,
    "NCheckState": _NS_UIPATH_UI_N,
    "NApplicationCard": _NS_UIPATH_UI_N,
    # Classic UI activities
    "Click": _NS_UIPATH_UI,
    "TypeInto": _NS_UIPATH_UI,
    "GetText": _NS_UIPATH_UI,
    "SelectItem": _NS_UIPATH_UI,
    "Check": _NS_UIPATH_UI,
    "Hover": _NS_UIPATH_UI,
    "DoubleClick": _NS_UIPATH_UI,
    "RightClick": _NS_UIPATH_UI,
    "SetText": _NS_UIPATH_UI,
    "SendHotkey": _NS_UIPATH_UI,
    "GetAttribute": _NS_UIPATH_UI,
    "SetFocus": _NS_UIPATH_UI,
    "WaitElement": _NS_UIPATH_UI,
    "ElementExists": _NS_UIPATH_UI,
    "FindElement": _NS_UIPATH_UI,
    "HighlightElement": _NS_UIPATH_UI,
    "AttachBrowser": _NS_UIPATH_UI,
    "AttachWindow": _NS_UIPATH_UI,
    "OpenBrowser": _NS_UIPATH_UI,
    "OpenApplication": _NS_UIPATH_UI,
    "CloseApplication": _NS_UIPATH_UI,
    "CloseTab": _NS_UIPATH_UI,
    "NavigateTo": _NS_UIPATH_UI,
    "GetFullText": _NS_UIPATH_UI,
    "GetVisibleText": _NS_UIPATH_UI,
    "ImageExists": _NS_UIPATH_UI,
    "FindImage": _NS_UIPATH_UI,
    "ClickImage": _NS_UIPATH_UI,
    "Screenshot": _NS_UIPATH_UI,
    "ExtractStructuredData": _NS_UIPATH_UI,
    # ── Control Flow ──────────────────────────────────────────────────
    "If": _NS_SYSTEM,
    "ForEach": _NS_SYSTEM,
    "While": _NS_SYSTEM,
    "DoWhile": _NS_SYSTEM,
    "Switch": _NS_SYSTEM,
    "Flowchart": _NS_SYSTEM,
    "FlowDecision": _NS_SYSTEM,
    "FlowSwitch": _NS_SYSTEM,
    "FlowStep": _NS_SYSTEM,
    "StateMachine": _NS_SYSTEM,
    "State": _NS_SYSTEM,
    "FinalState": _NS_SYSTEM,
    "Parallel": _NS_SYSTEM,
    "ParallelForEach": _NS_SYSTEM,
    "Sequence": _NS_SYSTEM,
    "Pick": _NS_SYSTEM,
    "PickBranch": _NS_SYSTEM,
    # ── Data / DataTable ──────────────────────────────────────────────
    "Assign": _NS_SYSTEM,
    "MultipleAssign": _NS_CORE,
    "BuildDataTable": _NS_CORE,
    "AddDataRow": _NS_CORE,
    "AddDataColumn": _NS_CORE,
    "FilterDataTable": _NS_CORE,
    "SortDataTable": _NS_CORE,
    "JoinDataTables": _NS_CORE,
    "LookupDataTable": _NS_CORE,
    "MergeDataTable": _NS_CORE,
    "OutputDataTable": _NS_CORE,
    "RemoveDataColumn": _NS_CORE,
    "RemoveDuplicateRows": _NS_CORE,
    # ── Error Handling ────────────────────────────────────────────────
    "TryCatch": _NS_SYSTEM,
    "Catch": _NS_SYSTEM,
    "Throw": _NS_SYSTEM,
    "Rethrow": _NS_SYSTEM,
    "RetryScope": _NS_CORE,
    "TerminateWorkflow": _NS_SYSTEM,
    # ── File Operations ───────────────────────────────────────────────
    "CopyFile": _NS_UIPATH_FILE,
    "MoveFile": _NS_UIPATH_FILE,
    "DeleteFile": _NS_UIPATH_FILE,
    "CreateDirectory": _NS_UIPATH_FILE,
    "PathExists": _NS_UIPATH_FILE,
    "ReadTextFile": _NS_UIPATH_FILE,
    "WriteTextFile": _NS_UIPATH_FILE,
    "ReadCSV": _NS_UIPATH_CSV,
    "WriteCSV": _NS_UIPATH_CSV,
    "AppendLine": _NS_UIPATH_FILE,
    # ── Excel / Integration ───────────────────────────────────────────
    "ReadRange": _NS_UIPATH_EXCEL,
    "WriteRange": _NS_UIPATH_EXCEL,
    "AppendRange": _NS_UIPATH_EXCEL,
    "WriteCell": _NS_UIPATH_EXCEL,
    "ReadCell": _NS_UIPATH_EXCEL,
    "ExcelApplicationScope": _NS_UIPATH_EXCEL,
    # ── Mail ──────────────────────────────────────────────────────────
    "GetIMAPMail": _NS_UIPATH_MAIL,
    "GetPOP3Mail": _NS_UIPATH_MAIL,
    "GetOutlookMail": _NS_UIPATH_MAIL,
    "SendMail": _NS_UIPATH_MAIL,
    "SendOutlookMail": _NS_UIPATH_MAIL,
    "SaveMailAttachments": _NS_UIPATH_MAIL,
    "MoveMail": _NS_UIPATH_MAIL,
    # ── PDF ───────────────────────────────────────────────────────────
    "ReadPDFText": _NS_UIPATH_PDF,
    "ReadPDFWithOCR": _NS_UIPATH_PDF,
    # ── Orchestrator ──────────────────────────────────────────────────
    "AddQueueItem": _NS_UIPATH_ORCH,
    "BulkAddQueueItems": _NS_UIPATH_ORCH,
    "GetQueueItem": _NS_UIPATH_ORCH,
    "GetTransactionItem": _NS_UIPATH_ORCH,
    "SetTransactionStatus": _NS_UIPATH_ORCH,
    "GetRobotAsset": _NS_UIPATH_ORCH,
    "GetRobotCredential": _NS_UIPATH_CRED,
    # ── HTTP / Web ────────────────────────────────────────────────────
    "HttpClient": _NS_UIPATH_WEB,
    "DeserializeJson": _NS_UIPATH_WEB,
    "SerializeJson": _NS_UIPATH_WEB,
    "DeserializeXml": _NS_UIPATH_WEB,
    # ── Invoke ────────────────────────────────────────────────────────
    "InvokeWorkflowFile": _NS_CORE,
    "InvokeCode": _NS_CORE,
    "InvokeMethod": _NS_SYSTEM_ACT,
    "InvokePowerShell": _NS_CORE,
    # ── Orchestrator ──────────────────────────────────────────────────
    "GetAsset": _NS_CORE,
    "SetAsset": _NS_CORE,
    "GetCredential": _NS_UIPATH_CRED,
    # ── Excel (modern) ────────────────────────────────────────────────
    "ExcelReadRange": _NS_UIPATH_EXCEL,
    "ExcelWriteRange": _NS_UIPATH_EXCEL,
    "ExcelForEachRow": _NS_UIPATH_EXCEL,
    "UseExcelFile": _NS_UIPATH_EXCEL,
    # ── Misc ──────────────────────────────────────────────────────────
    "LogMessage": _NS_CORE,
    "Comment": _NS_CORE,
    "CommentOut": _NS_CORE,
    "Break": _NS_SYSTEM,
    "Continue": _NS_CORE,
    "KillProcess": _NS_CORE,
    "TakeScreenshot": _NS_UIPATH_UI,
    "ShouldStop": _NS_CORE,
    "Delay": _NS_CORE,
    "MessageBox": _NS_CORE,
    "InputDialog": _NS_CORE,
    "WriteLn": _NS_SYSTEM,
}

# Also index by lowercase for case-insensitive lookups
VALID_ACTIVITIES_LOWER: dict[str, str] = {k.lower(): v for k, v in VALID_ACTIVITIES.items()}

# ---------------------------------------------------------------------------
# VALID_NAMESPACES: xmlns prefix -> URI
# ---------------------------------------------------------------------------

VALID_NAMESPACES: dict[str, str] = {
    "": _NS_ACTIVITIES,
    "ui": "http://schemas.uipath.com/workflow/activities",
    "sap": "http://schemas.uipath.com/workflow/activities/sap",
    "x": "http://schemas.microsoft.com/winfx/2006/xaml",
    "sap2010": "http://schemas.microsoft.com/netfx/2010/xaml/activities/presentation",
    "scg": "clr-namespace:System.Collections.Generic;assembly=mscorlib",
    "sco": "clr-namespace:System.Collections.ObjectModel;assembly=mscorlib",
    "mca": "clr-namespace:Microsoft.CSharp.Activities;assembly=System.Activities",
    "mc": "http://schemas.openxmlformats.org/markup-compatibility/2006",
    "local": _NS_CORE,
    "p": "http://schemas.microsoft.com/netfx/2009/xaml/activities",
    "this": "clr-namespace:",
    "System": "clr-namespace:System;assembly=mscorlib",
    "System.Activities": "clr-namespace:System.Activities;assembly=System.Activities",
    "System.Activities.Statements": _NS_SYSTEM,
    "UiPath.Core.Activities": _NS_CORE,
    "UiPath.Mail.Activities": _NS_UIPATH_MAIL,
    "UiPath.Excel.Activities": _NS_UIPATH_EXCEL,
    "UiPath.UIAutomation.Activities": _NS_UIPATH_UI,
    "UiPath.UIAutomationNext.Activities": _NS_UIPATH_UI_N,
    "UiPath.PDF.Activities": _NS_UIPATH_PDF,
    "UiPath.Web.Activities": _NS_UIPATH_WEB,
    "UiPath.CSV.Activities": _NS_UIPATH_CSV,
    "UiPath.Credentials.Activities": _NS_UIPATH_CRED,
}

# ---------------------------------------------------------------------------
# VALID_ENUMS: property name -> set of valid enum values
# ---------------------------------------------------------------------------

VALID_ENUMS: dict[str, set[str]] = {
    "ClickType": {"CLICK_SINGLE", "CLICK_DOUBLE", "CLICK_DOWN", "CLICK_UP"},
    "MouseButton": {"BTN_LEFT", "BTN_RIGHT", "BTN_MIDDLE"},
    "InputMode": {"Simulate", "HardwareEvents", "ChromiumAPI", "WindowMessages"},
    "KeyModifiers": {"None", "Alt", "Ctrl", "Shift", "Win"},
    "FilterOperator": {"EQ", "NE", "GT", "GE", "LT", "LE", "StartsWith", "EndsWith", "Contains"},
    "JoinType": {"Inner", "Left", "Full"},
    "SortDirection": {"Ascending", "Descending"},
    "MailFolder": {"INBOX", "Sent", "Drafts", "Trash"},
    "BrowserType": {"Chrome", "Firefox", "Edge", "Chromium"},
    "NClickType": {"Single", "Double"},
    "Position": {"Center", "TopLeft", "TopRight", "BottomLeft", "BottomRight"},
    "CursorPosition": {"Center", "TopLeft", "TopRight", "BottomLeft", "BottomRight"},
    "LogLevel": {"Trace", "Info", "Warn", "Error", "Fatal"},
    "Level": {"Trace", "Info", "Warn", "Error", "Fatal"},
    "TypeOfRead": {"FullText", "Native", "OCR"},
    "CompletionType": {"None", "Auto", "AtEnd"},
    "DelayBetweenKeys": {"0", "10", "20", "50", "100"},
    "EmptyField": {"None", "Zero", "SingleSpace"},
    "NewLine": {"LF", "CRLF", "Environment"},
    "ExistingSheetAction": {"DoNothing", "Replace", "Append"},
    "TransactionStatus": {"Successful", "Failed", "Abandoned"},
    "RequestMethod": {"GET", "POST", "PUT", "PATCH", "DELETE", "HEAD", "OPTIONS"},
    "AcceptFormat": {"ANY", "JSON", "XML", "TEXT"},
    "BodyFormat": {"application/json", "application/xml", "text/plain", "multipart/form-data"},
}

# ---------------------------------------------------------------------------
# VALID_PROPERTIES: activity name -> set of valid property/attribute names
# ---------------------------------------------------------------------------

VALID_PROPERTIES: dict[str, set[str]] = {
    "NClick": {
        "DisplayName", "Target", "ClickType", "MouseButton", "KeyModifiers",
        "CursorPosition", "OffsetX", "OffsetY", "InputMode", "DelayAfter",
        "DelayBefore", "ContinueOnError", "TimeoutMS", "AlterIfDisabled",
    },
    "NTypeInto": {
        "DisplayName", "Target", "Text", "ClickBeforeTyping", "EmptyField",
        "DelayBetweenKeys", "InputMode", "DelayAfter", "DelayBefore",
        "ContinueOnError", "TimeoutMS", "Activate",
    },
    "NGetText": {
        "DisplayName", "Target", "Value", "TimeoutMS", "DelayAfter",
        "DelayBefore", "ContinueOnError",
    },
    "NSelectItem": {
        "DisplayName", "Target", "Item", "TimeoutMS", "DelayAfter",
        "DelayBefore", "ContinueOnError",
    },
    "NCheck": {
        "DisplayName", "Target", "Action", "TimeoutMS", "DelayAfter",
        "DelayBefore", "ContinueOnError",
    },
    "NApplicationCard": {
        "DisplayName", "Title", "Process", "Arguments", "CloseAction",
        "TimeoutMS", "DelayAfter", "DelayBefore", "ContinueOnError",
    },
    "If": {
        "DisplayName", "Condition", "sap2010:WorkflowViewState.IdRef",
    },
    "ForEach": {
        "DisplayName", "Values", "TypeArgument",
        "sap2010:WorkflowViewState.IdRef",
    },
    "While": {
        "DisplayName", "Condition", "sap2010:WorkflowViewState.IdRef",
    },
    "DoWhile": {
        "DisplayName", "Condition", "sap2010:WorkflowViewState.IdRef",
    },
    "Switch": {
        "DisplayName", "Expression", "TypeArgument",
        "sap2010:WorkflowViewState.IdRef",
    },
    "Assign": {
        "DisplayName", "To", "Value", "sap2010:WorkflowViewState.IdRef",
    },
    "Sequence": {
        "DisplayName", "sap2010:WorkflowViewState.IdRef",
    },
    "Flowchart": {
        "DisplayName", "StartNode", "sap2010:WorkflowViewState.IdRef",
    },
    "TryCatch": {
        "DisplayName", "sap2010:WorkflowViewState.IdRef",
    },
    "Throw": {
        "DisplayName", "Exception", "sap2010:WorkflowViewState.IdRef",
    },
    "LogMessage": {
        "DisplayName", "Level", "Message", "sap2010:WorkflowViewState.IdRef",
    },
    "InvokeWorkflowFile": {
        "DisplayName", "WorkflowFileName", "FilePath", "Arguments",
        "ContinueOnError", "IsolatedRuntime", "UnSafe",
        "sap2010:WorkflowViewState.IdRef",
    },
    "HttpClient": {
        "DisplayName", "EndPoint", "Method", "AcceptFormat", "Body",
        "BodyFormat", "Headers", "Options", "ResponseContent",
        "ResponseStatus", "StatusCode", "ContinueOnError", "TimeoutMS",
        "sap2010:WorkflowViewState.IdRef",
    },
    "ReadRange": {
        "DisplayName", "SheetName", "Range", "DataTable",
        "AddHeaders", "PreserveFormat", "UseFilter", "WorkbookPath",
        "sap2010:WorkflowViewState.IdRef",
    },
    "WriteRange": {
        "DisplayName", "SheetName", "StartingCell", "DataTable",
        "AddHeaders", "WorkbookPath",
        "sap2010:WorkflowViewState.IdRef",
    },
    "Delay": {
        "DisplayName", "Duration", "sap2010:WorkflowViewState.IdRef",
    },
    "AddQueueItem": {
        "DisplayName", "QueueName", "ItemInformation", "Priority",
        "Reference", "DeferDate", "DueDate",
        "sap2010:WorkflowViewState.IdRef",
    },
    "GetTransactionItem": {
        "DisplayName", "QueueName", "TransactionItem",
        "sap2010:WorkflowViewState.IdRef",
    },
    "SetTransactionStatus": {
        "DisplayName", "TransactionItem", "Status", "ErrorType",
        "Reason", "sap2010:WorkflowViewState.IdRef",
    },
    "GetRobotCredential": {
        "DisplayName", "AssetName", "Username", "Password",
        "sap2010:WorkflowViewState.IdRef",
    },
    "Comment": {
        "DisplayName", "Text", "sap2010:WorkflowViewState.IdRef",
    },
    "MessageBox": {
        "DisplayName", "Text", "Caption", "Buttons",
        "TopMost", "ChosenButton", "sap2010:WorkflowViewState.IdRef",
    },
    "InputDialog": {
        "DisplayName", "Title", "Label", "Value", "Result",
        "IsPassword", "Options", "sap2010:WorkflowViewState.IdRef",
    },
    "ReadTextFile": {
        "DisplayName", "FileName", "Content", "Encoding",
        "sap2010:WorkflowViewState.IdRef",
    },
    "WriteTextFile": {
        "DisplayName", "FileName", "Text", "Encoding", "Append",
        "sap2010:WorkflowViewState.IdRef",
    },
    "DeserializeJson": {
        "DisplayName", "JsonString", "JsonObject", "TypeArgument",
        "sap2010:WorkflowViewState.IdRef",
    },
    "SendMail": {
        "DisplayName", "To", "Subject", "Body", "IsBodyHtml",
        "Attachments", "CC", "BCC", "From", "Port", "Server",
        "SecureConnection", "sap2010:WorkflowViewState.IdRef",
    },
    "GetIMAPMail": {
        "DisplayName", "Server", "Port", "Email", "Password",
        "MailFolder", "Top", "OnlyUnreadMessages", "Messages",
        "SecureConnection", "sap2010:WorkflowViewState.IdRef",
    },
    "KillProcess": {
        "DisplayName", "ProcessName", "sap2010:WorkflowViewState.IdRef",
    },
    "InvokeCode": {
        "DisplayName", "Code", "Language", "Arguments",
        "sap2010:WorkflowViewState.IdRef",
    },
    "RetryScope": {
        "DisplayName", "NumberOfRetries", "RetryInterval",
        "sap2010:WorkflowViewState.IdRef",
    },
    "FilterDataTable": {
        "DisplayName", "DataTable", "OutputDataTable", "FilterRows",
        "SelectColumns", "sap2010:WorkflowViewState.IdRef",
    },
    "BuildDataTable": {
        "DisplayName", "DataTable", "TableInfo",
        "sap2010:WorkflowViewState.IdRef",
    },
    "AddDataRow": {
        "DisplayName", "DataTable", "DataRow", "ArrayRow",
        "sap2010:WorkflowViewState.IdRef",
    },
}
