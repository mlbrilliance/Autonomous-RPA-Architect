"""Tests for Maestro mode detection and planning."""

from __future__ import annotations

from rpa_architect.config import GenerationMode
from rpa_architect.ir.schema import (
    DataContract,
    DataField,
    ProcessIR,
    Step,
    SystemInfo,
    Transaction,
    UIAction,
)
from rpa_architect.maestro.maestro_planner import detect_mode, plan_maestro


def _make_ir(
    systems: list[SystemInfo] | None = None,
    steps: list[Step] | None = None,
    process_type: str = "transactional",
) -> ProcessIR:
    if systems is None:
        systems = [SystemInfo(name="WebApp", type="web")]
    if steps is None:
        steps = [
            Step(
                id="s1",
                type="ui_flow",
                description="Navigate and extract data",
                actions=[UIAction(action="click", target="Submit")],
            )
        ]
    return ProcessIR(
        process_name="TestProcess",
        process_type=process_type,
        description="Test process",
        systems=systems,
        credentials=[],
        transactions=[
            Transaction(
                name="TestTransaction",
                input_contract=DataContract(fields=[DataField(name="id", type="string")]),
                steps=steps,
                business_rules=[],
            )
        ],
        config={},
        exception_categories=[],
    )


class TestDetectReframeworkMode:
    def test_simple_single_system(self) -> None:
        """Single-system bot with no human steps should be REFramework."""
        ir = _make_ir(
            systems=[SystemInfo(name="WebApp", type="web")],
            steps=[
                Step(id="s1", type="open_application", description="Open web app", actions=[]),
                Step(id="s2", type="ui_flow", description="Extract data", actions=[]),
                Step(id="s3", type="close_application", description="Close app", actions=[]),
            ],
        )
        mode = detect_mode(ir)
        assert mode == GenerationMode.REFRAMEWORK


class TestDetectMaestroMode:
    def test_human_approval_step(self) -> None:
        """Process with human approval steps should be Maestro."""
        ir = _make_ir(
            steps=[
                Step(id="s1", type="ui_flow", description="Extract invoice data", actions=[]),
                Step(id="s2", type="decision", description="Manager approval required", actions=[]),
                Step(id="s3", type="ui_flow", description="Post to ERP", actions=[]),
            ],
        )
        mode = detect_mode(ir)
        assert mode == GenerationMode.MAESTRO

    def test_human_keyword_in_description(self) -> None:
        """Steps with human-related keywords should trigger Maestro."""
        ir = _make_ir(
            steps=[
                Step(id="s1", type="ui_flow", description="Manual review of document", actions=[]),
            ],
        )
        mode = detect_mode(ir)
        assert mode == GenerationMode.MAESTRO


class TestPlanMaestro:
    def test_plan_creates_tasks(self) -> None:
        ir = _make_ir(
            steps=[
                Step(id="s1", type="ui_flow", description="Extract data", actions=[]),
                Step(id="s2", type="decision", description="Approve invoice", actions=[]),
                Step(id="s3", type="api_call", description="Post to API", actions=[]),
            ],
        )
        plan = plan_maestro(ir)
        assert len(plan.bpmn_tasks) >= 2
        assert len(plan.user_tasks) >= 1

    def test_plan_creates_reframework_subprojects(self) -> None:
        ir = _make_ir(
            steps=[
                Step(id="s1", type="open_application", description="Open app", actions=[]),
                Step(id="s2", type="ui_flow", description="Process data", actions=[]),
                Step(id="s3", type="close_application", description="Close app", actions=[]),
            ],
        )
        plan = plan_maestro(ir)
        assert len(plan.reframework_subprojects) >= 1
