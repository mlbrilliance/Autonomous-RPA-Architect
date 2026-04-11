"""Object Repository generation for UiPath projects.

Generates the .objects/ directory structure containing screen definitions
and a descriptor.json that maps element names to their selectors.

Supports both v1 (flat) and v2 (hierarchical Application > Version > Screen > Element)
schemas.  The v2 layout matches UiPath 2025.10 conventions.
"""

from __future__ import annotations

import json
import re
import uuid
from typing import Literal

from pydantic import BaseModel, Field

from rpa_architect.ir.schema import ProcessIR


class ObjectRepositoryEntry(BaseModel):
    """A single entry in the UiPath Object Repository."""

    screen_name: str = Field(description="Logical screen or page grouping.")
    element_name: str = Field(description="Unique element identifier within the screen.")
    selector_xml: str = Field(description="UiPath XML selector for the element.")
    ui_framework: Literal["default", "uia", "aa", "uia3"] = Field(
        default="default",
        description="UI automation framework to use.",
    )


def _build_screen_map(
    selectors: dict[str, str],
    ir: ProcessIR,
) -> dict[str, list[ObjectRepositoryEntry]]:
    """Group selectors into screens based on step system references.

    Elements are grouped by the system they interact with. If no system
    reference is available, they fall under a 'General' screen.
    """
    # Build a mapping from element_name prefix (step_id) to system_ref
    step_system_map: dict[str, str] = {}
    for transaction in ir.transactions:
        for step in transaction.steps:
            if step.system_ref:
                step_system_map[step.id] = step.system_ref

    # Determine UI framework from system type
    system_type_map: dict[str, str] = {}
    for system in ir.systems:
        system_type_map[system.name] = system.type

    screens: dict[str, list[ObjectRepositoryEntry]] = {}

    for element_name, selector_xml in selectors.items():
        # Extract step_id from element name (format: StepId_Target_idx)
        parts = element_name.split("_")
        step_id = parts[0] if parts else ""

        # Look up system reference
        system_ref = step_system_map.get(step_id, "General")
        screen_name = system_ref.replace(" ", "_")

        # Determine UI framework based on system type
        system_type = system_type_map.get(system_ref, "")
        if system_type == "web":
            ui_framework: Literal["default", "uia", "aa", "uia3"] = "default"
        elif system_type in ("desktop", "sap"):
            ui_framework = "uia"
        elif system_type == "mainframe":
            ui_framework = "aa"
        else:
            ui_framework = "default"

        entry = ObjectRepositoryEntry(
            screen_name=screen_name,
            element_name=element_name,
            selector_xml=selector_xml,
            ui_framework=ui_framework,
        )

        screens.setdefault(screen_name, []).append(entry)

    return screens


def generate_object_repository(
    ir: ProcessIR,
    selectors: dict[str, str],
) -> dict[str, str]:
    """Generate UiPath Object Repository files for the .objects/ directory.

    Produces a descriptor.json and per-screen definition files that UiPath
    Studio can load for element management.

    Args:
        ir: The ProcessIR describing the process.
        selectors: Dictionary of element_name -> selector_xml strings.

    Returns:
        Dictionary of file_path -> file_content for the .objects/ directory.
    """
    if not selectors:
        return {}

    screen_map = _build_screen_map(selectors, ir)
    files: dict[str, str] = {}

    # Build descriptor.json
    descriptor: dict = {
        "schemaVersion": "1.0",
        "projectName": ir.process_name,
        "screens": [],
    }

    for screen_name, entries in sorted(screen_map.items()):
        screen_file = f"{screen_name}.json"
        descriptor["screens"].append(
            {
                "name": screen_name,
                "file": screen_file,
                "elementCount": len(entries),
            }
        )

        # Build per-screen definition file
        screen_def: dict = {
            "name": screen_name,
            "elements": [],
        }
        for entry in sorted(entries, key=lambda e: e.element_name):
            screen_def["elements"].append(
                {
                    "name": entry.element_name,
                    "selector": entry.selector_xml,
                    "uiFramework": entry.ui_framework,
                }
            )

        files[f".objects/{screen_file}"] = json.dumps(screen_def, indent=2)

    files[".objects/descriptor.json"] = json.dumps(descriptor, indent=2)

    return files


# ---------------------------------------------------------------------------
# V2 hierarchical schema  (Application > Version > Screen > Element)
# ---------------------------------------------------------------------------

_VARIABLE_PATTERN = re.compile(r"\{\{(\w+)\}\}")


class ObjectRepositoryElementV2(BaseModel):
    """A single element in the v2 Object Repository."""

    element_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    display_name: str
    selector_xml: str
    window_selector: str = ""
    ui_framework: Literal["default", "uia", "aa", "uia3"] = "default"
    variables: dict[str, str] = Field(default_factory=dict)


class ObjectRepositoryScreenV2(BaseModel):
    """A screen (page / window) grouping elements."""

    name: str
    window_selector: str = ""
    elements: list[ObjectRepositoryElementV2] = Field(default_factory=list)


class ObjectRepositoryAppV2(BaseModel):
    """An application entry in the v2 Object Repository."""

    name: str
    version: str = "1.0"
    app_type: Literal["web", "desktop", "sap", "mainframe", "java"] = "web"
    screens: list[ObjectRepositoryScreenV2] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Variable helpers
# ---------------------------------------------------------------------------


def extract_selector_variables(selector_xml: str) -> list[str]:
    """Return variable names found as ``{{variable_name}}`` in *selector_xml*."""
    return _VARIABLE_PATTERN.findall(selector_xml)


def resolve_selector_variables(selector_xml: str, variables: dict[str, str]) -> str:
    """Replace ``{{var}}`` placeholders in *selector_xml* with values from *variables*."""

    def _replacer(match: re.Match) -> str:
        name = match.group(1)
        return variables.get(name, match.group(0))

    return _VARIABLE_PATTERN.sub(_replacer, selector_xml)


# ---------------------------------------------------------------------------
# V2 generation
# ---------------------------------------------------------------------------

_SYSTEM_TYPE_TO_APP_TYPE: dict[str, Literal["web", "desktop", "sap", "mainframe", "java"]] = {
    "web": "web",
    "desktop": "desktop",
    "sap": "sap",
    "mainframe": "mainframe",
    "java": "java",
}

_SYSTEM_TYPE_TO_UI_FRAMEWORK: dict[str, Literal["default", "uia", "aa", "uia3"]] = {
    "web": "default",
    "desktop": "uia",
    "sap": "uia",
    "mainframe": "aa",
    "java": "uia",
}


def _build_v2_apps(
    ir: ProcessIR,
    selectors: dict[str, str],
) -> list[ObjectRepositoryAppV2]:
    """Build the hierarchical app list from IR + selectors."""

    # Map step_id -> (system_name, system_type)
    step_system: dict[str, str] = {}
    for txn in ir.transactions:
        for step in txn.steps:
            if step.system_ref:
                step_system[step.id] = step.system_ref

    system_type_map: dict[str, str] = {s.name: s.type for s in ir.systems}

    # Collect elements per (app_name, screen_name)
    app_screens: dict[str, dict[str, list[ObjectRepositoryElementV2]]] = {}

    for element_name, selector_xml in selectors.items():
        parts = element_name.split("_")
        step_id = parts[0] if parts else ""

        app_name = step_system.get(step_id, "General")
        screen_name = app_name.replace(" ", "_")

        sys_type = system_type_map.get(app_name, "")
        ui_fw = _SYSTEM_TYPE_TO_UI_FRAMEWORK.get(sys_type, "default")

        variables_found = extract_selector_variables(selector_xml)
        var_dict = {v: "{{" + v + "}}" for v in variables_found}

        elem = ObjectRepositoryElementV2(
            display_name=element_name,
            selector_xml=selector_xml,
            ui_framework=ui_fw,
            variables=var_dict,
        )

        app_screens.setdefault(app_name, {}).setdefault(screen_name, []).append(elem)

    apps: list[ObjectRepositoryAppV2] = []
    for app_name in sorted(app_screens):
        sys_type = system_type_map.get(app_name, "")
        app_type = _SYSTEM_TYPE_TO_APP_TYPE.get(sys_type, "web")
        screens: list[ObjectRepositoryScreenV2] = []
        for scr_name in sorted(app_screens[app_name]):
            elems = sorted(app_screens[app_name][scr_name], key=lambda e: e.display_name)
            screens.append(ObjectRepositoryScreenV2(name=scr_name, elements=elems))
        apps.append(ObjectRepositoryAppV2(name=app_name, app_type=app_type, screens=screens))

    return apps


def generate_object_repository_v2(
    ir: ProcessIR,
    selectors: dict[str, str],
    schema_version: str = "2.0",
) -> dict[str, str]:
    """Generate v2 hierarchical Object Repository files.

    Output layout::

        .objects/
        ├── descriptor.json
        └── {AppName}/
            └── {Version}/
                └── {ScreenName}/
                    └── {ElementName}.json

    Args:
        ir: The ProcessIR describing the process.
        selectors: Dictionary of element_name -> selector_xml strings.
        schema_version: Schema version string for descriptor.json.

    Returns:
        Dictionary of file_path -> file_content for the .objects/ directory.
    """
    if not selectors:
        return {}

    apps = _build_v2_apps(ir, selectors)
    files: dict[str, str] = {}

    descriptor: dict = {
        "schemaVersion": schema_version,
        "projectName": ir.process_name,
        "applications": [],
    }

    for app in apps:
        app_descriptor: dict = {
            "name": app.name,
            "version": app.version,
            "type": app.app_type,
            "screens": [],
        }

        for screen in app.screens:
            screen_dir = f"{app.name}/{app.version}/{screen.name}/"
            app_descriptor["screens"].append(
                {
                    "name": screen.name,
                    "file": screen_dir,
                    "elementCount": len(screen.elements),
                }
            )

            for elem in screen.elements:
                safe_name = elem.display_name.replace(" ", "_")
                elem_path = f".objects/{app.name}/{app.version}/{screen.name}/{safe_name}.json"
                elem_data = {
                    "elementId": elem.element_id,
                    "displayName": elem.display_name,
                    "selectorXml": elem.selector_xml,
                    "windowSelector": elem.window_selector,
                    "uiFramework": elem.ui_framework,
                    "variables": elem.variables,
                }
                files[elem_path] = json.dumps(elem_data, indent=2)

        descriptor["applications"].append(app_descriptor)

    files[".objects/descriptor.json"] = json.dumps(descriptor, indent=2)

    return files


def generate_object_repository_v2_from_apps(
    apps: list[ObjectRepositoryAppV2],
    project_name: str = "Project",
    schema_version: str = "2.0",
) -> dict[str, str]:
    """Generate v2 Object Repository from pre-built application models.

    Convenience function for when you have apps already constructed
    rather than deriving them from IR + selectors.
    """
    files: dict[str, str] = {}

    descriptor: dict = {
        "schemaVersion": schema_version,
        "projectName": project_name,
        "applications": [],
    }

    for app in apps:
        app_descriptor: dict = {
            "name": app.name,
            "version": app.version,
            "type": app.app_type,
            "screens": [],
        }

        for screen in app.screens:
            screen_dir = f"{app.name}/{app.version}/{screen.name}/"
            app_descriptor["screens"].append(
                {
                    "name": screen.name,
                    "file": screen_dir,
                    "elementCount": len(screen.elements),
                }
            )

            for elem in screen.elements:
                safe_name = elem.display_name.replace(" ", "_")
                elem_path = f".objects/{app.name}/{app.version}/{screen.name}/{safe_name}.json"
                elem_data = {
                    "elementId": elem.element_id,
                    "displayName": elem.display_name,
                    "selectorXml": elem.selector_xml,
                    "windowSelector": elem.window_selector,
                    "uiFramework": elem.ui_framework,
                    "variables": elem.variables,
                }
                files[elem_path] = json.dumps(elem_data, indent=2)

        descriptor["applications"].append(app_descriptor)

    files[".objects/descriptor.json"] = json.dumps(descriptor, indent=2)

    return files
