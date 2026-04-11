"""Coded Automations API generators for UiPath C# coded workflows.

Generates C# method call strings for UiPath's Coded Automations APIs,
covering both ``system.*`` and ``uiAutomation.*`` namespaces.
"""

from __future__ import annotations

from rpa_architect.generators.registry import register_generator


# ---------------------------------------------------------------------------
# System APIs (system.*)
# ---------------------------------------------------------------------------

def gen_coded_get_asset(asset_name: str, variable: str) -> str:
    """Generate ``system.GetAsset`` call."""
    return f'var {variable} = system.GetAsset("{asset_name}");'


def gen_coded_set_asset(asset_name: str, value: str) -> str:
    """Generate ``system.SetAsset`` call."""
    return f'system.SetAsset("{asset_name}", {value});'


def gen_coded_get_credential(
    asset_name: str, username_var: str, password_var: str
) -> str:
    """Generate ``system.GetCredential`` call with tuple deconstruction."""
    return f'var ({username_var}, {password_var}) = system.GetCredential("{asset_name}");'


def gen_coded_add_queue_item(queue_name: str, data_expr: str) -> str:
    """Generate ``system.AddQueueItem`` call."""
    return f'system.AddQueueItem("{queue_name}", {data_expr});'


def gen_coded_get_queue_item(queue_name: str, variable: str) -> str:
    """Generate ``system.GetQueueItem`` call."""
    return f'var {variable} = system.GetQueueItem("{queue_name}");'


def gen_coded_set_transaction_status(item_var: str, status: str) -> str:
    """Generate ``system.SetTransactionStatus`` call."""
    return (
        f"system.SetTransactionStatus({item_var}, "
        f"UiPath.Core.Activities.TransactionStatus.{status});"
    )


def gen_coded_log_message(message: str, level: str = "Info") -> str:
    """Generate ``Log`` call."""
    return f'Log("{message}", LogLevel.{level});'


def gen_coded_read_text_file(path: str, variable: str) -> str:
    """Generate ``system.ReadTextFile`` call."""
    return f'var {variable} = system.ReadTextFile("{path}");'


def gen_coded_write_text_file(path: str, content_expr: str) -> str:
    """Generate ``system.WriteTextFile`` call."""
    return f'system.WriteTextFile("{path}", {content_expr});'


def gen_coded_copy_file(source: str, destination: str) -> str:
    """Generate ``system.CopyFile`` call."""
    return f'system.CopyFile("{source}", "{destination}");'


def gen_coded_path_exists(path: str, variable: str) -> str:
    """Generate ``system.PathExists`` call."""
    return f'var {variable} = system.PathExists("{path}");'


def gen_coded_orchestrator_http_request(
    method: str, path: str, variable: str
) -> str:
    """Generate ``system.OrchestratorHTTPRequest`` call."""
    return (
        f'var {variable} = system.OrchestratorHTTPRequest("{method}", "{path}");'
    )


# ---------------------------------------------------------------------------
# UI Automation APIs (uiAutomation.*)
# ---------------------------------------------------------------------------

def gen_coded_open_app(descriptor_path: str, variable: str) -> str:
    """Generate ``uiAutomation.Open`` call with using statement."""
    return f"using var {variable} = uiAutomation.Open({descriptor_path});"


def gen_coded_click(screen_var: str, element_name: str) -> str:
    """Generate a Click call on a screen variable."""
    return f'{screen_var}.Click("{element_name}");'


def gen_coded_type_into(screen_var: str, element_name: str, text: str) -> str:
    """Generate a TypeInto call on a screen variable."""
    return f'{screen_var}.TypeInto("{element_name}", "{text}");'


def gen_coded_get_text(
    screen_var: str, element_name: str, variable: str
) -> str:
    """Generate a GetText call on a screen variable."""
    return f'var {variable} = {screen_var}.GetText("{element_name}");'


# ---------------------------------------------------------------------------
# Registration
# ---------------------------------------------------------------------------

register_generator(
    "coded_get_asset", gen_coded_get_asset,
    "Get Asset (Coded)", "Coded API",
    "Retrieve an Orchestrator asset value",
)
register_generator(
    "coded_set_asset", gen_coded_set_asset,
    "Set Asset (Coded)", "Coded API",
    "Set an Orchestrator asset value",
)
register_generator(
    "coded_get_credential", gen_coded_get_credential,
    "Get Credential (Coded)", "Coded API",
    "Retrieve credential username and password from Orchestrator",
)
register_generator(
    "coded_add_queue_item", gen_coded_add_queue_item,
    "Add Queue Item (Coded)", "Coded API",
    "Add an item to an Orchestrator queue",
)
register_generator(
    "coded_get_queue_item", gen_coded_get_queue_item,
    "Get Queue Item (Coded)", "Coded API",
    "Retrieve the next item from an Orchestrator queue",
)
register_generator(
    "coded_set_transaction_status", gen_coded_set_transaction_status,
    "Set Transaction Status (Coded)", "Coded API",
    "Set the processing status of a queue transaction",
)
register_generator(
    "coded_log_message", gen_coded_log_message,
    "Log Message (Coded)", "Coded API",
    "Write a log message at a specified level",
)
register_generator(
    "coded_read_text_file", gen_coded_read_text_file,
    "Read Text File (Coded)", "Coded API",
    "Read a text file into a variable",
)
register_generator(
    "coded_write_text_file", gen_coded_write_text_file,
    "Write Text File (Coded)", "Coded API",
    "Write content to a text file",
)
register_generator(
    "coded_copy_file", gen_coded_copy_file,
    "Copy File (Coded)", "Coded API",
    "Copy a file from source to destination",
)
register_generator(
    "coded_path_exists", gen_coded_path_exists,
    "Path Exists (Coded)", "Coded API",
    "Check whether a file or directory path exists",
)
register_generator(
    "coded_orchestrator_http_request", gen_coded_orchestrator_http_request,
    "Orchestrator HTTP Request (Coded)", "Coded API",
    "Send an HTTP request to the Orchestrator API",
)
register_generator(
    "coded_open_app", gen_coded_open_app,
    "Open Application (Coded)", "Coded API",
    "Open an application using a UI descriptor",
)
register_generator(
    "coded_click", gen_coded_click,
    "Click (Coded)", "Coded API",
    "Click a UI element on an open application screen",
)
register_generator(
    "coded_type_into", gen_coded_type_into,
    "Type Into (Coded)", "Coded API",
    "Type text into a UI element on an open application screen",
)
register_generator(
    "coded_get_text", gen_coded_get_text,
    "Get Text (Coded)", "Coded API",
    "Extract text from a UI element on an open application screen",
)
