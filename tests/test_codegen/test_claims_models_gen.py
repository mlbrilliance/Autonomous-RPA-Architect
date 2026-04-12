"""Compile-tests for the claims adjudication C# domain models.

Generates Case.cs, Policy.cs, Provider.cs, ClaimVerdict.cs, ClaimMetrics.cs,
and ClaimsProcessContext.cs into a tmp_path + runs `dotnet build` to verify
the whole set is syntactically valid C# and types resolve against each other.
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


# ---------------------------------------------------------------------------
# Case.cs
# ---------------------------------------------------------------------------


def test_case_cs_contains_all_claim_fields() -> None:
    from rpa_architect.codegen.claims_models_gen import generate_case_cs

    cs = generate_case_cs()
    for field in (
        "ClaimId",
        "PolicyNumber",
        "ClaimantName",
        "DiagnosisCode",
        "ProcedureCode",
        "TotalAmount",
        "Currency",
        "SubmittedAt",
        "ProviderNpi",
        "DocumentUrls",
        "Status",
        "Verdict",
    ):
        assert f"public " in cs and field in cs, f"{field} missing from Case.cs"


def test_case_cs_uses_claims_namespace() -> None:
    from rpa_architect.codegen.claims_models_gen import generate_case_cs

    assert "namespace MedicalClaimsProcessing" in generate_case_cs()


def test_case_cs_custom_namespace() -> None:
    from rpa_architect.codegen.claims_models_gen import generate_case_cs

    cs = generate_case_cs(namespace="ClaimsFactory.Models")
    assert "namespace ClaimsFactory.Models" in cs


# ---------------------------------------------------------------------------
# Policy.cs
# ---------------------------------------------------------------------------


def test_policy_cs_has_coverage_dates() -> None:
    from rpa_architect.codegen.claims_models_gen import generate_policy_cs

    cs = generate_policy_cs()
    assert "CoverageStart" in cs
    assert "CoverageEnd" in cs
    assert "DeductibleRemaining" in cs
    assert "OutOfPocketMax" in cs


def test_policy_cs_has_is_active_on_helper() -> None:
    """Policy should expose an IsActiveOn(DateTime) method — used by
    CoverageVerificationRule to short-circuit without touching SuiteCRM."""
    from rpa_architect.codegen.claims_models_gen import generate_policy_cs

    cs = generate_policy_cs()
    assert "IsActiveOn" in cs


# ---------------------------------------------------------------------------
# Provider.cs
# ---------------------------------------------------------------------------


def test_provider_cs_has_in_network_flag() -> None:
    from rpa_architect.codegen.claims_models_gen import generate_provider_cs

    cs = generate_provider_cs()
    assert "InNetwork" in cs
    assert "Npi" in cs
    assert "SpecialtyCode" in cs


# ---------------------------------------------------------------------------
# ClaimVerdict enum
# ---------------------------------------------------------------------------


def test_claim_verdict_enum_has_four_values() -> None:
    from rpa_architect.codegen.claims_models_gen import generate_claim_verdict_cs

    cs = generate_claim_verdict_cs()
    assert "enum ClaimVerdict" in cs
    for v in ("AutoApprove", "FlagForReview", "Deny", "Pending"):
        assert v in cs


# ---------------------------------------------------------------------------
# ClaimMetrics.cs
# ---------------------------------------------------------------------------


def test_claim_metrics_tracks_per_verdict_counts() -> None:
    from rpa_architect.codegen.claims_models_gen import generate_claim_metrics_cs

    cs = generate_claim_metrics_cs()
    assert "AutoApproved" in cs
    assert "Flagged" in cs
    assert "Denied" in cs
    assert "BusinessFailures" in cs
    assert "SystemFailures" in cs


def test_claim_metrics_has_record_verdict_method() -> None:
    from rpa_architect.codegen.claims_models_gen import generate_claim_metrics_cs

    cs = generate_claim_metrics_cs()
    assert "RecordVerdict" in cs


# ---------------------------------------------------------------------------
# ClaimsProcessContext.cs
# ---------------------------------------------------------------------------


def test_claims_context_has_suitecrm_and_metrics() -> None:
    from rpa_architect.codegen.claims_models_gen import generate_claims_process_context_cs

    cs = generate_claims_process_context_cs()
    assert "SuiteCrmClient" in cs
    assert "ClaimMetrics" in cs
    assert "ClaimsRuleEngine" in cs
    assert "CurrentCase" in cs
    assert "CurrentTransactionId" in cs


# ---------------------------------------------------------------------------
# Compile-test — all models together
# ---------------------------------------------------------------------------


@pytest.mark.skipif(not _have_dotnet(), reason="dotnet SDK not installed")
def test_claims_models_compile_together(tmp_path: Path) -> None:
    from rpa_architect.codegen.claims_models_gen import (
        generate_case_cs,
        generate_claim_metrics_cs,
        generate_claim_verdict_cs,
        generate_claims_process_context_cs,
        generate_policy_cs,
        generate_provider_cs,
    )

    # The real SuiteCrmClient + ClaimsRuleEngine types don't exist yet
    # (they land in EV2-2 and EV2-3). Stub them so the models compile
    # standalone — the full integration test comes in EV2-6.
    stubs = """
namespace MedicalClaimsProcessing
{
    public class SuiteCrmClient {}
    public class ClaimsRuleEngine {}
}
"""

    (tmp_path / "test.csproj").write_text(_CSPROJ)
    (tmp_path / "Stubs.cs").write_text(stubs)
    (tmp_path / "Case.cs").write_text(generate_case_cs())
    (tmp_path / "Policy.cs").write_text(generate_policy_cs())
    (tmp_path / "Provider.cs").write_text(generate_provider_cs())
    (tmp_path / "ClaimVerdict.cs").write_text(generate_claim_verdict_cs())
    (tmp_path / "ClaimMetrics.cs").write_text(generate_claim_metrics_cs())
    (tmp_path / "ClaimsProcessContext.cs").write_text(
        generate_claims_process_context_cs()
    )

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
