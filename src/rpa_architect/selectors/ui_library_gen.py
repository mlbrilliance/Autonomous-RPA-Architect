"""UI Library project generation for UiPath.

Produces a standalone UI Library project containing a ``project.json`` with
``projectType: UILibrary`` and a ``.objects/`` directory that follows the v2
hierarchical schema.
"""

from __future__ import annotations

import json
import uuid

from rpa_architect.selectors.object_repository import ObjectRepositoryScreenV2


def generate_ui_library(
    app_name: str,
    version: str,
    screens: list[ObjectRepositoryScreenV2],
) -> dict[str, str]:
    """Generate a UI Library project (separate project.json + .objects/).

    Args:
        app_name: Application name for the library.
        version: Application / library version string.
        screens: List of v2 screen definitions containing elements.

    Returns:
        Dictionary of file_path -> file_content strings.
    """
    files: dict[str, str] = {}

    # -- project.json -------------------------------------------------------
    project_meta = {
        "name": f"{app_name}_UILibrary",
        "projectId": str(uuid.uuid4()),
        "projectVersion": version,
        "description": f"UI Library for {app_name} v{version}",
        "projectType": "UILibrary",
        "targetFramework": "Portable",
        "schemaVersion": "2.0",
        "studioVersion": "2025.10.0",
        "dependencies": {
            "UiPath.UIAutomationNext.Activities": "[25.10.0]",
        },
        "runtimeOptions": {
            "autoDispose": False,
            "netFrameworkLazyLoading": False,
        },
    }
    files["project.json"] = json.dumps(project_meta, indent=2)

    # -- .objects/ structure -------------------------------------------------
    descriptor: dict = {
        "schemaVersion": "2.0",
        "projectName": f"{app_name}_UILibrary",
        "applications": [
            {
                "name": app_name,
                "version": version,
                "type": "web",
                "screens": [],
            }
        ],
    }

    for screen in screens:
        screen_dir = f"{app_name}/{version}/{screen.name}/"
        descriptor["applications"][0]["screens"].append(
            {
                "name": screen.name,
                "file": screen_dir,
                "elementCount": len(screen.elements),
            }
        )

        for elem in screen.elements:
            safe_name = elem.display_name.replace(" ", "_")
            elem_path = f".objects/{app_name}/{version}/{screen.name}/{safe_name}.json"
            elem_data = {
                "elementId": elem.element_id,
                "displayName": elem.display_name,
                "selectorXml": elem.selector_xml,
                "windowSelector": elem.window_selector,
                "uiFramework": elem.ui_framework,
                "variables": elem.variables,
            }
            files[elem_path] = json.dumps(elem_data, indent=2)

    files[".objects/descriptor.json"] = json.dumps(descriptor, indent=2)

    return files
