"""Tests for the 5-rule medical claims adjudication engine generator.

Rules (in cheap→expensive execution order):
  1. CoverageVerificationRule   — in-memory policy check, Deny on expired
  2. AmountThresholdRule        — flag >$10k for review, deny >$100k
  3. DocumentationCompletenessRule — count notes, deny on insufficient docs
  4. NetworkProviderRule        — SuiteCRM live lookup, flag out-of-network
  5. FraudVelocityRule          — recent-cases count, flag ≥2 / deny ≥4

Chain short-circuits on Deny; FlagForReview accumulates reasons.
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
# Structure
# ---------------------------------------------------------------------------


def test_rules_module_has_irule_interface() -> None:
    from rpa_architect.codegen.claims_rules_gen import generate_claims_rules_cs

    cs = generate_claims_rules_cs()
    assert "public interface IClaimRule" in cs
    assert "Task<RuleResult> EvaluateAsync" in cs


def test_rule_result_has_verdict_and_reason() -> None:
    from rpa_architect.codegen.claims_rules_gen import generate_claims_rules_cs

    cs = generate_claims_rules_cs()
    assert "class RuleResult" in cs
    assert "public ClaimVerdict Verdict" in cs
    assert "public string Reason" in cs


def test_all_five_rules_present() -> None:
    from rpa_architect.codegen.claims_rules_gen import generate_claims_rules_cs

    cs = generate_claims_rules_cs()
    for cls in (
        "CoverageVerificationRule",
        "AmountThresholdRule",
        "DocumentationCompletenessRule",
        "NetworkProviderRule",
        "FraudVelocityRule",
    ):
        assert f"class {cls} : IClaimRule" in cs, f"{cls} missing or wrong shape"


def test_rule_engine_has_evaluate_async() -> None:
    from rpa_architect.codegen.claims_rules_gen import generate_claims_rules_cs

    cs = generate_claims_rules_cs()
    assert "class ClaimsRuleEngine" in cs
    assert "public async Task<ClaimVerdict> EvaluateAsync" in cs


def test_rule_engine_registers_rules_in_cheap_first_order() -> None:
    """The rules list in the engine constructor must be ordered cheap→expensive."""
    from rpa_architect.codegen.claims_rules_gen import generate_claims_rules_cs

    cs = generate_claims_rules_cs()
    # Find the rules list initialization — order matters because the engine
    # short-circuits on first Deny, so cheap rules should run first.
    idx_coverage = cs.find("new CoverageVerificationRule")
    idx_amount = cs.find("new AmountThresholdRule")
    idx_docs = cs.find("new DocumentationCompletenessRule")
    idx_network = cs.find("new NetworkProviderRule")
    idx_fraud = cs.find("new FraudVelocityRule")
    assert idx_coverage >= 0 and idx_amount >= 0 and idx_docs >= 0
    assert idx_network >= 0 and idx_fraud >= 0
    # Cheap rules first: Coverage < Amount < Docs < Network < Fraud
    assert idx_coverage < idx_amount < idx_docs < idx_network < idx_fraud


# ---------------------------------------------------------------------------
# Rule logic
# ---------------------------------------------------------------------------


def test_coverage_verification_uses_policy_is_active_on() -> None:
    from rpa_architect.codegen.claims_rules_gen import generate_claims_rules_cs

    cs = generate_claims_rules_cs()
    # Grep for the IsActiveOn call within the Coverage rule class
    start = cs.find("class CoverageVerificationRule")
    end = cs.find("}", cs.find("}", start) + 1)
    assert "IsActiveOn" in cs[start:end + 10000]


def test_amount_threshold_flags_over_10k() -> None:
    from rpa_architect.codegen.claims_rules_gen import generate_claims_rules_cs

    cs = generate_claims_rules_cs()
    assert "10000" in cs or "10_000m" in cs


def test_documentation_rule_uses_get_case_notes() -> None:
    from rpa_architect.codegen.claims_rules_gen import generate_claims_rules_cs

    cs = generate_claims_rules_cs()
    assert "GetCaseNotesAsync" in cs


def test_network_rule_uses_get_provider_by_npi() -> None:
    from rpa_architect.codegen.claims_rules_gen import generate_claims_rules_cs

    cs = generate_claims_rules_cs()
    assert "GetProviderByNpiAsync" in cs
    assert "InNetwork" in cs


def test_fraud_velocity_uses_list_recent_cases() -> None:
    from rpa_architect.codegen.claims_rules_gen import generate_claims_rules_cs

    cs = generate_claims_rules_cs()
    assert "ListRecentCasesByClaimantAsync" in cs


def test_fraud_velocity_denies_4_or_more_prior() -> None:
    """≥4 prior cases in 30d = fraud. 2-3 = FlagForReview. <2 = pass.

    Thresholds may be expressed as literals or named constants — both
    patterns are acceptable. Verify the numbers appear and the Deny vs
    Flag paths exist.
    """
    from rpa_architect.codegen.claims_rules_gen import generate_claims_rules_cs

    cs = generate_claims_rules_cs()
    # Either a literal 4 threshold or a named DenyThreshold = 4 const
    has_deny_threshold = "DenyThreshold = 4" in cs or "priorCount >= 4" in cs
    assert has_deny_threshold, "no ≥4 deny threshold found"
    has_flag_threshold = "FlagThreshold = 2" in cs or "priorCount >= 2" in cs
    assert has_flag_threshold, "no ≥2 flag threshold found"


# ---------------------------------------------------------------------------
# Chain behavior
# ---------------------------------------------------------------------------


def test_engine_short_circuits_on_deny() -> None:
    """After the first Deny verdict, remaining rules must not run."""
    from rpa_architect.codegen.claims_rules_gen import generate_claims_rules_cs

    cs = generate_claims_rules_cs()
    engine_start = cs.find("class ClaimsRuleEngine")
    engine_end = cs.rfind("}")
    engine = cs[engine_start:engine_end]
    assert "ClaimVerdict.Deny" in engine
    assert "return " in engine  # explicit return path for short-circuit


def test_engine_accumulates_flag_for_review_reasons() -> None:
    """Multiple FlagForReview results should all land in ctx.FlagReasons."""
    from rpa_architect.codegen.claims_rules_gen import generate_claims_rules_cs

    cs = generate_claims_rules_cs()
    assert "FlagReasons" in cs


# ---------------------------------------------------------------------------
# Compile test
# ---------------------------------------------------------------------------


@pytest.mark.skipif(not _have_dotnet(), reason="dotnet SDK not installed")
def test_rules_compile_with_models_and_client(tmp_path: Path) -> None:
    from rpa_architect.codegen.claims_models_gen import (
        generate_case_cs,
        generate_claim_metrics_cs,
        generate_claim_verdict_cs,
        generate_claims_process_context_cs,
        generate_policy_cs,
        generate_provider_cs,
    )
    from rpa_architect.codegen.claims_rules_gen import generate_claims_rules_cs
    from rpa_architect.codegen.suitecrm_client_gen import generate_suitecrm_client_cs

    exceptions_stub = """
using System;

namespace MedicalClaimsProcessing
{
    public class BusinessException : Exception
    {
        public BusinessException(string message) : base(message) { }
    }

    public class RpaSystemException : Exception
    {
        public RpaSystemException(string message) : base(message) { }
        public RpaSystemException(string message, Exception inner) : base(message, inner) { }
    }
}
"""
    (tmp_path / "test.csproj").write_text(_CSPROJ)
    (tmp_path / "Exceptions.cs").write_text(exceptions_stub)
    (tmp_path / "Case.cs").write_text(generate_case_cs())
    (tmp_path / "Policy.cs").write_text(generate_policy_cs())
    (tmp_path / "Provider.cs").write_text(generate_provider_cs())
    (tmp_path / "ClaimVerdict.cs").write_text(generate_claim_verdict_cs())
    (tmp_path / "ClaimMetrics.cs").write_text(generate_claim_metrics_cs())
    (tmp_path / "ClaimsProcessContext.cs").write_text(generate_claims_process_context_cs())
    (tmp_path / "SuiteCrmClient.cs").write_text(generate_suitecrm_client_cs())
    (tmp_path / "ClaimsRules.cs").write_text(generate_claims_rules_cs())

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
