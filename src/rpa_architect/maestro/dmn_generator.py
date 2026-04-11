"""DMN 1.3 decision table generation from IR business rules."""

from __future__ import annotations

import xml.etree.ElementTree as ET

from pydantic import BaseModel, Field

from rpa_architect.ir.schema import BusinessRule

_DMN_NS = "https://www.omg.org/spec/DMN/20191111/MODEL/"
_DMNDI_NS = "https://www.omg.org/spec/DMN/20191111/DMNDI/"
_DC_NS = "http://www.omg.org/spec/DMN/20180521/DC/"
_FEEL_NS = "https://www.omg.org/spec/DMN/20191111/FEEL/"

# ------------------------------------------------------------------
# Models
# ------------------------------------------------------------------


class DecisionInput(BaseModel):
    """An input column in a DMN decision table."""

    id: str
    label: str
    type_ref: str = "string"
    expression: str = ""


class DecisionOutput(BaseModel):
    """An output column in a DMN decision table."""

    id: str
    label: str
    type_ref: str = "string"


class DecisionRule(BaseModel):
    """A single row in a DMN decision table."""

    id: str
    input_entries: list[str] = Field(default_factory=list)
    output_entries: list[str] = Field(default_factory=list)
    annotation: str = ""


class DecisionTable(BaseModel):
    """Full DMN decision table definition."""

    name: str
    inputs: list[DecisionInput] = Field(default_factory=list)
    outputs: list[DecisionOutput] = Field(default_factory=list)
    rules: list[DecisionRule] = Field(default_factory=list)


# ------------------------------------------------------------------
# Mapping helpers
# ------------------------------------------------------------------


def _rules_to_table(business_rules: list[BusinessRule], decision_name: str) -> DecisionTable:
    """Convert a list of :class:`BusinessRule` into a :class:`DecisionTable`."""
    table = DecisionTable(name=decision_name)

    # We always have at least one input (condition) and one output (outcome).
    table.inputs.append(
        DecisionInput(
            id="Input_condition",
            label="Condition",
            type_ref="string",
            expression="condition",
        )
    )
    table.outputs.append(
        DecisionOutput(id="Output_outcome", label="Outcome", type_ref="string")
    )

    # If any rule has route parameters, add a second output.
    has_route = any(r.parameters.get("route_to") for r in business_rules)
    if has_route:
        table.outputs.append(
            DecisionOutput(id="Output_route", label="Route To", type_ref="string")
        )

    for idx, rule in enumerate(business_rules, start=1):
        input_entries = [f'"{rule.condition}"']
        output_entries = [f'"{rule.outcome}"']
        if has_route:
            output_entries.append(f'"{rule.parameters.get("route_to", "")}"')

        table.rules.append(
            DecisionRule(
                id=f"Rule_{idx}",
                input_entries=input_entries,
                output_entries=output_entries,
                annotation=rule.reason or "",
            )
        )

    return table


# ------------------------------------------------------------------
# XML serialisation
# ------------------------------------------------------------------


def generate_dmn(business_rules: list[BusinessRule], decision_name: str) -> str:
    """Generate a DMN 1.3 XML document containing a decision table.

    Args:
        business_rules: List of IR business rules.
        decision_name: Name for the DMN decision element.

    Returns:
        A string containing valid DMN 1.3 XML.
    """
    table = _rules_to_table(business_rules, decision_name)

    ET.register_namespace("", _DMN_NS)
    ET.register_namespace("dmndi", _DMNDI_NS)
    ET.register_namespace("dc", _DC_NS)
    ET.register_namespace("feel", _FEEL_NS)

    root = ET.Element(f"{{{_DMN_NS}}}definitions")
    root.set("id", "Definitions_1")
    root.set("name", decision_name)
    root.set("namespace", _DMN_NS)

    # Decision element
    decision_el = ET.SubElement(root, f"{{{_DMN_NS}}}decision")
    decision_el.set("id", f"Decision_{decision_name.replace(' ', '_')}")
    decision_el.set("name", decision_name)

    # Decision table
    dt_el = ET.SubElement(decision_el, f"{{{_DMN_NS}}}decisionTable")
    dt_el.set("id", f"DecisionTable_{decision_name.replace(' ', '_')}")
    dt_el.set("hitPolicy", "FIRST")

    # Inputs
    for inp in table.inputs:
        inp_el = ET.SubElement(dt_el, f"{{{_DMN_NS}}}input")
        inp_el.set("id", inp.id)
        inp_el.set("label", inp.label)
        expr_el = ET.SubElement(inp_el, f"{{{_DMN_NS}}}inputExpression")
        expr_el.set("id", f"{inp.id}_expr")
        expr_el.set("typeRef", inp.type_ref)
        text_el = ET.SubElement(expr_el, f"{{{_DMN_NS}}}text")
        text_el.text = inp.expression

    # Outputs
    for out in table.outputs:
        out_el = ET.SubElement(dt_el, f"{{{_DMN_NS}}}output")
        out_el.set("id", out.id)
        out_el.set("label", out.label)
        out_el.set("typeRef", out.type_ref)

    # Rules
    for rule in table.rules:
        rule_el = ET.SubElement(dt_el, f"{{{_DMN_NS}}}rule")
        rule_el.set("id", rule.id)
        for entry_text in rule.input_entries:
            ie_el = ET.SubElement(rule_el, f"{{{_DMN_NS}}}inputEntry")
            ie_el.set("id", f"{rule.id}_ie_{rule.input_entries.index(entry_text)}")
            t_el = ET.SubElement(ie_el, f"{{{_DMN_NS}}}text")
            t_el.text = entry_text
        for entry_text in rule.output_entries:
            oe_el = ET.SubElement(rule_el, f"{{{_DMN_NS}}}outputEntry")
            oe_el.set("id", f"{rule.id}_oe_{rule.output_entries.index(entry_text)}")
            t_el = ET.SubElement(oe_el, f"{{{_DMN_NS}}}text")
            t_el.text = entry_text
        if rule.annotation:
            desc_el = ET.SubElement(rule_el, f"{{{_DMN_NS}}}description")
            desc_el.text = rule.annotation

    ET.indent(root, space="  ")
    return ET.tostring(root, encoding="unicode", xml_declaration=True)
