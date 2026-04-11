"""Framework wiring engine -- connects generated workflows into REFramework structure.

This module automatically wires custom business workflows into the UiPath
REFramework by inserting InvokeWorkflowFile activities, injecting shared
variables, and chaining argument flows between workflows.

Usage::

    from rpa_architect.wiring import wire_project

    result = wire_project("/path/to/uipath/project")
    for action in result.actions:
        print(f"  {action.action_type}: {action.detail}")
"""
from __future__ import annotations

from rpa_architect.wiring.invoke_linker import generate_invoke_workflow
from rpa_architect.wiring.variable_injector import inject_variables
from rpa_architect.wiring.wiring_engine import WiringResult, wire_project

__all__ = [
    "generate_invoke_workflow",
    "inject_variables",
    "wire_project",
    "WiringResult",
]
