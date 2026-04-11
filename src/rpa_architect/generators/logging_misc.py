"""Logging and miscellaneous activity generators for UiPath XAML.

Generators for Log Message, Comment, Kill Process, Take Screenshot,
Terminate Workflow, and Should Stop.
"""

from __future__ import annotations

from rpa_architect.generators.base import quote_attr, unique_id
from rpa_architect.generators.registry import register_generator


# ---------------------------------------------------------------------------
# Generators
# ---------------------------------------------------------------------------

def gen_log_message(
    message: str,
    level: str = "Info",
    display_name: str = "Log Message",
) -> str:
    """Generate ``<ui:LogMessage>`` activity XAML.

    Parameters
    ----------
    message:
        The log message expression. May contain string interpolation
        (e.g. ``$"Processing item {itemId}"``).
    level:
        Log level: ``Trace``, ``Info``, ``Warn``, ``Error``, ``Fatal``.
    """
    ref = unique_id()
    return (
        f'<ui:LogMessage Level="{quote_attr(level)}"'
        f' Message="{quote_attr(message)}"'
        f' DisplayName="{quote_attr(display_name)}"'
        f' sap2010:WorkflowViewState.IdRef="LogMessage_{ref}" />'
    )


def gen_comment(
    text: str,
    display_name: str = "Comment",
) -> str:
    """Generate ``<ui:Comment>`` activity XAML."""
    ref = unique_id()
    return (
        f'<ui:Comment Text="{quote_attr(text)}"'
        f' DisplayName="{quote_attr(display_name)}"'
        f' sap2010:WorkflowViewState.IdRef="Comment_{ref}" />'
    )


def gen_kill_process(
    process_name: str,
    display_name: str = "Kill Process",
) -> str:
    """Generate ``<ui:KillProcess>`` activity XAML."""
    ref = unique_id()
    return (
        f'<ui:KillProcess ProcessName="{quote_attr(process_name)}"'
        f' DisplayName="{quote_attr(display_name)}"'
        f' sap2010:WorkflowViewState.IdRef="KillProcess_{ref}" />'
    )


def gen_take_screenshot(
    output: str = "",
    display_name: str = "Take Screenshot",
) -> str:
    """Generate ``<ui:TakeScreenshot>`` activity XAML."""
    ref = unique_id()
    out_attr = f' Image="[{quote_attr(output)}]"' if output else ""
    return (
        f'<ui:TakeScreenshot{out_attr}'
        f' DisplayName="{quote_attr(display_name)}"'
        f' sap2010:WorkflowViewState.IdRef="TakeScreenshot_{ref}" />'
    )


def gen_terminate_workflow(
    exception_type: str = "System.Exception",
    reason: str = "",
    display_name: str = "Terminate Workflow",
) -> str:
    """Generate ``<TerminateWorkflow>`` activity XAML."""
    ref = unique_id()
    reason_expr = reason if reason else "Terminated by automation"
    return (
        f'<TerminateWorkflow DisplayName="{quote_attr(display_name)}"'
        f' sap2010:WorkflowViewState.IdRef="TerminateWorkflow_{ref}">\n'
        f'  <TerminateWorkflow.Exception>\n'
        f'    <InArgument x:TypeArguments="s:Exception">'
        f'[New {quote_attr(exception_type)}'
        f'(&quot;{quote_attr(reason_expr)}&quot;)]</InArgument>\n'
        f'  </TerminateWorkflow.Exception>\n'
        f'  <TerminateWorkflow.Reason>\n'
        f'    <InArgument x:TypeArguments="x:String">'
        f'{quote_attr(reason_expr)}</InArgument>\n'
        f'  </TerminateWorkflow.Reason>\n'
        f'</TerminateWorkflow>'
    )


def gen_should_stop(
    output: str = "",
    display_name: str = "Should Stop",
) -> str:
    """Generate ``<ui:ShouldStop>`` activity XAML.

    Used in long-running workflows to check if the Orchestrator has
    requested the process to stop.
    """
    ref = unique_id()
    out_attr = f' Result="[{quote_attr(output)}]"' if output else ""
    return (
        f'<ui:ShouldStop{out_attr}'
        f' DisplayName="{quote_attr(display_name)}"'
        f' sap2010:WorkflowViewState.IdRef="ShouldStop_{ref}" />'
    )


# ---------------------------------------------------------------------------
# Registration
# ---------------------------------------------------------------------------

register_generator("log_message", gen_log_message, "Log Message", "Logging",
                   "Write a message to the Robot log")
register_generator("comment", gen_comment, "Comment", "Miscellaneous",
                   "Add a designer comment (no runtime effect)")
register_generator("kill_process", gen_kill_process, "Kill Process", "Miscellaneous",
                   "Kill a running process by name")
register_generator("take_screenshot", gen_take_screenshot, "Take Screenshot",
                   "Miscellaneous", "Capture a screenshot")
register_generator("terminate_workflow", gen_terminate_workflow, "Terminate Workflow",
                   "Miscellaneous", "Terminate the current workflow with an exception")
register_generator("should_stop", gen_should_stop, "Should Stop", "Miscellaneous",
                   "Check if the Orchestrator requested the process to stop")
