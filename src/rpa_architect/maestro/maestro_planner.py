"""Mode detection and Maestro planning for process orchestration."""

from __future__ import annotations

import logging
from typing import Any

from pydantic import BaseModel, Field

from rpa_architect.config import GenerationMode
from rpa_architect.ir.schema import ProcessIR, Step

logger = logging.getLogger("rpa_architect.maestro.planner")

# Step types that indicate human involvement.
_HUMAN_STEP_TYPES = {"decision"}
_HUMAN_KEYWORDS = {"approve", "approval", "review", "manual", "human", "sign off", "escalat"}

# Step types that indicate purely automated transactional work.
_AUTOMATED_STEP_TYPES = {
    "open_application",
    "login_sequence",
    "ui_flow",
    "data_operation",
    "close_application",
    "navigate",
    "extract_data",
    "transform_data",
}

# Keywords indicating a step should be handled by an AI agent node.
_AGENT_KEYWORDS = {
    "classify", "classification", "categorize", "categorise",
    "extract", "parse", "interpret", "summarize", "summarise",
    "generate", "compose", "draft", "write",
    "decide", "evaluate", "assess", "judge",
    "research", "analyze", "analyse", "investigate",
    "natural language", "nlp", "sentiment", "unstructured",
}

# Step types suited to agent handling.
_AGENT_STEP_TYPES = {"classification", "extraction", "generation", "analysis"}


class BpmnTaskDef(BaseModel):
    """A task to be rendered in the BPMN diagram."""

    task_id: str = Field(description="Unique BPMN task identifier.")
    name: str = Field(description="Human-readable task name.")
    task_type: str = Field(
        description="BPMN task type: serviceTask, userTask, businessRuleTask, agentTask."
    )
    step_refs: list[str] = Field(
        default_factory=list,
        description="IR step IDs covered by this task.",
    )
    metadata: dict[str, Any] = Field(default_factory=dict)


class AgentTaskDef(BpmnTaskDef):
    """An AI agent task embedded within a Maestro workflow.

    Agent tasks handle ambiguous, NL-heavy, or classification work
    that resists deterministic rules — the hybrid pattern.
    """

    agent_type: str = Field(
        default="general",
        description="Agent specialization: classification, extraction, decision, generation, research.",
    )
    llm_model: str = Field(
        default="",
        description="Preferred LLM model for this agent node (empty = platform default).",
    )
    guardrails: list[str] = Field(
        default_factory=list,
        description="Validation rules the agent output must pass before proceeding.",
    )
    fallback_to_human: bool = Field(
        default=True,
        description="Route to human review if agent confidence is below threshold.",
    )
    confidence_threshold: float = Field(
        default=0.8,
        ge=0.0,
        le=1.0,
        description="Minimum confidence to proceed without human review.",
    )


class DmnDecisionDef(BaseModel):
    """A DMN decision table reference."""

    decision_id: str = Field(description="Unique decision identifier.")
    name: str = Field(description="Decision name.")
    rule_refs: list[str] = Field(
        default_factory=list,
        description="IR BusinessRule IDs included in this table.",
    )


class ReframeworkSubproject(BaseModel):
    """A sub-project to be generated in REFramework style."""

    name: str
    transaction_ref: str
    step_refs: list[str] = Field(default_factory=list)


class MaestroPlan(BaseModel):
    """Complete plan for Maestro-based generation."""

    bpmn_tasks: list[BpmnTaskDef] = Field(default_factory=list)
    dmn_decisions: list[DmnDecisionDef] = Field(default_factory=list)
    reframework_subprojects: list[ReframeworkSubproject] = Field(default_factory=list)
    user_tasks: list[BpmnTaskDef] = Field(default_factory=list)


# ------------------------------------------------------------------
# Detection helpers
# ------------------------------------------------------------------


def _has_human_steps(ir: ProcessIR) -> bool:
    """Return True if any transaction step involves human interaction."""
    for txn in ir.transactions:
        for step in txn.steps:
            if _step_is_human(step):
                return True
    return False


def _step_is_human(step: Step) -> bool:
    if step.type in _HUMAN_STEP_TYPES:
        return True
    description = (step.description or "").lower()
    if any(kw in description for kw in _HUMAN_KEYWORDS):
        return True
    for sub in step.substeps:
        if _step_is_human(sub):
            return True
    return False


def _has_multiple_actors(ir: ProcessIR) -> bool:
    """Return True if more than one system or actor type is involved."""
    system_names = {s.name for s in ir.systems}
    return len(system_names) > 1


def _step_is_agent_candidate(step: Step) -> str | None:
    """Return the agent type if this step is best handled by an AI agent, else None."""
    if step.type in _AGENT_STEP_TYPES:
        type_map = {
            "classification": "classification",
            "extraction": "extraction",
            "generation": "generation",
            "analysis": "research",
        }
        return type_map.get(step.type, "general")

    description = (step.description or "").lower()
    for kw in _AGENT_KEYWORDS:
        if kw in description:
            if kw in ("classify", "classification", "categorize", "categorise"):
                return "classification"
            if kw in ("extract", "parse", "interpret"):
                return "extraction"
            if kw in ("generate", "compose", "draft", "write"):
                return "generation"
            if kw in ("decide", "evaluate", "assess", "judge"):
                return "decision"
            if kw in ("research", "analyze", "analyse", "investigate"):
                return "research"
            return "general"
    return None


def _is_single_system_transactional(ir: ProcessIR) -> bool:
    """Return True if the process is single-system and purely transactional."""
    if len(ir.systems) > 1:
        return False
    if ir.process_type != "transactional":
        return False
    for txn in ir.transactions:
        for step in txn.steps:
            if _step_is_human(step):
                return False
    return True


# ------------------------------------------------------------------
# Public API
# ------------------------------------------------------------------


def detect_mode(ir: ProcessIR) -> GenerationMode:
    """Determine the appropriate generation mode for a process.

    Decision logic:

    * **reframework** — single-system, transactional, no human steps.
    * **maestro** — human approval steps *or* multiple actor types.
    * **hybrid** — multiple actors *and* a transactional core.

    Args:
        ir: The parsed process intermediate representation.

    Returns:
        A :class:`GenerationMode` enum value (never ``AUTO``).
    """
    has_human = _has_human_steps(ir)
    multi_actor = _has_multiple_actors(ir)
    single_txn = _is_single_system_transactional(ir)

    if single_txn and not has_human:
        logger.info("Detected mode: reframework (single-system transactional)")
        return GenerationMode.REFRAMEWORK

    if has_human or multi_actor:
        if multi_actor and ir.process_type == "transactional":
            logger.info("Detected mode: hybrid (multi-actor transactional)")
            return GenerationMode.HYBRID
        logger.info("Detected mode: maestro (human steps or multi-actor)")
        return GenerationMode.MAESTRO

    logger.info("Detected mode: reframework (default)")
    return GenerationMode.REFRAMEWORK


def plan_maestro(ir: ProcessIR) -> MaestroPlan:
    """Generate a :class:`MaestroPlan` from the process IR.

    Walks every transaction and classifies each step into BPMN service tasks,
    user tasks, or business-rule tasks.  Business rules with routing outcomes
    are collected into DMN decision tables.

    If ``ir.document_understanding`` is set, a Document Understanding service
    task and a Document Validation user task (Action Center) are prepended to
    the plan, with the user task gated on the configured confidence threshold.

    Args:
        ir: The parsed process intermediate representation.

    Returns:
        A fully populated :class:`MaestroPlan`.
    """
    bpmn_tasks: list[BpmnTaskDef] = []
    user_tasks: list[BpmnTaskDef] = []
    dmn_decisions: list[DmnDecisionDef] = []
    reframework_subs: list[ReframeworkSubproject] = []
    task_counter = 0

    # Document Understanding block: serviceTask + userTask validation gate.
    if ir.document_understanding is not None and ir.document_understanding.enabled:
        task_counter += 1
        du_task_id = f"Task_{task_counter}"
        bpmn_tasks.append(
            BpmnTaskDef(
                task_id=du_task_id,
                name="Document Understanding",
                task_type="serviceTask",
                step_refs=[],
                metadata={
                    "binding_type": "document_understanding",
                    "extraction_endpoint": ir.document_understanding.extraction_endpoint,
                    "document_type": ir.document_understanding.document_type,
                    "confidence_threshold": ir.document_understanding.confidence_threshold,
                },
            )
        )
        task_counter += 1
        user_tasks.append(
            BpmnTaskDef(
                task_id=f"Task_{task_counter}",
                name="Document Validation",
                task_type="userTask",
                step_refs=[],
                metadata={
                    "binding_type": "action_center",
                    "gated_on": f"confidence < {ir.document_understanding.confidence_threshold}",
                    "after_task": du_task_id,
                },
            )
        )

    for txn in ir.transactions:
        automated_step_ids: list[str] = []

        # Classify steps.
        for step in txn.steps:
            task_counter += 1
            tid = f"Task_{task_counter}"

            if _step_is_human(step):
                user_tasks.append(
                    BpmnTaskDef(
                        task_id=tid,
                        name=step.description or f"User Task {step.id}",
                        task_type="userTask",
                        step_refs=[step.id],
                    )
                )
            elif (agent_type := _step_is_agent_candidate(step)) is not None:
                bpmn_tasks.append(
                    AgentTaskDef(
                        task_id=tid,
                        name=step.description or f"Agent Task {step.id}",
                        task_type="agentTask",
                        step_refs=[step.id],
                        agent_type=agent_type,
                        fallback_to_human=True,
                        metadata={"binding_type": "agent_node"},
                    )
                )
            elif step.type == "api_call":
                bpmn_tasks.append(
                    BpmnTaskDef(
                        task_id=tid,
                        name=step.description or f"API Call {step.id}",
                        task_type="serviceTask",
                        step_refs=[step.id],
                        metadata={"binding_type": "api_workflow"},
                    )
                )
            else:
                bpmn_tasks.append(
                    BpmnTaskDef(
                        task_id=tid,
                        name=step.description or f"Service Task {step.id}",
                        task_type="serviceTask",
                        step_refs=[step.id],
                        metadata={"binding_type": "rpa_workflow"},
                    )
                )
                automated_step_ids.append(step.id)

        # Collect business rules into DMN decisions.
        routing_rules = [r for r in txn.business_rules if r.outcome in ("route", "escalate")]
        if routing_rules:
            dmn_decisions.append(
                DmnDecisionDef(
                    decision_id=f"Decision_{txn.name}",
                    name=f"{txn.name} Routing Rules",
                    rule_refs=[r.id for r in routing_rules],
                )
            )
            task_counter += 1
            bpmn_tasks.append(
                BpmnTaskDef(
                    task_id=f"Task_{task_counter}",
                    name=f"Evaluate {txn.name} Rules",
                    task_type="businessRuleTask",
                    step_refs=[],
                    metadata={"decision_ref": f"Decision_{txn.name}"},
                )
            )

        # Automated steps that form a transactional block get a REFramework sub-project.
        if automated_step_ids:
            reframework_subs.append(
                ReframeworkSubproject(
                    name=f"{txn.name}_Automation",
                    transaction_ref=txn.name,
                    step_refs=automated_step_ids,
                )
            )

    plan = MaestroPlan(
        bpmn_tasks=bpmn_tasks,
        dmn_decisions=dmn_decisions,
        reframework_subprojects=reframework_subs,
        user_tasks=user_tasks,
    )
    logger.info(
        "Maestro plan: %d BPMN tasks, %d user tasks, %d DMN decisions, %d subprojects",
        len(bpmn_tasks),
        len(user_tasks),
        len(dmn_decisions),
        len(reframework_subs),
    )
    return plan
