"""Generate InvokeWorkflowFile XAML with proper argument bindings."""
from __future__ import annotations

import logging
from pathlib import PurePosixPath
from typing import Any

logger = logging.getLogger(__name__)

# UiPath XAML namespace prefixes used in InvokeWorkflowFile activities
_DIRECTION_TAG = {
    "in": "InArgument",
    "out": "OutArgument",
    "inout": "InOutArgument",
}

# Prefix conventions for argument keys in UiPath
_KEY_PREFIX = {
    "in": "in_",
    "out": "out_",
    "inout": "io_",
}


def generate_invoke_workflow(
    workflow_path: str,
    arguments: dict[str, tuple[str, str]] | None = None,
    display_name: str | None = None,
) -> str:
    """Generate an InvokeWorkflowFile XAML element.

    Args:
        workflow_path: Relative path to the workflow (e.g., "Workflows/ProcessInvoice.xaml")
        arguments: Dict of arg_name -> (direction, value_expression)
                   direction: "In", "Out", "InOut"
        display_name: Optional display name (defaults to workflow filename)

    Returns:
        Valid XAML string for an InvokeWorkflowFile activity
    """
    if display_name is None:
        display_name = PurePosixPath(workflow_path).stem

    arguments = arguments or {}

    # Normalise path separators to backslash (UiPath convention on Windows)
    normalised_path = workflow_path.replace("/", "\\")

    if not arguments:
        return (
            f'<ui:InvokeWorkflowFile'
            f' WorkflowFileName="{_xml_escape(normalised_path)}"'
            f' DisplayName="{_xml_escape(display_name)}" />'
        )

    arg_lines = []
    for arg_name, (direction, value) in arguments.items():
        arg_lines.append(
            generate_argument_binding(arg_name, direction, value)
        )

    args_xml = "\n".join(f"      {line}" for line in arg_lines)
    return (
        f'<ui:InvokeWorkflowFile'
        f' WorkflowFileName="{_xml_escape(normalised_path)}"'
        f' DisplayName="{_xml_escape(display_name)}">\n'
        f'    <ui:InvokeWorkflowFile.Arguments>\n'
        f'{args_xml}\n'
        f'    </ui:InvokeWorkflowFile.Arguments>\n'
        f'</ui:InvokeWorkflowFile>'
    )


def generate_argument_binding(
    name: str,
    direction: str,
    value: str,
    arg_type: str = "x:String",
) -> str:
    """Generate a single argument binding XAML element.

    For In arguments:    <InArgument x:TypeArguments="x:String" x:Key="in_argName">[value]</InArgument>
    For Out arguments:   <OutArgument x:TypeArguments="x:String" x:Key="out_argName">[variable]</OutArgument>
    For InOut arguments: <InOutArgument x:TypeArguments="x:String" x:Key="io_argName">[variable]</InOutArgument>

    Args:
        name: The argument name (without direction prefix).
        direction: "In", "Out", or "InOut".
        value: The VB expression or variable name to bind.
        arg_type: The XAML type argument (default "x:String").

    Returns:
        A single XML element string.
    """
    dir_lower = direction.lower()
    tag = _DIRECTION_TAG.get(dir_lower)
    if tag is None:
        logger.warning("Unknown argument direction '%s' for '%s'; defaulting to InArgument.", direction, name)
        tag = "InArgument"
        dir_lower = "in"

    prefix = _KEY_PREFIX.get(dir_lower, "in_")
    key = f"{prefix}{name}"

    # Wrap value in brackets for VB expression if not already wrapped
    if value and not value.startswith("["):
        value_expr = f"[{value}]"
    else:
        value_expr = value

    return (
        f'<{tag} x:TypeArguments="{_xml_escape(arg_type)}"'
        f' x:Key="{_xml_escape(key)}">{_xml_escape_text(value_expr)}</{tag}>'
    )


def generate_invoke_chain(
    workflows: list[dict[str, Any]],
    shared_variables: dict[str, str] | None = None,
) -> str:
    """Generate a sequence of InvokeWorkflowFile calls for multiple workflows.

    Args:
        workflows: List of {"path": str, "arguments": dict, "display_name": str}
                   Each arguments dict maps arg_name -> (direction, value_expression).
        shared_variables: Variables to pass as In arguments to all workflows
                          (e.g., {"Config": "Config", "TransactionItem": "TransactionItem"}).
                          Maps argument_name -> variable_name.

    Returns:
        XAML Sequence containing all invocations.
    """
    shared_variables = shared_variables or {}

    invocation_lines: list[str] = []

    for wf in workflows:
        path = wf.get("path", "")
        arguments: dict[str, tuple[str, str]] = dict(wf.get("arguments", {}))
        name = wf.get("display_name") or PurePosixPath(path).stem

        # Merge shared variables as In arguments (workflow-specific args take precedence)
        for var_name, var_value in shared_variables.items():
            if var_name not in arguments:
                arguments[var_name] = ("In", var_value)

        invoke_xml = generate_invoke_workflow(
            workflow_path=path,
            arguments=arguments if arguments else None,
            display_name=name,
        )
        # Indent each invocation inside the Sequence
        indented = "\n".join(f"    {line}" for line in invoke_xml.splitlines())
        invocation_lines.append(indented)

    body = "\n".join(invocation_lines)
    return (
        f'<Sequence DisplayName="Invoke Business Workflows">\n'
        f'{body}\n'
        f'</Sequence>'
    )


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _xml_escape(value: str) -> str:
    """Escape a string for use inside an XML attribute value."""
    return (
        value
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
        .replace("'", "&apos;")
    )


def _xml_escape_text(value: str) -> str:
    """Escape a string for use as XML text content (less strict than attribute)."""
    return (
        value
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
    )
