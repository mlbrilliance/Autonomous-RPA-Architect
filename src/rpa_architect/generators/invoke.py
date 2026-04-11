"""Invoke activity generators for UiPath XAML.

Generators for Invoke Workflow, Invoke Code, and Invoke Method activities.
"""

from __future__ import annotations

from rpa_architect.generators.base import indent, quote_attr, unique_id
from rpa_architect.generators.registry import register_generator


# ---------------------------------------------------------------------------
# Generators
# ---------------------------------------------------------------------------

def gen_invoke_workflow(
    workflow_path: str,
    arguments: dict[str, tuple[str, str]] | None = None,
    display_name: str = "Invoke Workflow",
) -> str:
    """Generate ``<ui:InvokeWorkflowFile>`` activity XAML.

    Parameters
    ----------
    workflow_path:
        Relative path to the ``.xaml`` workflow file.
    arguments:
        Mapping of argument name to ``(direction, value)`` where direction is
        ``"In"``, ``"Out"``, or ``"InOut"``.
    """
    ref = unique_id()
    arguments = arguments or {}

    if not arguments:
        return (
            f'<ui:InvokeWorkflowFile WorkflowFileName="{quote_attr(workflow_path)}"'
            f' DisplayName="{quote_attr(display_name)}"'
            f' sap2010:WorkflowViewState.IdRef="InvokeWorkflowFile_{ref}" />'
        )

    arg_parts: list[str] = []
    for arg_name, (direction, value) in arguments.items():
        direction_lower = direction.lower()
        if direction_lower == "in":
            arg_parts.append(
                f'    <InArgument x:TypeArguments="x:Object"'
                f' x:Key="{quote_attr(arg_name)}">[{quote_attr(value)}]</InArgument>'
            )
        elif direction_lower == "out":
            arg_parts.append(
                f'    <OutArgument x:TypeArguments="x:Object"'
                f' x:Key="{quote_attr(arg_name)}">[{quote_attr(value)}]</OutArgument>'
            )
        elif direction_lower == "inout":
            arg_parts.append(
                f'    <InOutArgument x:TypeArguments="x:Object"'
                f' x:Key="{quote_attr(arg_name)}">[{quote_attr(value)}]</InOutArgument>'
            )

    args_xml = "\n".join(arg_parts)
    return (
        f'<ui:InvokeWorkflowFile WorkflowFileName="{quote_attr(workflow_path)}"'
        f' DisplayName="{quote_attr(display_name)}"'
        f' sap2010:WorkflowViewState.IdRef="InvokeWorkflowFile_{ref}">\n'
        f'  <ui:InvokeWorkflowFile.Arguments>\n'
        f'{args_xml}\n'
        f'  </ui:InvokeWorkflowFile.Arguments>\n'
        f'</ui:InvokeWorkflowFile>'
    )


def gen_invoke_code(
    code: str,
    language: str = "CSharp",
    arguments: list[dict] | None = None,
    display_name: str = "Invoke Code",
) -> str:
    """Generate ``<ui:InvokeCode>`` activity XAML.

    Parameters
    ----------
    code:
        The inline code to execute.
    language:
        Language of the code (``CSharp`` or ``VBNet``).
    arguments:
        Optional list of dicts with ``name``, ``type`` (XAML type),
        ``direction`` (``In``, ``Out``, ``InOut``), and ``value``.
    """
    ref = unique_id()
    arguments = arguments or []

    arg_parts: list[str] = []
    for arg in arguments:
        arg_name = arg.get("name", "arg")
        arg_type = arg.get("type", "x:String")
        arg_dir = arg.get("direction", "In")
        arg_val = arg.get("value", "")

        if arg_dir.lower() == "in":
            arg_parts.append(
                f'    <ui:InvokeCodeArgument Name="{quote_attr(arg_name)}"'
                f' Type="{quote_attr(arg_type)}"'
                f' Direction="In"'
                f' Value="[{quote_attr(arg_val)}]" />'
            )
        elif arg_dir.lower() == "out":
            arg_parts.append(
                f'    <ui:InvokeCodeArgument Name="{quote_attr(arg_name)}"'
                f' Type="{quote_attr(arg_type)}"'
                f' Direction="Out"'
                f' Value="[{quote_attr(arg_val)}]" />'
            )
        elif arg_dir.lower() == "inout":
            arg_parts.append(
                f'    <ui:InvokeCodeArgument Name="{quote_attr(arg_name)}"'
                f' Type="{quote_attr(arg_type)}"'
                f' Direction="InOut"'
                f' Value="[{quote_attr(arg_val)}]" />'
            )

    code_escaped = quote_attr(code)

    if arg_parts:
        args_xml = "\n".join(arg_parts)
        return (
            f'<ui:InvokeCode Language="{quote_attr(language)}"'
            f' Code="{code_escaped}"'
            f' DisplayName="{quote_attr(display_name)}"'
            f' sap2010:WorkflowViewState.IdRef="InvokeCode_{ref}">\n'
            f'  <ui:InvokeCode.CodeArguments>\n'
            f'{args_xml}\n'
            f'  </ui:InvokeCode.CodeArguments>\n'
            f'</ui:InvokeCode>'
        )
    else:
        return (
            f'<ui:InvokeCode Language="{quote_attr(language)}"'
            f' Code="{code_escaped}"'
            f' DisplayName="{quote_attr(display_name)}"'
            f' sap2010:WorkflowViewState.IdRef="InvokeCode_{ref}" />'
        )


def gen_invoke_method(
    target_object: str,
    method_name: str,
    parameters: list[dict] | None = None,
    result: str = "",
    display_name: str = "Invoke Method",
) -> str:
    """Generate ``<InvokeMethod>`` activity XAML.

    Parameters
    ----------
    target_object:
        Expression for the object to invoke the method on.
    method_name:
        Name of the method to call.
    parameters:
        Optional list of dicts with ``type``, ``direction``, and ``value``.
    result:
        Variable to store the method return value.
    """
    ref = unique_id()
    parameters = parameters or []

    result_attr = f' Result="[{quote_attr(result)}]"' if result else ""

    if not parameters:
        return (
            f'<InvokeMethod TargetObject="[{quote_attr(target_object)}]"'
            f' MethodName="{quote_attr(method_name)}"'
            f'{result_attr}'
            f' DisplayName="{quote_attr(display_name)}"'
            f' sap2010:WorkflowViewState.IdRef="InvokeMethod_{ref}" />'
        )

    param_parts: list[str] = []
    for p in parameters:
        p_type = p.get("type", "x:String")
        p_dir = p.get("direction", "In")
        p_val = p.get("value", "")

        if p_dir.lower() == "in":
            param_parts.append(
                f'    <InArgument x:TypeArguments="{quote_attr(p_type)}">'
                f'[{quote_attr(p_val)}]</InArgument>'
            )
        elif p_dir.lower() == "out":
            param_parts.append(
                f'    <OutArgument x:TypeArguments="{quote_attr(p_type)}">'
                f'[{quote_attr(p_val)}]</OutArgument>'
            )
        elif p_dir.lower() == "inout":
            param_parts.append(
                f'    <InOutArgument x:TypeArguments="{quote_attr(p_type)}">'
                f'[{quote_attr(p_val)}]</InOutArgument>'
            )

    params_xml = "\n".join(param_parts)
    return (
        f'<InvokeMethod TargetObject="[{quote_attr(target_object)}]"'
        f' MethodName="{quote_attr(method_name)}"'
        f'{result_attr}'
        f' DisplayName="{quote_attr(display_name)}"'
        f' sap2010:WorkflowViewState.IdRef="InvokeMethod_{ref}">\n'
        f'  <InvokeMethod.Parameters>\n'
        f'{params_xml}\n'
        f'  </InvokeMethod.Parameters>\n'
        f'</InvokeMethod>'
    )


# ---------------------------------------------------------------------------
# Registration
# ---------------------------------------------------------------------------

register_generator("invoke_workflow", gen_invoke_workflow, "Invoke Workflow",
                   "Invoke", "Invoke another .xaml workflow file")
register_generator("invoke_code", gen_invoke_code, "Invoke Code", "Invoke",
                   "Execute inline C# or VB.NET code")
register_generator("invoke_method", gen_invoke_method, "Invoke Method", "Invoke",
                   "Invoke a method on an object")
