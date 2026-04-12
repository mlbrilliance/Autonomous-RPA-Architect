"""Tests for the Reporter generator family.

The Reporter is the third process in the claims factory. It:
  1. Queries the MedicalClaims queue for items in a time window
  2. Groups by verdict outcome (auto_approve / flag_for_review / deny)
  3. Renders an HTML SLA report with latency + distribution
  4. Uploads the HTML to a SlaReports Orchestrator bucket (or stdout-only
     if buckets aren't authorized)
  5. Optionally creates a summary Note in SuiteCRM
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


def test_reporter_queue_reader_lists_successful_items() -> None:
    from rpa_architect.codegen.reporter_gen import generate_reporter_queue_reader_cs

    cs = generate_reporter_queue_reader_cs()
    assert "class ReporterQueueReader" in cs
    assert "ListQueueItemsAsync" in cs or "QueueItems" in cs


def test_reporter_init_state_present() -> None:
    from rpa_architect.codegen.reporter_gen import generate_reporter_init_state_cs

    cs = generate_reporter_init_state_cs()
    assert "class ReporterInitState" in cs


def test_reporter_process_state_aggregates_verdict_distribution() -> None:
    from rpa_architect.codegen.reporter_gen import generate_reporter_process_state_cs

    cs = generate_reporter_process_state_cs()
    assert "class ReporterProcessState" in cs
    # Counts per verdict (auto_approve / flag_for_review / deny)
    assert "AutoApprove" in cs or "auto_approve" in cs
    assert "Deny" in cs or "deny" in cs


def test_reporter_process_state_renders_html() -> None:
    from rpa_architect.codegen.reporter_gen import generate_reporter_process_state_cs

    cs = generate_reporter_process_state_cs()
    assert "<html" in cs or "<!DOCTYPE html>" in cs


def test_reporter_main_has_workflow_attribute() -> None:
    from rpa_architect.codegen.reporter_gen import generate_reporter_main_cs

    cs = generate_reporter_main_cs()
    assert "[Workflow]" in cs
    assert ": CodedWorkflow" in cs
    assert "public async Task<int> Execute()" in cs


@pytest.mark.skipif(not _have_dotnet(), reason="dotnet SDK not installed")
def test_full_reporter_project_compiles(tmp_path: Path) -> None:
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
    from rpa_architect.codegen.performer_gen import generate_performer_queue_client_cs
    from rpa_architect.codegen.reporter_gen import (
        generate_reporter_init_state_cs,
        generate_reporter_main_cs,
        generate_reporter_process_state_cs,
        generate_reporter_queue_reader_cs,
        generate_reporter_set_status_state_cs,
    )
    from rpa_architect.codegen.suitecrm_client_gen import generate_suitecrm_client_cs

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

    (tmp_path / "test.csproj").write_text(_CSPROJ)
    (tmp_path / "CodedWorkflowsStub.cs").write_text(_STUB_CODEDWORKFLOWS)
    (tmp_path / "AssetClient.cs").write_text(asset_stub)
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
    (tmp_path / "IState.cs").write_text(generate_claims_istate_cs())
    (tmp_path / "ClaimsExceptions.cs").write_text(generate_claims_exceptions_cs())
    (tmp_path / "EndState.cs").write_text(generate_claims_end_state_cs())
    # Reporter uses PerformerQueueClient (reuses the partial class) to
    # list items — simplest way to avoid a third queue client.
    (tmp_path / "PerformerQueueClient.cs").write_text(
        generate_performer_queue_client_cs()
    )
    (tmp_path / "ReporterQueueReader.cs").write_text(generate_reporter_queue_reader_cs())
    (tmp_path / "ReporterInitState.cs").write_text(generate_reporter_init_state_cs())
    (tmp_path / "ReporterProcessState.cs").write_text(
        generate_reporter_process_state_cs()
    )
    (tmp_path / "ReporterSetStatusState.cs").write_text(
        generate_reporter_set_status_state_cs()
    )
    (tmp_path / "ReporterMain.cs").write_text(generate_reporter_main_cs())

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
