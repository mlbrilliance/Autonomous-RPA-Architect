"""Multi-process claims factory assembler — EV2-8.

Writes three sibling UiPath project directories (``dispatcher/``,
``performer/``, ``reporter/``) from one :class:`ProcessIR` whose
``process_topology == "dispatcher_performer_reporter"``.

Each project dir is a standalone Portable UiPath project:

  - Byte-identical copies of the shared claims C# sources (Case, Policy,
    Provider, SuiteCrmClient, ClaimsRuleEngine, ...). We can't share a
    library DLL because UiPath Community Cloud's NuGet feed silently
    strips cross-package references at pack time.
  - Its own Main.xaml (one-line wrapper invoking the compiled [Workflow]
    class) and project.json (Portable enum, projectProfile=0).
  - Process-specific C# files (DispatcherMain + state machine, or
    PerformerMain + state machine, or ReporterMain + state machine).

The resulting layout is:

    output_dir/
      dispatcher/   ← pack this into dispatcher.nupkg
      performer/    ← pack this into performer.nupkg
      reporter/     ← pack this into reporter.nupkg

``proof/deploy_claims.py`` (EV2-9) walks the three dirs, runs ``uipcli
pack`` on each, and uploads them as separate Orchestrator releases.
"""

from __future__ import annotations

import logging
from pathlib import Path

from rpa_architect.codegen.claims_models_gen import (
    generate_case_cs,
    generate_claim_metrics_cs,
    generate_claim_verdict_cs,
    generate_claims_process_context_cs,
    generate_policy_cs,
    generate_provider_cs,
)
from rpa_architect.codegen.claims_rules_gen import generate_claims_rules_cs
from rpa_architect.codegen.dispatcher_gen import (
    generate_asset_client_cs,
    generate_claims_end_state_cs,
    generate_claims_exceptions_cs,
    generate_claims_istate_cs,
    generate_dispatcher_get_transaction_state_cs,
    generate_dispatcher_init_state_cs,
    generate_dispatcher_main_cs,
    generate_dispatcher_process_state_cs,
    generate_dispatcher_set_transaction_status_state_cs,
    generate_uipath_queue_client_cs,
)
from rpa_architect.codegen.performer_gen import (
    generate_performer_get_transaction_state_cs,
    generate_performer_init_state_cs,
    generate_performer_main_cs,
    generate_performer_process_state_cs,
    generate_performer_queue_client_cs,
    generate_performer_set_transaction_status_state_cs,
)
from rpa_architect.codegen.reporter_gen import (
    generate_reporter_init_state_cs,
    generate_reporter_main_cs,
    generate_reporter_process_state_cs,
    generate_reporter_queue_reader_cs,
    generate_reporter_set_status_state_cs,
)
from rpa_architect.codegen.suitecrm_client_gen import generate_suitecrm_client_cs

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Shared claims C# files (byte-identical across all three project dirs)
# ---------------------------------------------------------------------------


def _shared_claims_files(namespace: str) -> dict[str, str]:
    """Return the set of C# files emitted into every claims project dir.

    Each of these is content-identical across dispatcher, performer, and
    reporter. A test enforces byte-equality so we catch any drift.
    """
    return {
        "Case.cs": generate_case_cs(namespace),
        "Policy.cs": generate_policy_cs(namespace),
        "Provider.cs": generate_provider_cs(namespace),
        "ClaimVerdict.cs": generate_claim_verdict_cs(namespace),
        "ClaimMetrics.cs": generate_claim_metrics_cs(namespace),
        "ClaimsProcessContext.cs": generate_claims_process_context_cs(namespace),
        "SuiteCrmClient.cs": generate_suitecrm_client_cs(namespace),
        "ClaimsRules.cs": generate_claims_rules_cs(namespace),
        "IState.cs": generate_claims_istate_cs(namespace),
        "ClaimsExceptions.cs": generate_claims_exceptions_cs(namespace),
        "EndState.cs": generate_claims_end_state_cs(namespace),
        "AssetClient.cs": generate_asset_client_cs(namespace),
    }


# ---------------------------------------------------------------------------
# Process-specific C# files
# ---------------------------------------------------------------------------


def _dispatcher_specific_files(namespace: str) -> dict[str, str]:
    return {
        "UiPathQueueClient.cs": generate_uipath_queue_client_cs(namespace),
        "DispatcherInitState.cs": generate_dispatcher_init_state_cs(namespace),
        "DispatcherGetTransactionDataState.cs": generate_dispatcher_get_transaction_state_cs(
            namespace
        ),
        "DispatcherProcessState.cs": generate_dispatcher_process_state_cs(namespace),
        "DispatcherSetTransactionStatusState.cs": generate_dispatcher_set_transaction_status_state_cs(
            namespace
        ),
        "DispatcherMain.cs": generate_dispatcher_main_cs(namespace),
    }


def _performer_specific_files(namespace: str) -> dict[str, str]:
    return {
        "PerformerQueueClient.cs": generate_performer_queue_client_cs(namespace),
        "PerformerInitState.cs": generate_performer_init_state_cs(namespace),
        "PerformerGetTransactionDataState.cs": generate_performer_get_transaction_state_cs(
            namespace
        ),
        "PerformerProcessState.cs": generate_performer_process_state_cs(namespace),
        "PerformerSetTransactionStatusState.cs": generate_performer_set_transaction_status_state_cs(
            namespace
        ),
        "PerformerMain.cs": generate_performer_main_cs(namespace),
    }


def _reporter_specific_files(namespace: str) -> dict[str, str]:
    return {
        # Reporter reuses PerformerQueueClient (same partial class pattern).
        "PerformerQueueClient.cs": generate_performer_queue_client_cs(namespace),
        "ReporterQueueReader.cs": generate_reporter_queue_reader_cs(namespace),
        "ReporterInitState.cs": generate_reporter_init_state_cs(namespace),
        "ReporterProcessState.cs": generate_reporter_process_state_cs(namespace),
        "ReporterSetStatusState.cs": generate_reporter_set_status_state_cs(namespace),
        "ReporterMain.cs": generate_reporter_main_cs(namespace),
    }


# ---------------------------------------------------------------------------
# Main.xaml + project.json (per-project)
# ---------------------------------------------------------------------------


def _main_xaml_invoking(cs_file: str, display_name: str) -> str:
    """Return a Main.xaml that invokes a specific CodedWorkflow .cs file.

    Uses ``ui:InvokeWorkflowFile`` exactly like the v0.5 Odoo project
    that was validated live on Community Cloud. No expressions, no
    variables — JIT is disabled in Portable (BW §6).
    """
    return (
        '<?xml version="1.0" encoding="utf-8"?>\n'
        '<Activity mc:Ignorable="sap sap2010 sads"'
        ' x:Class="Main"'
        ' xmlns="http://schemas.microsoft.com/netfx/2009/xaml/activities"'
        ' xmlns:mc="http://schemas.openxmlformats.org/markup-compatibility/2006"'
        ' xmlns:sap="http://schemas.microsoft.com/netfx/2009/xaml/activities/presentation"'
        ' xmlns:sap2010="http://schemas.microsoft.com/netfx/2010/xaml/activities/presentation"'
        ' xmlns:sads="http://schemas.microsoft.com/netfx/2010/xaml/activities/debugger"'
        ' xmlns:ui="http://schemas.uipath.com/workflow/activities"'
        ' xmlns:x="http://schemas.microsoft.com/winfx/2006/xaml">\n'
        f'  <Sequence DisplayName="{display_name}">\n'
        f'    <ui:InvokeWorkflowFile DisplayName="Invoke {display_name}"'
        f' WorkflowFileName="{cs_file}" />\n'
        '  </Sequence>\n'
        '</Activity>\n'
    )


def _build_project_json(project_name: str, main_entry: str) -> str:
    """Minimal Portable project.json with all the v0.5-learned fields.

    Keeps targetFramework="Portable", projectProfile=0 (numeric),
    requiresUserInteraction=false, main="Main.xaml" — every gotcha from
    docs/community_cloud_limitations.md lines up here.
    """
    import json
    import uuid

    # Match the v0.5 project.json template exactly — it's the only format
    # that's been validated live on UiPath Community Cloud's serverless
    # runtime with uipcli 25.10.12. Every field is load-bearing; don't
    # add extras without live validation.
    payload = {
        "projectVersion": "1.0.2",
        "description": f"{project_name} — generated by autonomous-rpa-architect v0.6",
        "name": project_name,
        "main": "Main.xaml",
        "dependencies": {
            "UiPath.System.Activities": "[25.10.0]",
            "UiPath.WebAPI.Activities": "[2.3.1]",
        },
        "toolVersion": "25.10.0",
        "targetFramework": "Portable",
        "designOptions": {
            "projectProfile": 0,  # numeric, not "Development" — gotcha §11
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
                "uniqueId": str(
                    uuid.uuid5(uuid.NAMESPACE_URL, f"rpa-architect://{project_name}")
                ),
                "input": [],
                "output": [],
            }
        ],
        "schemaVersion": "4.0",
        "studioVersion": "25.10.0.0",
        "expressionLanguage": "CSharp",  # MUST be CSharp for CodedWorkflows
        "isTemplate": False,
    }
    return json.dumps(payload, indent=2, ensure_ascii=False)


# ---------------------------------------------------------------------------
# Top-level entry point
# ---------------------------------------------------------------------------


def assemble_claims_factory(
    namespace: str,
    output_dir: Path,
) -> dict[str, Path]:
    """Emit the three sibling project dirs for the claims factory.

    Args:
        namespace: The C# namespace for all generated types (e.g.
            ``MedicalClaimsProcessing``).
        output_dir: Root directory. Subdirectories ``dispatcher/``,
            ``performer/``, and ``reporter/`` are created.

    Returns:
        Mapping of process name → full path to the project directory.
    """
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    project_dirs: dict[str, Path] = {}

    # Project names must NOT collide with any class name in the generated
    # C# because uipcli creates a child namespace from the project name
    # (e.g. MedicalClaimsProcessing.ClaimsDispatcher). If a class with the
    # same name as the project exists in the parent namespace, CS0101
    # fires. We use "Claims" prefix to distinguish from the class names
    # (DispatcherMain, PerformerMain, ReporterMain).
    #
    # Each entry: (project_name, main_cs_file, generator_fn)
    specs = {
        "dispatcher": ("ClaimsDispatcher", "DispatcherMain.cs", _dispatcher_specific_files),
        "performer": ("ClaimsPerformer", "PerformerMain.cs", _performer_specific_files),
        "reporter": ("ClaimsReporter", "ReporterMain.cs", _reporter_specific_files),
    }

    shared = _shared_claims_files(namespace)

    for process_name, (main_class, cs_file, specific_fn) in specs.items():
        project_dir = output_dir / process_name
        project_dir.mkdir(parents=True, exist_ok=True)

        # Write shared files.
        for name, content in shared.items():
            (project_dir / name).write_text(content, encoding="utf-8")

        # Write process-specific files.
        for name, content in specific_fn(namespace).items():
            (project_dir / name).write_text(content, encoding="utf-8")

        # Main.xaml — must invoke the specific CodedWorkflow .cs file
        # via InvokeWorkflowFile, exactly like v0.5's Odoo Main.xaml.
        (project_dir / "Main.xaml").write_text(
            _main_xaml_invoking(cs_file, main_class),
            encoding="utf-8",
        )
        (project_dir / "project.json").write_text(
            _build_project_json(
                main_class,  # project name (no dots — uipcli creates a child namespace from it)
                main_class,
            ),
            encoding="utf-8",
        )

        project_dirs[process_name] = project_dir
        logger.info("Assembled %s project at %s", process_name, project_dir)

    return project_dirs
