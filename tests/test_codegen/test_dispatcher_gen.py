"""Tests for the Dispatcher generator family.

The Dispatcher is the first UiPath process in the three-package factory. It:
  1. Connects to SuiteCRM
  2. Fetches Cases where status='New'
  3. Pre-fetches the matching Policy per case (snapshot isolation)
  4. Pushes each case as a queue item to the Orchestrator MedicalClaims queue
  5. PATCHes the SuiteCRM Case status to 'Queued'

It does NOT adjudicate. That's the Performer's job.

The Dispatcher also needs:
  - UiPathQueueClient.cs — C# HTTP client that hits Orchestrator's
    AddQueueItem OData action (can't reuse the Python UiPathClient inside
    the robot; everything must be compiled C#)
  - AssetClient.cs — runtime reader for UiPath Assets containing SuiteCRM
    credentials (no secrets baked into the package)
"""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

import pytest


DOTNET_ROOT = os.environ.get("DOTNET_ROOT") or str(Path.home() / ".dotnet")
DOTNET_BIN = Path(DOTNET_ROOT) / "dotnet"


def _have_dotnet() -> bool:
    return DOTNET_BIN.exists() or bool(shutil.which("dotnet"))


_CSPROJ = """<Project Sdk="Microsoft.NET.Sdk">
  <PropertyGroup>
    <TargetFramework>net8.0</TargetFramework>
    <OutputType>Library</OutputType>
    <Nullable>enable</Nullable>
    <NoWarn>CS0246;CS8632;CS8618;CS8625;CS8601;CS8602;CS8603;CS8604;CS8765;CS8767</NoWarn>
  </PropertyGroup>
</Project>
"""


_STUB_CODEDWORKFLOWS = """namespace UiPath.CodedWorkflows
{
    public class CodedWorkflow {}
    public class WorkflowAttribute : System.Attribute {}
}
"""


# ---------------------------------------------------------------------------
# Individual pieces
# ---------------------------------------------------------------------------


def test_uipath_queue_client_has_add_queue_item_method() -> None:
    from rpa_architect.codegen.dispatcher_gen import generate_uipath_queue_client_cs

    cs = generate_uipath_queue_client_cs()
    assert "class UiPathQueueClient" in cs
    assert "public async Task AddQueueItemAsync" in cs
    assert "UiPathODataSvc.AddQueueItem" in cs


def test_uipath_queue_client_uses_oauth2_client_credentials() -> None:
    from rpa_architect.codegen.dispatcher_gen import generate_uipath_queue_client_cs

    cs = generate_uipath_queue_client_cs()
    assert "identity_/connect/token" in cs
    assert "client_credentials" in cs


def test_uipath_queue_client_sends_folder_header() -> None:
    from rpa_architect.codegen.dispatcher_gen import generate_uipath_queue_client_cs

    cs = generate_uipath_queue_client_cs()
    assert "X-UIPATH-OrganizationUnitId" in cs


def test_asset_client_reads_from_env_or_config() -> None:
    """The AssetClient pulls SuiteCRM creds from local config (baked at
    pack time via deploy_claims.py regenerating the config before pack).
    """
    from rpa_architect.codegen.dispatcher_gen import generate_asset_client_cs

    cs = generate_asset_client_cs()
    assert "class AssetClient" in cs
    assert "GetSuiteCrmBaseUrl" in cs
    assert "GetSuiteCrmClientId" in cs
    assert "GetSuiteCrmClientSecret" in cs


# ---------------------------------------------------------------------------
# Dispatcher state machine
# ---------------------------------------------------------------------------


def test_dispatcher_init_state_fetches_new_cases() -> None:
    from rpa_architect.codegen.dispatcher_gen import generate_dispatcher_init_state_cs

    cs = generate_dispatcher_init_state_cs()
    assert "class DispatcherInitState" in cs
    # Init state: authenticate + load queue of pending cases
    assert "SuiteCrm" in cs
    assert "Cases" in cs or "Status" in cs


def test_dispatcher_process_state_enqueues_via_queue_client() -> None:
    from rpa_architect.codegen.dispatcher_gen import generate_dispatcher_process_state_cs

    cs = generate_dispatcher_process_state_cs()
    assert "class DispatcherProcessState" in cs
    assert "AddQueueItemAsync" in cs


def test_dispatcher_process_state_patches_suitecrm_status_to_queued() -> None:
    from rpa_architect.codegen.dispatcher_gen import generate_dispatcher_process_state_cs

    cs = generate_dispatcher_process_state_cs()
    # PATCH the case — UpdateCaseStatusAsync or similar; we accept
    # either calling the SuiteCrm client directly or an inline HTTP call.
    assert '"Queued"' in cs or "\"Queued\"" in cs


def test_dispatcher_handles_payload_size_fallback() -> None:
    """BW-10: if the serialized case exceeds ~800 KiB, fall back to a
    bucket reference instead of embedding the full payload in the queue
    item SpecificContent (which has a 1 MiB limit)."""
    from rpa_architect.codegen.dispatcher_gen import generate_dispatcher_process_state_cs

    cs = generate_dispatcher_process_state_cs()
    assert "800" in cs or "payload_bucket_ref" in cs or "MaxPayloadSize" in cs


def test_dispatcher_main_uses_workflow_attribute() -> None:
    from rpa_architect.codegen.dispatcher_gen import generate_dispatcher_main_cs

    cs = generate_dispatcher_main_cs()
    assert "[Workflow]" in cs
    assert ": CodedWorkflow" in cs
    assert "public async Task<int> Execute()" in cs


def test_dispatcher_main_instantiates_queue_client_and_suitecrm() -> None:
    from rpa_architect.codegen.dispatcher_gen import generate_dispatcher_main_cs

    cs = generate_dispatcher_main_cs()
    assert "UiPathQueueClient" in cs
    assert "SuiteCrmClient" in cs
    assert "AssetClient" in cs


# ---------------------------------------------------------------------------
# Compile test — full Dispatcher project
# ---------------------------------------------------------------------------


@pytest.mark.skipif(not _have_dotnet(), reason="dotnet SDK not installed")
def test_full_dispatcher_project_compiles(tmp_path: Path) -> None:
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
    from rpa_architect.codegen.suitecrm_client_gen import generate_suitecrm_client_cs

    (tmp_path / "test.csproj").write_text(_CSPROJ)
    (tmp_path / "CodedWorkflowsStub.cs").write_text(_STUB_CODEDWORKFLOWS)

    # Claims domain
    (tmp_path / "Case.cs").write_text(generate_case_cs())
    (tmp_path / "Policy.cs").write_text(generate_policy_cs())
    (tmp_path / "Provider.cs").write_text(generate_provider_cs())
    (tmp_path / "ClaimVerdict.cs").write_text(generate_claim_verdict_cs())
    (tmp_path / "ClaimMetrics.cs").write_text(generate_claim_metrics_cs())
    (tmp_path / "ClaimsProcessContext.cs").write_text(
        generate_claims_process_context_cs()
    )
    (tmp_path / "SuiteCrmClient.cs").write_text(generate_suitecrm_client_cs())
    (tmp_path / "ClaimsRules.cs").write_text(generate_claims_rules_cs())

    # Claims-native versions of IState / exceptions / EndState (not the
    # v0.5 Odoo-locked ones — those reference BatchMetrics fields like
    # TotalInvoices / CreatedBillIds that don't exist on ClaimMetrics).
    (tmp_path / "IState.cs").write_text(generate_claims_istate_cs())
    (tmp_path / "ClaimsExceptions.cs").write_text(generate_claims_exceptions_cs())
    (tmp_path / "EndState.cs").write_text(generate_claims_end_state_cs())

    # Dispatcher files
    (tmp_path / "UiPathQueueClient.cs").write_text(generate_uipath_queue_client_cs())
    (tmp_path / "AssetClient.cs").write_text(generate_asset_client_cs())
    (tmp_path / "DispatcherInitState.cs").write_text(generate_dispatcher_init_state_cs())
    (tmp_path / "DispatcherGetTransactionDataState.cs").write_text(
        generate_dispatcher_get_transaction_state_cs()
    )
    (tmp_path / "DispatcherProcessState.cs").write_text(
        generate_dispatcher_process_state_cs()
    )
    (tmp_path / "DispatcherSetTransactionStatusState.cs").write_text(
        generate_dispatcher_set_transaction_status_state_cs()
    )
    (tmp_path / "DispatcherMain.cs").write_text(generate_dispatcher_main_cs())

    env = os.environ.copy()
    env["DOTNET_ROOT"] = DOTNET_ROOT
    env["PATH"] = f"{DOTNET_ROOT}:{DOTNET_ROOT}/tools:{env.get('PATH', '')}"
    env["DOTNET_NOLOGO"] = "1"
    env["DOTNET_CLI_TELEMETRY_OPTOUT"] = "1"
    dn = str(DOTNET_BIN) if DOTNET_BIN.exists() else "dotnet"

    build = subprocess.run(
        [dn, "build", str(tmp_path / "test.csproj")],
        capture_output=True, text=True, env=env, timeout=300,
    )
    assert build.returncode == 0, (
        f"build failed:\nSTDOUT:\n{build.stdout}\nSTDERR:\n{build.stderr}"
    )
    assert "0 Error(s)" in build.stdout
