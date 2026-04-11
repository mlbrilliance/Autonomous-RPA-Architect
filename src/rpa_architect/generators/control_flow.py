"""Control-flow activity generators for UiPath XAML.

Generates If, ForEach, While, Switch, Flowchart, StateMachine, Parallel,
and other control-flow structures.
"""

from __future__ import annotations

from rpa_architect.generators.base import indent, quote_attr, unique_id
from rpa_architect.generators.registry import register_generator


# ---------------------------------------------------------------------------
# Generators
# ---------------------------------------------------------------------------

def gen_if(
    condition: str,
    then_body: str,
    else_body: str = "",
    display_name: str = "If",
) -> str:
    """Generate ``<If>`` activity XAML."""
    ref = unique_id()
    parts = [
        f'<If Condition="[{quote_attr(condition)}]"'
        f' DisplayName="{quote_attr(display_name)}"'
        f' sap2010:WorkflowViewState.IdRef="If_{ref}">',
        f'  <If.Then>',
        indent(then_body, 2),
        f'  </If.Then>',
    ]
    if else_body:
        parts.extend([
            f'  <If.Else>',
            indent(else_body, 2),
            f'  </If.Else>',
        ])
    parts.append('</If>')
    return "\n".join(parts)


def gen_if_else_if(
    conditions: list[tuple[str, str]],
    else_body: str = "",
    display_name: str = "If-ElseIf",
) -> str:
    """Generate nested ``<If>`` activities to emulate If / ElseIf chains.

    Parameters
    ----------
    conditions:
        List of ``(condition_expression, body_xaml)`` tuples evaluated in order.
    else_body:
        XAML body for the final ``Else`` branch.
    """
    if not conditions:
        return ""

    # Build from the innermost else outward
    result = else_body
    for cond_expr, cond_body in reversed(conditions):
        result = gen_if(
            condition=cond_expr,
            then_body=cond_body,
            else_body=result,
            display_name=display_name,
        )
    return result


def gen_foreach(
    collection: str,
    item_type: str,
    item_name: str,
    body: str,
    display_name: str = "For Each",
) -> str:
    """Generate ``<ForEach>`` activity XAML.

    Parameters
    ----------
    collection:
        Expression referencing the collection to iterate.
    item_type:
        .NET type of each item (e.g. ``x:String``, ``sd:DataRow``).
    item_name:
        Variable name for the current item.
    body:
        XAML body to execute for each item.
    """
    ref = unique_id()
    return (
        f'<ForEach x:TypeArguments="{quote_attr(item_type)}"'
        f' Values="[{quote_attr(collection)}]"'
        f' DisplayName="{quote_attr(display_name)}"'
        f' sap2010:WorkflowViewState.IdRef="ForEach_{ref}">\n'
        f'  <ActivityAction x:TypeArguments="{quote_attr(item_type)}">\n'
        f'    <ActivityAction.Argument>\n'
        f'      <DelegateInArgument x:TypeArguments="{quote_attr(item_type)}"'
        f' Name="{quote_attr(item_name)}" />\n'
        f'    </ActivityAction.Argument>\n'
        f'{indent(body, 2)}\n'
        f'  </ActivityAction>\n'
        f'</ForEach>'
    )


def gen_foreach_row(
    datatable: str,
    body: str,
    display_name: str = "For Each Row",
) -> str:
    """Generate ``<ui:ForEachRow>`` activity XAML for iterating DataTable rows."""
    ref = unique_id()
    return (
        f'<ui:ForEachRow DataTable="[{quote_attr(datatable)}]"'
        f' DisplayName="{quote_attr(display_name)}"'
        f' sap2010:WorkflowViewState.IdRef="ForEachRow_{ref}">\n'
        f'  <ui:ForEachRow.Body>\n'
        f'    <ActivityAction x:TypeArguments="sd:DataRow">\n'
        f'      <ActivityAction.Argument>\n'
        f'        <DelegateInArgument x:TypeArguments="sd:DataRow" Name="CurrentRow" />\n'
        f'      </ActivityAction.Argument>\n'
        f'{indent(body, 3)}\n'
        f'    </ActivityAction>\n'
        f'  </ui:ForEachRow.Body>\n'
        f'</ui:ForEachRow>'
    )


def gen_foreach_file(
    directory: str,
    pattern: str,
    body: str,
    display_name: str = "For Each File",
) -> str:
    """Generate ``<ui:ForEachFileInFolder>`` activity XAML."""
    ref = unique_id()
    return (
        f'<ui:ForEachFileInFolder Directory="{quote_attr(directory)}"'
        f' SearchPattern="{quote_attr(pattern)}"'
        f' DisplayName="{quote_attr(display_name)}"'
        f' sap2010:WorkflowViewState.IdRef="ForEachFileInFolder_{ref}">\n'
        f'  <ui:ForEachFileInFolder.Body>\n'
        f'    <ActivityAction x:TypeArguments="x:String">\n'
        f'      <ActivityAction.Argument>\n'
        f'        <DelegateInArgument x:TypeArguments="x:String" Name="CurrentFile" />\n'
        f'      </ActivityAction.Argument>\n'
        f'{indent(body, 3)}\n'
        f'    </ActivityAction>\n'
        f'  </ui:ForEachFileInFolder.Body>\n'
        f'</ui:ForEachFileInFolder>'
    )


def gen_while(
    condition: str,
    body: str,
    display_name: str = "While",
) -> str:
    """Generate ``<While>`` activity XAML."""
    ref = unique_id()
    return (
        f'<While Condition="[{quote_attr(condition)}]"'
        f' DisplayName="{quote_attr(display_name)}"'
        f' sap2010:WorkflowViewState.IdRef="While_{ref}">\n'
        f'  <While.Body>\n'
        f'{indent(body, 2)}\n'
        f'  </While.Body>\n'
        f'</While>'
    )


def gen_do_while(
    condition: str,
    body: str,
    display_name: str = "Do While",
) -> str:
    """Generate ``<DoWhile>`` activity XAML."""
    ref = unique_id()
    return (
        f'<DoWhile Condition="[{quote_attr(condition)}]"'
        f' DisplayName="{quote_attr(display_name)}"'
        f' sap2010:WorkflowViewState.IdRef="DoWhile_{ref}">\n'
        f'  <DoWhile.Body>\n'
        f'{indent(body, 2)}\n'
        f'  </DoWhile.Body>\n'
        f'</DoWhile>'
    )


def gen_switch(
    expression: str,
    cases: dict[str, str],
    default_body: str = "",
    type_argument: str = "x:String",
    display_name: str = "Switch",
) -> str:
    """Generate ``<Switch>`` activity XAML.

    Parameters
    ----------
    expression:
        The expression to switch on.
    cases:
        Mapping of case value to XAML body.
    default_body:
        XAML for the default case.
    type_argument:
        .NET type for the switch expression.
    """
    ref = unique_id()
    parts = [
        f'<Switch x:TypeArguments="{quote_attr(type_argument)}"'
        f' Expression="[{quote_attr(expression)}]"'
        f' DisplayName="{quote_attr(display_name)}"'
        f' sap2010:WorkflowViewState.IdRef="Switch_{ref}">',
    ]
    if default_body:
        parts.append(f'  <Switch.Default>')
        parts.append(indent(default_body, 2))
        parts.append(f'  </Switch.Default>')

    for case_val, case_body in cases.items():
        parts.append(f'  <x:String x:Key="{quote_attr(case_val)}">')
        parts.append(indent(case_body, 2))
        parts.append(f'  </x:String>')

    parts.append('</Switch>')
    return "\n".join(parts)


def gen_flowchart(
    nodes: list[dict],
    display_name: str = "Flowchart",
) -> str:
    """Generate ``<Flowchart>`` activity XAML.

    Parameters
    ----------
    nodes:
        List of dicts with keys: ``type`` (``"start"``, ``"step"``, ``"decision"``),
        ``display_name``, ``body`` (XAML string), and optionally ``true_target``
        / ``false_target`` indices for decisions.
    """
    ref = unique_id()

    node_refs: list[str] = []
    node_xaml_parts: list[str] = []

    for i, node in enumerate(nodes):
        node_ref = unique_id()
        node_refs.append(node_ref)
        ntype = node.get("type", "step")
        dn = node.get("display_name", f"Node {i}")
        body = node.get("body", "")

        if ntype == "decision":
            condition = node.get("condition", "True")
            true_idx = node.get("true_target")
            false_idx = node.get("false_target")
            part = (
                f'<FlowDecision Condition="[{quote_attr(condition)}]"'
                f' DisplayName="{quote_attr(dn)}"'
                f' sap2010:WorkflowViewState.IdRef="FlowDecision_{node_ref}"'
                f' x:Name="__ReferenceID{node_ref}"'
            )
            # Targets resolved after all nodes are created
            if true_idx is not None and true_idx < len(nodes):
                part += f' True="{{x:Reference __ReferenceID_placeholder_true_{i}}}"'
            if false_idx is not None and false_idx < len(nodes):
                part += f' False="{{x:Reference __ReferenceID_placeholder_false_{i}}}"'
            part += ' />'
            node_xaml_parts.append(part)
        else:
            step_part = (
                f'<FlowStep x:Name="__ReferenceID{node_ref}"'
                f' sap2010:WorkflowViewState.IdRef="FlowStep_{node_ref}">\n'
            )
            if body:
                step_part += indent(body) + '\n'
            next_idx = node.get("next")
            if next_idx is not None and next_idx < len(nodes):
                step_part += f'  <FlowStep.Next>\n'
                step_part += f'    <x:Reference>__ReferenceID_placeholder_next_{i}</x:Reference>\n'
                step_part += f'  </FlowStep.Next>\n'
            step_part += '</FlowStep>'
            node_xaml_parts.append(step_part)

    # Build flowchart body
    body_parts = "\n".join(indent(p) for p in node_xaml_parts)

    start_node = ""
    if nodes and node_refs:
        start_node = f' StartNode="{{x:Reference __ReferenceID{node_refs[0]}}}"'

    result = (
        f'<Flowchart DisplayName="{quote_attr(display_name)}"'
        f' sap2010:WorkflowViewState.IdRef="Flowchart_{ref}"'
        f'{start_node}>\n'
        f'{body_parts}\n'
        f'</Flowchart>'
    )

    # Resolve placeholder references
    for i, node in enumerate(nodes):
        if i < len(node_refs):
            ref_id = node_refs[i]
            result = result.replace(
                f'__ReferenceID_placeholder_true_{i}',
                f'__ReferenceID{node_refs[node["true_target"]]}' if node.get("true_target") is not None and node["true_target"] < len(node_refs) else '',
            )
            result = result.replace(
                f'__ReferenceID_placeholder_false_{i}',
                f'__ReferenceID{node_refs[node["false_target"]]}' if node.get("false_target") is not None and node["false_target"] < len(node_refs) else '',
            )
            result = result.replace(
                f'__ReferenceID_placeholder_next_{i}',
                f'__ReferenceID{node_refs[node["next"]]}' if node.get("next") is not None and node["next"] < len(node_refs) else '',
            )

    return result


def gen_state_machine(
    states: list[dict],
    display_name: str = "State Machine",
) -> str:
    """Generate ``<StateMachine>`` activity XAML.

    Parameters
    ----------
    states:
        List of dicts with keys: ``name``, ``entry`` (XAML body),
        ``transitions`` (list of dicts with ``condition``, ``target_index``,
        ``display_name``), and optionally ``is_final`` (bool).
    """
    ref = unique_id()
    state_refs: list[str] = []
    state_parts: list[str] = []

    for i, state in enumerate(states):
        sref = unique_id()
        state_refs.append(sref)
        sname = state.get("name", f"State {i}")
        entry = state.get("entry", "")
        is_final = state.get("is_final", False)

        if is_final:
            state_parts.append(
                f'<State DisplayName="{quote_attr(sname)}"'
                f' IsFinal="True"'
                f' sap2010:WorkflowViewState.IdRef="State_{sref}"'
                f' x:Name="__StateRef{sref}" />'
            )
        else:
            transitions = state.get("transitions", [])
            trans_parts: list[str] = []
            for t in transitions:
                tref = unique_id()
                t_dn = t.get("display_name", "Transition")
                t_cond = t.get("condition", "True")
                t_target = t.get("target_index", 0)
                trans_parts.append(
                    f'<Transition Condition="[{quote_attr(t_cond)}]"'
                    f' DisplayName="{quote_attr(t_dn)}"'
                    f' To="{{x:Reference __StateRef_placeholder_{t_target}}}"'
                    f' sap2010:WorkflowViewState.IdRef="Transition_{tref}" />'
                )

            trans_xml = ""
            if trans_parts:
                inner = "\n".join(indent(t, 2) for t in trans_parts)
                trans_xml = f'\n  <State.Transitions>\n{inner}\n  </State.Transitions>'

            entry_xml = ""
            if entry:
                entry_xml = f'\n  <State.Entry>\n{indent(entry, 2)}\n  </State.Entry>'

            state_parts.append(
                f'<State DisplayName="{quote_attr(sname)}"'
                f' sap2010:WorkflowViewState.IdRef="State_{sref}"'
                f' x:Name="__StateRef{sref}">'
                f'{entry_xml}{trans_xml}\n'
                f'</State>'
            )

    body = "\n".join(indent(s) for s in state_parts)

    initial = ""
    if state_refs:
        initial = f' InitialState="{{x:Reference __StateRef{state_refs[0]}}}"'

    result = (
        f'<StateMachine DisplayName="{quote_attr(display_name)}"'
        f' sap2010:WorkflowViewState.IdRef="StateMachine_{ref}"'
        f'{initial}>\n'
        f'{body}\n'
        f'</StateMachine>'
    )

    # Resolve placeholder references
    for i in range(len(states)):
        if i < len(state_refs):
            result = result.replace(
                f'__StateRef_placeholder_{i}',
                f'__StateRef{state_refs[i]}',
            )

    return result


def gen_parallel(
    branches: list[str],
    display_name: str = "Parallel",
) -> str:
    """Generate ``<Parallel>`` activity XAML."""
    ref = unique_id()
    branch_xml = "\n".join(indent(b) for b in branches)
    return (
        f'<Parallel DisplayName="{quote_attr(display_name)}"'
        f' sap2010:WorkflowViewState.IdRef="Parallel_{ref}">\n'
        f'{branch_xml}\n'
        f'</Parallel>'
    )


def gen_parallel_foreach(
    collection: str,
    item_type: str,
    body: str,
    display_name: str = "Parallel For Each",
) -> str:
    """Generate ``<ParallelForEach>`` activity XAML."""
    ref = unique_id()
    return (
        f'<ParallelForEach x:TypeArguments="{quote_attr(item_type)}"'
        f' Values="[{quote_attr(collection)}]"'
        f' DisplayName="{quote_attr(display_name)}"'
        f' sap2010:WorkflowViewState.IdRef="ParallelForEach_{ref}">\n'
        f'  <ActivityAction x:TypeArguments="{quote_attr(item_type)}">\n'
        f'    <ActivityAction.Argument>\n'
        f'      <DelegateInArgument x:TypeArguments="{quote_attr(item_type)}"'
        f' Name="item" />\n'
        f'    </ActivityAction.Argument>\n'
        f'{indent(body, 2)}\n'
        f'  </ActivityAction>\n'
        f'</ParallelForEach>'
    )


# ---------------------------------------------------------------------------
# Registration
# ---------------------------------------------------------------------------

register_generator("if", gen_if, "If", "Control Flow",
                   "Conditional branch based on a Boolean expression")
register_generator("if_else_if", gen_if_else_if, "If-ElseIf", "Control Flow",
                   "Chained conditional branches (If / ElseIf / Else)")
register_generator("foreach", gen_foreach, "For Each", "Control Flow",
                   "Iterate over a typed collection")
register_generator("foreach_row", gen_foreach_row, "For Each Row", "Control Flow",
                   "Iterate over DataTable rows")
register_generator("foreach_file", gen_foreach_file, "For Each File", "Control Flow",
                   "Iterate over files in a directory")
register_generator("while", gen_while, "While", "Control Flow",
                   "Loop while a condition is true")
register_generator("do_while", gen_do_while, "Do While", "Control Flow",
                   "Loop at least once, then while a condition is true")
register_generator("switch", gen_switch, "Switch", "Control Flow",
                   "Multi-branch switch on an expression")
register_generator("flowchart", gen_flowchart, "Flowchart", "Control Flow",
                   "Flowchart with steps and decisions")
register_generator("state_machine", gen_state_machine, "State Machine", "Control Flow",
                   "State machine with states and transitions")
register_generator("parallel", gen_parallel, "Parallel", "Control Flow",
                   "Execute branches in parallel")
register_generator("parallel_foreach", gen_parallel_foreach, "Parallel For Each",
                   "Control Flow", "Iterate over a collection in parallel")
