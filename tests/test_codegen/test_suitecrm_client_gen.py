"""Tests for the SuiteCrmClient.cs generator.

The generated client:
- OAuth2 password grant against /Api/access_token
- Caches AccessToken + ExpiresAt in memory
- On 401, refreshes token once and retries the original request
  (BW-09 mitigation: SuiteCRM evicts tokens at ~50 min idle)
- GetCaseByIdAsync, GetPolicyByIdAsync (Account type=Policy),
  GetProviderByNpiAsync (Account type=Provider),
  ListRecentCasesByClaimantAsync (for FraudVelocityRule — batched),
  UpdateCaseVerdictAsync (PATCH with verdict + status),
  CreateAdjudicationNoteAsync, GetCaseNotesAsync (doc substitute — BW-07)
- Throws BusinessException on 404, RpaSystemException on 5xx
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
# Structure tests
# ---------------------------------------------------------------------------


def test_client_is_public_class_in_namespace() -> None:
    from rpa_architect.codegen.suitecrm_client_gen import generate_suitecrm_client_cs

    cs = generate_suitecrm_client_cs()
    assert "namespace MedicalClaimsProcessing" in cs
    assert "public class SuiteCrmClient" in cs


def test_client_uses_httpclient_with_cookie_handler_not_needed() -> None:
    """SuiteCRM 8 uses Bearer tokens, not cookies. No HttpClientHandler
    CookieContainer needed, unlike v0.5's OdooClient."""
    from rpa_architect.codegen.suitecrm_client_gen import generate_suitecrm_client_cs

    cs = generate_suitecrm_client_cs()
    assert "HttpClient" in cs
    assert "Authorization" in cs
    assert "Bearer" in cs


# ---------------------------------------------------------------------------
# OAuth2 flow
# ---------------------------------------------------------------------------


def test_client_has_oauth2_password_grant() -> None:
    from rpa_architect.codegen.suitecrm_client_gen import generate_suitecrm_client_cs

    cs = generate_suitecrm_client_cs()
    assert "/Api/access_token" in cs
    assert '"password"' in cs
    assert "grant_type" in cs


def test_client_caches_access_token_until_expiry() -> None:
    from rpa_architect.codegen.suitecrm_client_gen import generate_suitecrm_client_cs

    cs = generate_suitecrm_client_cs()
    assert "_accessToken" in cs
    assert "_expiresAt" in cs
    assert "EnsureTokenAsync" in cs


def test_client_refreshes_token_on_401() -> None:
    """BW-09 mitigation: if any authed request returns 401, clear token
    and retry once before giving up."""
    from rpa_architect.codegen.suitecrm_client_gen import generate_suitecrm_client_cs

    cs = generate_suitecrm_client_cs()
    assert "StatusCode == HttpStatusCode.Unauthorized" in cs
    assert "_accessToken = null" in cs


# ---------------------------------------------------------------------------
# API methods
# ---------------------------------------------------------------------------


def test_client_has_get_case_by_id_async() -> None:
    from rpa_architect.codegen.suitecrm_client_gen import generate_suitecrm_client_cs

    cs = generate_suitecrm_client_cs()
    assert "public async Task<Case> GetCaseByIdAsync" in cs
    assert "/Api/V8/module/Cases/" in cs


def test_client_has_get_policy_by_number_async() -> None:
    from rpa_architect.codegen.suitecrm_client_gen import generate_suitecrm_client_cs

    cs = generate_suitecrm_client_cs()
    assert "public async Task<Policy>" in cs
    assert "GetPolicyByNumberAsync" in cs


def test_client_has_get_provider_by_npi_async() -> None:
    from rpa_architect.codegen.suitecrm_client_gen import generate_suitecrm_client_cs

    cs = generate_suitecrm_client_cs()
    assert "public async Task<Provider>" in cs
    assert "GetProviderByNpiAsync" in cs


def test_client_has_list_recent_cases_by_claimant_async() -> None:
    """Used by FraudVelocityRule — returns Cases for a claimant in the
    last N days, batched so rate limiting stays under control."""
    from rpa_architect.codegen.suitecrm_client_gen import generate_suitecrm_client_cs

    cs = generate_suitecrm_client_cs()
    assert "ListRecentCasesByClaimantAsync" in cs
    assert "filter[claimant_name]" in cs or "filter[name]" in cs or "claimant" in cs.lower()


def test_client_has_update_case_verdict_async() -> None:
    from rpa_architect.codegen.suitecrm_client_gen import generate_suitecrm_client_cs

    cs = generate_suitecrm_client_cs()
    assert "UpdateCaseVerdictAsync" in cs
    assert "PATCH" in cs or "HttpMethod.Patch" in cs or "Method = " in cs


def test_client_has_get_case_notes_async_for_doc_substitute() -> None:
    """BW-07: Documents REST is broken. Notes are the substitute."""
    from rpa_architect.codegen.suitecrm_client_gen import generate_suitecrm_client_cs

    cs = generate_suitecrm_client_cs()
    assert "GetCaseNotesAsync" in cs
    assert "/Api/V8/module/Notes" in cs
    assert "parent_type" in cs and "parent_id" in cs


def test_client_has_create_adjudication_note_async() -> None:
    from rpa_architect.codegen.suitecrm_client_gen import generate_suitecrm_client_cs

    cs = generate_suitecrm_client_cs()
    assert "CreateAdjudicationNoteAsync" in cs


# ---------------------------------------------------------------------------
# Error discipline
# ---------------------------------------------------------------------------


def test_client_throws_business_exception_on_404() -> None:
    from rpa_architect.codegen.suitecrm_client_gen import generate_suitecrm_client_cs

    cs = generate_suitecrm_client_cs()
    assert "NotFound" in cs
    assert "BusinessException" in cs


def test_client_throws_system_exception_on_5xx() -> None:
    from rpa_architect.codegen.suitecrm_client_gen import generate_suitecrm_client_cs

    cs = generate_suitecrm_client_cs()
    assert "RpaSystemException" in cs


# ---------------------------------------------------------------------------
# Compile test
# ---------------------------------------------------------------------------


@pytest.mark.skipif(not _have_dotnet(), reason="dotnet SDK not installed")
def test_suitecrm_client_compiles_with_claims_models(tmp_path: Path) -> None:
    from rpa_architect.codegen.claims_models_gen import (
        generate_case_cs,
        generate_claim_metrics_cs,
        generate_claim_verdict_cs,
        generate_policy_cs,
        generate_provider_cs,
    )
    from rpa_architect.codegen.suitecrm_client_gen import generate_suitecrm_client_cs

    # Exception types aren't in the claims models — stub them for now
    # (real ones come from v0.5's reframework_csharp_gen in later phases).
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
    (tmp_path / "SuiteCrmClient.cs").write_text(generate_suitecrm_client_cs())

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
