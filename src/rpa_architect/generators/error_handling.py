"""Error-handling activity generators for UiPath XAML.

Generators for TryCatch, Throw, Rethrow, and RetryScope activities.
"""

from __future__ import annotations

from rpa_architect.generators.base import indent, quote_attr, unique_id
from rpa_architect.generators.registry import register_generator


# ---------------------------------------------------------------------------
# Generators
# ---------------------------------------------------------------------------

def gen_try_catch(
    try_body: str,
    catches: list[dict],
    finally_body: str = "",
    display_name: str = "Try Catch",
) -> str:
    """Generate ``<TryCatch>`` activity XAML.

    Parameters
    ----------
    try_body:
        XAML for the ``Try`` block.
    catches:
        List of dicts with ``exception_type`` (e.g. ``"System.Exception"``)
        and ``body`` (XAML string).
    finally_body:
        Optional XAML for the ``Finally`` block.
    """
    ref = unique_id()
    parts = [
        f'<TryCatch DisplayName="{quote_attr(display_name)}"'
        f' sap2010:WorkflowViewState.IdRef="TryCatch_{ref}">',
        f'  <TryCatch.Try>',
        indent(try_body, 2),
        f'  </TryCatch.Try>',
        f'  <TryCatch.Catches>',
    ]

    for catch in catches:
        exc_type = catch.get("exception_type", "System.Exception")
        catch_body = catch.get("body", "")
        catch_ref = unique_id()
        parts.extend([
            f'    <Catch x:TypeArguments="s:Exception"'
            f' sap2010:WorkflowViewState.IdRef="Catch_{catch_ref}">',
            f'      <ActivityAction x:TypeArguments="s:Exception">',
            f'        <ActivityAction.Argument>',
            f'          <DelegateInArgument x:TypeArguments="s:Exception" Name="exception" />',
            f'        </ActivityAction.Argument>',
        ])
        if catch_body:
            parts.append(indent(catch_body, 4))
        parts.extend([
            f'      </ActivityAction>',
            f'    </Catch>',
        ])

    parts.append(f'  </TryCatch.Catches>')

    if finally_body:
        parts.extend([
            f'  <TryCatch.Finally>',
            indent(finally_body, 2),
            f'  </TryCatch.Finally>',
        ])

    parts.append('</TryCatch>')
    return "\n".join(parts)


def gen_throw(
    exception_type: str,
    message: str,
    display_name: str = "Throw",
) -> str:
    """Generate ``<Throw>`` activity XAML."""
    ref = unique_id()
    return (
        f'<Throw DisplayName="{quote_attr(display_name)}"'
        f' Exception="[New {quote_attr(exception_type)}'
        f'(&quot;{quote_attr(message)}&quot;)]"'
        f' sap2010:WorkflowViewState.IdRef="Throw_{ref}" />'
    )


def gen_rethrow(
    display_name: str = "Rethrow",
) -> str:
    """Generate ``<Rethrow>`` activity XAML."""
    ref = unique_id()
    return (
        f'<Rethrow DisplayName="{quote_attr(display_name)}"'
        f' sap2010:WorkflowViewState.IdRef="Rethrow_{ref}" />'
    )


def gen_retry_scope(
    body: str,
    max_retries: int = 3,
    retry_interval: int = 5,
    display_name: str = "Retry Scope",
) -> str:
    """Generate ``<ui:RetryScope>`` activity XAML.

    Parameters
    ----------
    body:
        XAML for the action to retry.
    max_retries:
        Maximum number of retry attempts.
    retry_interval:
        Seconds between retries.
    """
    ref = unique_id()
    return (
        f'<ui:RetryScope NumberOfRetries="{max_retries}"'
        f' RetryInterval="00:00:{retry_interval:02d}"'
        f' DisplayName="{quote_attr(display_name)}"'
        f' sap2010:WorkflowViewState.IdRef="RetryScope_{ref}">\n'
        f'  <ui:RetryScope.ActivityBody>\n'
        f'    <ActivityAction>\n'
        f'{indent(body, 3)}\n'
        f'    </ActivityAction>\n'
        f'  </ui:RetryScope.ActivityBody>\n'
        f'</ui:RetryScope>'
    )


# ---------------------------------------------------------------------------
# Registration
# ---------------------------------------------------------------------------

register_generator("try_catch", gen_try_catch, "Try Catch", "Error Handling",
                   "Try/Catch/Finally error handling block")
register_generator("throw", gen_throw, "Throw", "Error Handling",
                   "Throw an exception")
register_generator("rethrow", gen_rethrow, "Rethrow", "Error Handling",
                   "Re-throw the current exception in a Catch block")
register_generator("retry_scope", gen_retry_scope, "Retry Scope", "Error Handling",
                   "Retry an action up to N times on failure")
