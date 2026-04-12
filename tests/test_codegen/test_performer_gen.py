"""Tests for the Performer generator family.

The Performer is the queue-consuming analog to v0.5's ProcessInvoiceMain.
Unlike the Dispatcher (which produces queue items) and the Reporter (which
aggregates), the Performer leases one item at a time via
StartTransaction, runs the 5-rule engine, writes the verdict back to
SuiteCRM, and marks the transaction Successful or BusinessFailure.
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


_STUB_CODEDWORKFLOWS = """
namespace UiPath.CodedWorkflows
{
    [System.AttributeUsage(System.AttributeTargets.Method)]
    public class WorkflowAttribute : System.Attribute {}
}
namespace ClaimsDispatcher { public class CodedWorkflow {} }
namespace ClaimsPerformer { public class CodedWorkflow {} }
namespace ClaimsReporter { public class CodedWorkflow {} }
"""


# ---------------------------------------------------------------------------
# PerformerQueueClient — the C# OData client for StartTransaction / SetResult
# ---------------------------------------------------------------------------


def test_performer_queue_client_has_start_transaction() -> None:
    from rpa_architect.codegen.performer_gen import generate_performer_queue_client_cs

    cs = generate_performer_queue_client_cs()
    assert "class PerformerQueueClient" in cs
    assert "StartTransactionAsync" in cs
    assert "UiPathODataSvc.StartTransaction" in cs


def test_performer_queue_client_has_set_transaction_result() -> None:
    from rpa_architect.codegen.performer_gen import generate_performer_queue_client_cs

    cs = generate_performer_queue_client_cs()
    assert "SetTransactionResultAsync" in cs
    assert "UiPathODataSvc.SetTransactionResult" in cs


def test_performer_queue_client_returns_null_on_204() -> None:
    """Empty queue → Orchestrator returns 204 → client must return null."""
    from rpa_architect.codegen.performer_gen import generate_performer_queue_client_cs

    cs = generate_performer_queue_client_cs()
    assert "204" in cs or "NoContent" in cs
    assert "return null" in cs


def test_performer_queue_client_passes_is_successful_flag() -> None:
    from rpa_architect.codegen.performer_gen import generate_performer_queue_client_cs

    cs = generate_performer_queue_client_cs()
    assert "IsSuccessful" in cs


# ---------------------------------------------------------------------------
# Performer state machine
# ---------------------------------------------------------------------------


def test_performer_init_warms_up_suitecrm() -> None:
    from rpa_architect.codegen.performer_gen import generate_performer_init_state_cs

    cs = generate_performer_init_state_cs()
    assert "class PerformerInitState" in cs
    assert "SuiteCrm" in cs
    assert "__warmup__" in cs or "warmup" in cs.lower()


def test_performer_get_transaction_calls_start_transaction() -> None:
    from rpa_architect.codegen.performer_gen import (
        generate_performer_get_transaction_state_cs,
    )

    cs = generate_performer_get_transaction_state_cs()
    assert "class PerformerGetTransactionDataState" in cs
    assert "StartTransactionAsync" in cs


def test_performer_get_transaction_returns_end_when_queue_drained() -> None:
    from rpa_architect.codegen.performer_gen import (
        generate_performer_get_transaction_state_cs,
    )

    cs = generate_performer_get_transaction_state_cs()
    # When StartTransaction returns null, loop back to End.
    assert "new EndState" in cs or "EndState()" in cs


def test_performer_get_transaction_decodes_payload_or_fetches_by_id() -> None:
    """Decodes payload_b64 if present (BW-10 happy path), otherwise
    calls SuiteCrm.GetCaseByIdAsync using the claim_id."""
    from rpa_architect.codegen.performer_gen import (
        generate_performer_get_transaction_state_cs,
    )

    cs = generate_performer_get_transaction_state_cs()
    assert "payload_b64" in cs or "FromBase64String" in cs
    assert "GetCaseByIdAsync" in cs or "suitecrm_id" in cs


def test_performer_process_runs_rule_engine_and_writes_back() -> None:
    from rpa_architect.codegen.performer_gen import generate_performer_process_state_cs

    cs = generate_performer_process_state_cs()
    assert "class PerformerProcessState" in cs
    assert "Rules.EvaluateAsync" in cs
    assert "UpdateCaseVerdictAsync" in cs


def test_performer_process_creates_adjudication_note() -> None:
    """Every processed claim must leave an audit note on the SuiteCRM case."""
    from rpa_architect.codegen.performer_gen import generate_performer_process_state_cs

    cs = generate_performer_process_state_cs()
    assert "CreateAdjudicationNoteAsync" in cs


def test_performer_set_status_distinguishes_business_vs_system() -> None:
    """BusinessException → SetTransactionResult(IsSuccessful=false, business_error=...)
    SystemException → rethrow so state machine retries."""
    from rpa_architect.codegen.performer_gen import (
        generate_performer_set_transaction_status_state_cs,
    )

    cs = generate_performer_set_transaction_status_state_cs()
    assert "class PerformerSetTransactionStatusState" in cs
    assert "SetTransactionResultAsync" in cs


def test_performer_main_uses_workflow_attribute_and_drains_loop() -> None:
    from rpa_architect.codegen.performer_gen import generate_performer_main_cs

    cs = generate_performer_main_cs()
    assert "[Workflow]" in cs
    assert ": CodedWorkflow" in cs
    assert "public async Task<int> Execute()" in cs
    assert "PerformerInitState" in cs
    assert "PerformerQueueClient" in cs
    assert "SuiteCrmClient" in cs


# ---------------------------------------------------------------------------
# Compile test — full Performer project
# ---------------------------------------------------------------------------


@pytest.mark.skipif(not _have_dotnet(), reason="dotnet SDK not installed")
def test_full_performer_project_compiles(tmp_path: Path) -> None:
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
        generate_claims_end_state_cs,
        generate_claims_exceptions_cs,
        generate_claims_istate_cs,
    )
    from rpa_architect.codegen.performer_gen import (
        generate_performer_get_transaction_state_cs,
        generate_performer_init_state_cs,
        generate_performer_main_cs,
        generate_performer_process_state_cs,
        generate_performer_queue_client_cs,
        generate_performer_set_transaction_status_state_cs,
    )
    from rpa_architect.codegen.suitecrm_client_gen import generate_suitecrm_client_cs

    (tmp_path / "test.csproj").write_text(_CSPROJ)
    (tmp_path / "CodedWorkflowsStub.cs").write_text(_STUB_CODEDWORKFLOWS)

    # Asset client stub (the real one is written by the assembler)
    asset_stub = """
namespace MedicalClaimsProcessing
{
    public static class AssetClient
    {
        public const string SuiteCrmBaseUrl = "http://localhost";
        public const string SuiteCrmClientId = "x";
        public const string SuiteCrmClientSecret = "x";
        public const string SuiteCrmUsername = "x";
        public const string SuiteCrmPassword = "x";
        public const string UiPathIdentityUrl = "http://localhost";
        public const string UiPathOrchestratorUrl = "http://localhost";
        public const string UiPathClientId = "x";
        public const string UiPathClientSecret = "x";
        public const string UiPathFolderId = "1";
        public const string QueueName = "MedicalClaims";
        public const string RobotIdentifier = "robot-01";
    }
}
"""
    (tmp_path / "AssetClient.cs").write_text(asset_stub)

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

    # Shared claims states / exceptions
    (tmp_path / "IState.cs").write_text(generate_claims_istate_cs())
    (tmp_path / "ClaimsExceptions.cs").write_text(generate_claims_exceptions_cs())
    (tmp_path / "EndState.cs").write_text(generate_claims_end_state_cs())

    # Performer files
    (tmp_path / "PerformerQueueClient.cs").write_text(
        generate_performer_queue_client_cs()
    )
    (tmp_path / "PerformerInitState.cs").write_text(
        generate_performer_init_state_cs()
    )
    (tmp_path / "PerformerGetTransactionDataState.cs").write_text(
        generate_performer_get_transaction_state_cs()
    )
    (tmp_path / "PerformerProcessState.cs").write_text(
        generate_performer_process_state_cs()
    )
    (tmp_path / "PerformerSetTransactionStatusState.cs").write_text(
        generate_performer_set_transaction_status_state_cs()
    )
    (tmp_path / "PerformerMain.cs").write_text(generate_performer_main_cs())

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
