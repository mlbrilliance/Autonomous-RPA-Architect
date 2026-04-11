"""project.json generation for UiPath Studio projects.

Produces a well-formed project.json with standard REFramework dependencies,
project metadata, and runtime configuration.
"""

from __future__ import annotations

import json
from typing import Any

from rpa_architect.ir.schema import ProcessIR

# Cross-Platform / Portable dependencies — minimal set so the package
# works on UiPath Cloud Serverless robots (no UIAutomation, no Mail/Excel
# UI activities). All logic lives inside CodedWorkflow .cs files using
# System.Net.Http directly.
_DEFAULT_DEPENDENCIES: dict[str, str] = {
    "UiPath.System.Activities": "[25.10.0]",
    "UiPath.WebAPI.Activities": "[2.3.1]",
}

# Document Understanding (IXP) dependencies, injected when ProcessIR.document_understanding is set.
_DU_DEPENDENCIES: dict[str, str] = {
    "UiPath.IntelligentOCR.Activities": "[6.27.0]",
    "UiPath.DocumentUnderstanding.ML.Activities": "[2.10.0]",
    "UiPath.OCR.Activities": "[1.20.0]",
}

_PROJECT_JSON_TEMPLATE = {
    "projectVersion": "1.0.0",
    "description": "",
    "name": "",
    # Legacy required field — UiPath.Executor.RobotRunner.InitWorkflowApplication()
    # calls Path.Combine(projectDir, project.main). If `main` is absent,
    # path2=null and the robot throws ArgumentNullException (observed live
    # on the first run against UiPath Community Cloud). Must be a valid
    # .xaml file per the Studio docs — our Main.xaml is a minimal wrapper
    # that hands off to ProcessInvoiceMain.cs (the CodedWorkflow).
    "main": "Main.xaml",
    "dependencies": {},
    "toolVersion": "25.10.0",
    # Cross-Platform target — runs on UiPath Cloud Serverless without
    # needing Windows credentials or an interactive desktop session. Uses
    # CodedWorkflow (C#) as the entry point so all logic is HttpClient
    # API calls (no UI activities, no UIAutomation dep).
    "targetFramework": "Portable",
    # Studio 25.10's WorkflowCompiler uses numeric ProjectProfile enum values
    # (0 = Development, 1 = Production). Old string "Development" is rejected.
    "designOptions": {
        "projectProfile": 0,
        "outputType": "Process",
        "libraryOptions": {"includeOriginalXaml": False, "privateWorkflows": []},
        "processOptions": {
            "ignoredFiles": [],
            "readyToRunEntryPoints": [],
            "autoDispose": False,
            "isFaulted": False,
        },
        "fileInfoCollection": [],
        "modernBehavior": True,
    },
    "runtimeOptions": {
        "autoDispose": False,
        "isPausable": True,
        # requiresUserInteraction=false so the process can run on an
        # Unattended robot without a Windows desktop session (Community
        # Cloud free tier robots are credentialless serverless runners).
        "requiresUserInteraction": False,
        "supportsPersistence": False,
        "excludedLoggedData": ["Private:*", "EncryptedPassword"],
        "executionType": "Workflow",
        "readyToRunEntryPoints": [],
        "startsWithDefault": True,
        "netVersion": "net6.0",
    },
    "entryPoints": [
        {
            "filePath": "Main.xaml",
            "uniqueId": "00000000-0000-0000-0000-000000000001",
            "input": [],
            "output": [],
        }
    ],
    "schemaVersion": "4.0",
    "studioVersion": "25.10.0.0",
    "expressionLanguage": "CSharp",
    "isTemplate": False,
}


def generate_project_json(
    ir: ProcessIR,
    dependencies: list[str] | None = None,
) -> str:
    """Generate a UiPath project.json file.

    Merges standard REFramework dependencies with any additional packages
    specified, and populates project metadata from the IR.

    Args:
        ir: The ProcessIR containing process name, description, and metadata.
        dependencies: Optional list of additional NuGet package names to include.
            Version ranges default to the latest compatible version.

    Returns:
        JSON string of the complete project.json content.
    """
    project: dict[str, Any] = json.loads(json.dumps(_PROJECT_JSON_TEMPLATE))

    # Set project metadata
    project["name"] = ir.process_name
    project["description"] = ir.description or f"RPA process: {ir.process_name}"

    # Merge dependencies
    all_deps = dict(_DEFAULT_DEPENDENCIES)

    # Inject Document Understanding deps when DU is configured.
    if ir.document_understanding is not None and ir.document_understanding.enabled:
        all_deps.update(_DU_DEPENDENCIES)

    if dependencies:
        for dep in dependencies:
            if dep not in all_deps:
                # Add with a permissive version range
                all_deps[dep] = "[*]"

    project["dependencies"] = all_deps

    # Add metadata from IR
    if ir.metadata.get("author"):
        project["description"] = (
            project.get("description", "") + f"\nAuthor: {ir.metadata['author']}"
        ).strip()
    if ir.metadata.get("version"):
        project["projectVersion"] = ir.metadata["version"]

    return json.dumps(project, indent=2, ensure_ascii=False)
