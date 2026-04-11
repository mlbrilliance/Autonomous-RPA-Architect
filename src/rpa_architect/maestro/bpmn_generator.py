"""BPMN 2.0 XML generation from ProcessIR and task bindings."""

from __future__ import annotations

import xml.etree.ElementTree as ET

from pydantic import BaseModel, Field

from rpa_architect.ir.schema import ProcessIR
from rpa_architect.maestro.service_task_binder import TaskBinding

# ------------------------------------------------------------------
# BPMN element models
# ------------------------------------------------------------------

_BPMN_NS = "http://www.omg.org/spec/BPMN/20100524/MODEL"
_BPMNDI_NS = "http://www.omg.org/spec/BPMN/20100524/DI"
_DC_NS = "http://www.omg.org/spec/DD/20100524/DC"
_DI_NS = "http://www.omg.org/spec/DD/20100524/DI"
_XSI_NS = "http://www.w3.org/2001/XMLSchema-instance"


class BpmnElement(BaseModel):
    """Base for all BPMN element models."""

    id: str
    name: str = ""


class StartEvent(BpmnElement):
    pass


class EndEvent(BpmnElement):
    pass


class ServiceTask(BpmnElement):
    implementation: str = ""


class UserTask(BpmnElement):
    assignee: str = ""


class BusinessRuleTask(BpmnElement):
    decision_ref: str = ""


class ExclusiveGateway(BpmnElement):
    pass


class ParallelGateway(BpmnElement):
    pass


class SequenceFlow(BpmnElement):
    source_ref: str
    target_ref: str
    condition: str | None = None


class AgentTask(BpmnElement):
    """AI agent task rendered as a service task with agent:// implementation."""
    implementation: str = ""
    agent_type: str = ""
    guardrails: list[str] = Field(default_factory=list)
    fallback_to_human: bool = True


class ErrorBoundaryEvent(BpmnElement):
    attached_to: str
    error_ref: str = ""


class BpmnProcess(BaseModel):
    """Container for a full BPMN process definition."""

    id: str
    name: str
    start_events: list[StartEvent] = Field(default_factory=list)
    end_events: list[EndEvent] = Field(default_factory=list)
    service_tasks: list[ServiceTask] = Field(default_factory=list)
    user_tasks: list[UserTask] = Field(default_factory=list)
    business_rule_tasks: list[BusinessRuleTask] = Field(default_factory=list)
    agent_tasks: list[AgentTask] = Field(default_factory=list)
    exclusive_gateways: list[ExclusiveGateway] = Field(default_factory=list)
    parallel_gateways: list[ParallelGateway] = Field(default_factory=list)
    sequence_flows: list[SequenceFlow] = Field(default_factory=list)
    error_boundary_events: list[ErrorBoundaryEvent] = Field(default_factory=list)


# ------------------------------------------------------------------
# Builder helpers
# ------------------------------------------------------------------


def _build_process(ir: ProcessIR, task_bindings: list[TaskBinding]) -> BpmnProcess:
    """Translate IR + bindings into a :class:`BpmnProcess`."""
    from rpa_architect.maestro.maestro_planner import plan_maestro

    plan = plan_maestro(ir)
    proc = BpmnProcess(id=f"Process_{ir.process_name}", name=ir.process_name)

    # Start / End
    proc.start_events.append(StartEvent(id="StartEvent_1", name="Start"))
    proc.end_events.append(EndEvent(id="EndEvent_1", name="End"))

    binding_map: dict[str, TaskBinding] = {b.task_id: b for b in task_bindings}

    prev_id = "StartEvent_1"
    flow_counter = 0

    # Service / user / business-rule tasks from the plan.
    all_tasks = plan.bpmn_tasks + plan.user_tasks
    all_tasks.sort(key=lambda t: t.task_id)

    for task_def in all_tasks:
        if task_def.task_type == "agentTask":
            from rpa_architect.maestro.maestro_planner import AgentTaskDef

            agent_def = task_def if isinstance(task_def, AgentTaskDef) else None
            proc.agent_tasks.append(
                AgentTask(
                    id=task_def.task_id,
                    name=task_def.name,
                    implementation=f"agent://{agent_def.agent_type if agent_def else 'general'}",
                    agent_type=agent_def.agent_type if agent_def else "general",
                    guardrails=agent_def.guardrails if agent_def else [],
                    fallback_to_human=agent_def.fallback_to_human if agent_def else True,
                )
            )
        elif task_def.task_type == "serviceTask":
            binding = binding_map.get(task_def.task_id)
            proc.service_tasks.append(
                ServiceTask(
                    id=task_def.task_id,
                    name=task_def.name,
                    implementation=binding.target_name if binding else "",
                )
            )
        elif task_def.task_type == "userTask":
            proc.user_tasks.append(
                UserTask(id=task_def.task_id, name=task_def.name)
            )
        elif task_def.task_type == "businessRuleTask":
            proc.business_rule_tasks.append(
                BusinessRuleTask(
                    id=task_def.task_id,
                    name=task_def.name,
                    decision_ref=task_def.metadata.get("decision_ref", ""),
                )
            )

        # Connect with a sequence flow.
        flow_counter += 1
        proc.sequence_flows.append(
            SequenceFlow(
                id=f"Flow_{flow_counter}",
                name="",
                source_ref=prev_id,
                target_ref=task_def.task_id,
            )
        )
        prev_id = task_def.task_id

    # Exclusive gateways for business rules with routing.
    for txn in ir.transactions:
        routing_rules = [r for r in txn.business_rules if r.outcome in ("route", "escalate")]
        if routing_rules:
            gw_id = f"Gateway_{txn.name}"
            proc.exclusive_gateways.append(
                ExclusiveGateway(id=gw_id, name=f"{txn.name} Decision")
            )
            flow_counter += 1
            proc.sequence_flows.append(
                SequenceFlow(
                    id=f"Flow_{flow_counter}",
                    source_ref=prev_id,
                    target_ref=gw_id,
                )
            )
            for rule in routing_rules:
                target = rule.parameters.get("route_to", "EndEvent_1")
                flow_counter += 1
                proc.sequence_flows.append(
                    SequenceFlow(
                        id=f"Flow_{flow_counter}",
                        source_ref=gw_id,
                        target_ref=target,
                        condition=rule.condition,
                    )
                )
            prev_id = gw_id

    # Error boundary events for exception categories.
    for exc in ir.exception_categories:
        if exc.type == "system" and proc.service_tasks:
            attached = proc.service_tasks[0].id
            proc.error_boundary_events.append(
                ErrorBoundaryEvent(
                    id=f"BoundaryError_{exc.name}",
                    name=exc.name,
                    attached_to=attached,
                    error_ref=exc.name,
                )
            )

    # Final flow to end event.
    flow_counter += 1
    proc.sequence_flows.append(
        SequenceFlow(
            id=f"Flow_{flow_counter}",
            source_ref=prev_id,
            target_ref="EndEvent_1",
        )
    )

    return proc


# ------------------------------------------------------------------
# XML serialisation
# ------------------------------------------------------------------


def _add_element(parent: ET.Element, tag: str, attribs: dict[str, str]) -> ET.Element:
    """Create a sub-element with the BPMN namespace."""
    el = ET.SubElement(parent, f"{{{_BPMN_NS}}}{tag}")
    for k, v in attribs.items():
        el.set(k, v)
    return el


def generate_bpmn(ir: ProcessIR, task_bindings: list[TaskBinding]) -> str:
    """Generate a BPMN 2.0 XML document.

    Args:
        ir: The process intermediate representation.
        task_bindings: Service task binding details.

    Returns:
        A string containing valid BPMN 2.0 XML.
    """
    proc = _build_process(ir, task_bindings)

    # Register namespaces for clean output.
    ET.register_namespace("bpmn", _BPMN_NS)
    ET.register_namespace("bpmndi", _BPMNDI_NS)
    ET.register_namespace("dc", _DC_NS)
    ET.register_namespace("di", _DI_NS)
    ET.register_namespace("xsi", _XSI_NS)

    root = ET.Element(f"{{{_BPMN_NS}}}definitions")
    root.set("id", "Definitions_1")
    root.set("targetNamespace", "http://bpmn.io/schema/bpmn")
    # Note: xmlns:xsi is auto-emitted by ET because xsi is registered above and
    # used in conditionExpression elements when routing rules are present.
    # Setting it manually here would cause a duplicate attribute on output.

    process_el = _add_element(root, "process", {
        "id": proc.id,
        "name": proc.name,
        "isExecutable": "true",
    })

    # Start events
    for se in proc.start_events:
        _add_element(process_el, "startEvent", {"id": se.id, "name": se.name})

    # Service tasks
    for st in proc.service_tasks:
        attrs: dict[str, str] = {"id": st.id, "name": st.name}
        if st.implementation:
            attrs["implementation"] = st.implementation
        _add_element(process_el, "serviceTask", attrs)

    # User tasks
    for ut in proc.user_tasks:
        attrs = {"id": ut.id, "name": ut.name}
        if ut.assignee:
            attrs["assignee"] = ut.assignee
        _add_element(process_el, "userTask", attrs)

    # Business rule tasks
    for brt in proc.business_rule_tasks:
        attrs = {"id": brt.id, "name": brt.name}
        if brt.decision_ref:
            attrs["decisionRef"] = brt.decision_ref
        _add_element(process_el, "businessRuleTask", attrs)

    # Agent tasks (rendered as service tasks with agent:// implementation + extensions)
    for at in proc.agent_tasks:
        attrs: dict[str, str] = {"id": at.id, "name": at.name}
        if at.implementation:
            attrs["implementation"] = at.implementation
        agent_el = _add_element(process_el, "serviceTask", attrs)
        # Add extension elements for agent configuration
        ext_el = ET.SubElement(agent_el, f"{{{_BPMN_NS}}}extensionElements")
        agent_config = ET.SubElement(ext_el, "agentConfiguration")
        agent_config.set("agentType", at.agent_type)
        agent_config.set("fallbackToHuman", str(at.fallback_to_human).lower())
        for guard in at.guardrails:
            guard_el = ET.SubElement(agent_config, "guardrail")
            guard_el.text = guard

    # Exclusive gateways
    for gw in proc.exclusive_gateways:
        _add_element(process_el, "exclusiveGateway", {"id": gw.id, "name": gw.name})

    # Parallel gateways
    for gw in proc.parallel_gateways:
        _add_element(process_el, "parallelGateway", {"id": gw.id, "name": gw.name})

    # Sequence flows
    for sf in proc.sequence_flows:
        attrs = {"id": sf.id, "sourceRef": sf.source_ref, "targetRef": sf.target_ref}
        if sf.name:
            attrs["name"] = sf.name
        flow_el = _add_element(process_el, "sequenceFlow", attrs)
        if sf.condition:
            cond_el = ET.SubElement(flow_el, f"{{{_BPMN_NS}}}conditionExpression")
            cond_el.set(f"{{{_XSI_NS}}}type", "bpmn:tFormalExpression")
            cond_el.text = sf.condition

    # Error boundary events
    for ebe in proc.error_boundary_events:
        be_el = _add_element(process_el, "boundaryEvent", {
            "id": ebe.id,
            "name": ebe.name,
            "attachedToRef": ebe.attached_to,
        })
        err_def = ET.SubElement(be_el, f"{{{_BPMN_NS}}}errorEventDefinition")
        if ebe.error_ref:
            err_def.set("errorRef", ebe.error_ref)

    # End events
    for ee in proc.end_events:
        _add_element(process_el, "endEvent", {"id": ee.id, "name": ee.name})

    ET.indent(root, space="  ")
    return ET.tostring(root, encoding="unicode", xml_declaration=True)
