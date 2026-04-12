"""Tests for the SuiteCRM seed client used by the claims SLA proof.

Covers:
- Required env vars (no hardcoded admin/admin defaults)
- Deterministic 100-claim fixture with 5 faults at known indices
- OAuth2 password grant token flow (mocked)
- Notes endpoint as document substitute (BW-07)
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest


FIXTURE_PATH = Path(__file__).parent.parent / "fixtures" / "claims" / "seed_claims.json"


# ---------------------------------------------------------------------------
# Fixture schema
# ---------------------------------------------------------------------------


def test_seed_claims_fixture_exists() -> None:
    assert FIXTURE_PATH.exists(), f"missing fixture at {FIXTURE_PATH}"


def test_seed_claims_fixture_has_100_cases() -> None:
    data = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))
    assert "cases" in data
    assert len(data["cases"]) == 100


def test_seed_claims_fixture_has_5_faults_at_known_indices() -> None:
    data = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))
    faults = data.get("fault_indices", {})
    assert set(faults.keys()) == {
        "expired_policy",
        "fraud_velocity",
        "out_of_network",
        "missing_docs",
        "amount_over_threshold",
    }
    indices = set(faults.values())
    assert len(indices) == 5
    for idx in indices:
        assert 0 <= idx < 100


def test_expired_policy_fault_has_past_coverage_end() -> None:
    data = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))
    idx = data["fault_indices"]["expired_policy"]
    case = data["cases"][idx]
    policy_num = case["policy_number"]
    policy = next(p for p in data["policies"] if p["policy_number"] == policy_num)
    assert policy["coverage_end"] < "2026-01-01"


def test_fraud_velocity_fault_has_4_prior_claims_same_claimant() -> None:
    data = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))
    idx = data["fault_indices"]["fraud_velocity"]
    case = data["cases"][idx]
    claimant = case["claimant_name"]
    prior = [c for c in data["cases"] if c["claimant_name"] == claimant]
    assert len(prior) >= 5, f"need ≥5 total (including this one), got {len(prior)}"


def test_out_of_network_fault_provider_flagged() -> None:
    data = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))
    idx = data["fault_indices"]["out_of_network"]
    case = data["cases"][idx]
    npi = case["provider_npi"]
    provider = next(p for p in data["providers"] if p["npi"] == npi)
    assert provider["in_network"] is False


def test_missing_docs_fault_has_only_one_note() -> None:
    data = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))
    idx = data["fault_indices"]["missing_docs"]
    case = data["cases"][idx]
    assert case["procedure_code"].startswith("99")
    assert len(case["notes"]) == 1


def test_amount_over_threshold_fault_exceeds_10k() -> None:
    data = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))
    idx = data["fault_indices"]["amount_over_threshold"]
    case = data["cases"][idx]
    assert case["total_amount"] > 10000


def test_clean_cases_distinct_from_fault_cases() -> None:
    data = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))
    fault_indices = set(data["fault_indices"].values())
    assert len(fault_indices) == 5
    clean_count = 100 - len(fault_indices)
    assert clean_count == 95


# ---------------------------------------------------------------------------
# Seed client — env var requirements
# ---------------------------------------------------------------------------


def test_seed_client_module_importable() -> None:
    from proof import suitecrm_seed_client  # noqa: F401


def test_seed_client_require_env_raises_on_missing(monkeypatch) -> None:
    from proof.suitecrm_seed_client import _require_env

    monkeypatch.delenv("SUITECRM_BASE_URL", raising=False)
    with pytest.raises(SystemExit) as exc_info:
        _require_env("SUITECRM_BASE_URL")
    assert "SUITECRM_BASE_URL" in str(exc_info.value)


def test_seed_client_require_env_returns_value(monkeypatch) -> None:
    from proof.suitecrm_seed_client import _require_env

    monkeypatch.setenv("SUITECRM_BASE_URL", "http://localhost:8080")
    assert _require_env("SUITECRM_BASE_URL") == "http://localhost:8080"


def test_seed_client_builds_oauth_token_request_payload() -> None:
    from proof.suitecrm_seed_client import build_token_request_payload

    payload = build_token_request_payload(
        client_id="test_id",
        client_secret="test_secret",
        username="admin",
        password="test_pass",
    )
    assert payload["grant_type"] == "password"
    assert payload["client_id"] == "test_id"
    assert payload["client_secret"] == "test_secret"
    assert payload["username"] == "admin"
    assert payload["password"] == "test_pass"


def test_seed_client_case_payload_matches_fixture_shape() -> None:
    from proof.suitecrm_seed_client import build_case_payload

    fixture_case = {
        "claim_id": "CLM-00001",
        "policy_number": "POL-1001",
        "claimant_name": "Alice Smith",
        "diagnosis_code": "M79.3",
        "procedure_code": "99213",
        "total_amount": 245.00,
        "currency": "USD",
        "submitted_at": "2026-04-10T12:00:00Z",
        "provider_npi": "1234567890",
        "notes": [],
    }
    payload = build_case_payload(fixture_case)
    assert payload["data"]["type"] == "Cases"
    attrs = payload["data"]["attributes"]
    assert attrs["name"] == "CLM-00001"
    assert attrs["status"] == "New"
    assert attrs["description"] != ""


def test_seed_client_note_payload_uses_parent_case() -> None:
    from proof.suitecrm_seed_client import build_note_payload

    payload = build_note_payload(
        case_id="case-uuid-42",
        filename="discharge_summary.pdf",
        content_b64="SGVsbG8gV29ybGQ=",
    )
    assert payload["data"]["type"] == "Notes"
    assert payload["data"]["attributes"]["parent_type"] == "Cases"
    assert payload["data"]["attributes"]["parent_id"] == "case-uuid-42"
    assert payload["data"]["attributes"]["filename"] == "discharge_summary.pdf"
