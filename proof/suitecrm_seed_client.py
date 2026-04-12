"""Async httpx helper to seed a local SuiteCRM 8 instance for the SLA proof.

Used exclusively by ``proof/run_sla_claims.py`` to populate the SuiteCRM
database with:
  - 10 policies (1 expired)
  - 15 providers (1 out-of-network)
  - 100 Cases (95 clean + 5 deliberately faulty)
  - Notes attached to each Case (doc substitute — SuiteCRM 8 REST document
    upload is broken, Issue #10794)

Reads its configuration from env vars (no hardcoded defaults):
  SUITECRM_BASE_URL   — e.g. http://localhost:8080
  SUITECRM_CLIENT_ID  — OAuth2 client id
  SUITECRM_CLIENT_SECRET
  SUITECRM_USERNAME   — login you set up in the SuiteCRM UI
  SUITECRM_PASSWORD

All four of CLIENT_ID / CLIENT_SECRET / USERNAME / PASSWORD are required —
we never fall back to admin/admin. See proof/suitecrm/.env.example.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Any


def _require_env(name: str) -> str:
    """Return an env var's value, or SystemExit if unset.

    We deliberately avoid a hardcoded fallback to prevent secret leakage.
    """
    val = os.environ.get(name)
    if not val:
        raise SystemExit(
            f"error: {name} not set. Copy proof/suitecrm/.env.example to "
            "proof/suitecrm/.env, fill in your local values, and source it "
            "before running this script."
        )
    return val


def build_token_request_payload(
    *,
    client_id: str,
    client_secret: str,
    username: str,
    password: str,
) -> dict[str, str]:
    """Build the OAuth2 password-grant payload for SuiteCRM 8.

    Endpoint: POST {SUITECRM_BASE_URL}/Api/access_token
    """
    return {
        "grant_type": "password",
        "client_id": client_id,
        "client_secret": client_secret,
        "username": username,
        "password": password,
        "scope": "",
    }


def build_case_payload(case: dict[str, Any]) -> dict[str, Any]:
    """Build a JSON:API-compliant payload for creating a SuiteCRM Case.

    Uses the /Api/V8/module/Cases endpoint which expects JSON:API format:
      { "data": { "type": "Cases", "attributes": {...} } }

    We store the claim_id in `name` (SuiteCRM's case_number-style field)
    and embed the rest of the clinical metadata in a structured description
    so the dispatcher can parse it back out without needing custom fields.
    """
    description = (
        f"policy_number={case['policy_number']}\n"
        f"claimant_name={case['claimant_name']}\n"
        f"diagnosis_code={case['diagnosis_code']}\n"
        f"procedure_code={case['procedure_code']}\n"
        f"total_amount={case['total_amount']}\n"
        f"currency={case['currency']}\n"
        f"submitted_at={case['submitted_at']}\n"
        f"provider_npi={case['provider_npi']}\n"
    )
    return {
        "data": {
            "type": "Cases",
            "attributes": {
                "name": case["claim_id"],
                "status": "New",
                "priority": "P2",
                "description": description,
            },
        }
    }


def build_note_payload(
    *,
    case_id: str,
    filename: str,
    content_b64: str,
) -> dict[str, Any]:
    """Build a JSON:API payload for creating a SuiteCRM Note linked to a Case.

    Notes are used as the document substitute because Documents REST upload
    is broken in SuiteCRM 8 (GitHub Issue #10794, reopened Apr 2026).

    BW-13b: SuiteCRM 8's JSON:API **also** rejects inline file uploads via
    the Notes endpoint — sending ``filename`` + ``file_mime_type`` +
    ``file_contents`` in one POST returns 400 Bad Request. The workaround
    is to record only the ``name`` + ``description`` metadata; the rules
    engine counts attached Notes rather than reading the file contents,
    so the presence of the Note is what matters for
    ``DocumentationCompletenessRule``.
    """
    return {
        "data": {
            "type": "Notes",
            "attributes": {
                "name": filename,
                "parent_type": "Cases",
                "parent_id": case_id,
                "description": f"Synthetic doc ref: {filename}",
            },
        }
    }


async def _get_token(client, base_url: str, payload: dict) -> str:
    """Exchange password credentials for an access token."""
    resp = await client.post(
        f"{base_url}/Api/access_token",
        json=payload,
        headers={"Content-Type": "application/json"},
        timeout=30.0,
    )
    resp.raise_for_status()
    return resp.json()["access_token"]


async def seed_all(fixture_path: Path) -> dict[str, int]:
    """Seed policies → providers → cases → notes into SuiteCRM.

    Returns counts per entity type. Raises SystemExit if env is missing.
    """
    import httpx

    base_url = _require_env("SUITECRM_BASE_URL")
    client_id = _require_env("SUITECRM_CLIENT_ID")
    client_secret = _require_env("SUITECRM_CLIENT_SECRET")
    username = _require_env("SUITECRM_USERNAME")
    password = _require_env("SUITECRM_PASSWORD")

    data = json.loads(fixture_path.read_text(encoding="utf-8"))

    # SuiteCRM 8 is slow — each POST takes ~1s. With 100 cases × 3+
    # related writes that's ~300+ s of sync calls. Default 5s timeout
    # isn't enough.
    async with httpx.AsyncClient(timeout=120.0) as http:
        token = await _get_token(
            http,
            base_url,
            build_token_request_payload(
                client_id=client_id,
                client_secret=client_secret,
                username=username,
                password=password,
            ),
        )
        auth_headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/vnd.api+json",
            "Accept": "application/vnd.api+json",
        }

        # Policies and providers — SuiteCRM doesn't ship with these modules,
        # so we store them as Accounts with a `type` discriminator.
        policies_created = 0
        for policy in data["policies"]:
            # SuiteCRM 8 JSON:API POST goes to /Api/V8/module (no type
            # suffix) — the type lives in the payload body. A POST to
            # /Api/V8/module/Accounts returns 405 Method Not Allowed.
            resp = await http.post(
                f"{base_url}/Api/V8/module",
                json={
                    "data": {
                        "type": "Accounts",
                        "attributes": {
                            "name": policy["policy_number"],
                            "account_type": "Policy",
                            "description": (
                                f"holder={policy['holder']}\n"
                                f"coverage_start={policy['coverage_start']}\n"
                                f"coverage_end={policy['coverage_end']}\n"
                                f"deductible_remaining={policy['deductible_remaining']}\n"
                                f"out_of_pocket_max={policy['out_of_pocket_max']}\n"
                            ),
                        },
                    }
                },
                headers=auth_headers,
            )
            resp.raise_for_status()
            policies_created += 1

        providers_created = 0
        for provider in data["providers"]:
            resp = await http.post(
                f"{base_url}/Api/V8/module",
                json={
                    "data": {
                        "type": "Accounts",
                        "attributes": {
                            "name": provider["npi"],
                            "account_type": "Provider",
                            "description": (
                                f"name={provider['name']}\n"
                                f"in_network={provider['in_network']}\n"
                                f"specialty_code={provider['specialty_code']}\n"
                            ),
                        },
                    }
                },
                headers=auth_headers,
            )
            resp.raise_for_status()
            providers_created += 1

        cases_created = 0
        notes_created = 0
        for case in data["cases"]:
            resp = await http.post(
                f"{base_url}/Api/V8/module",
                json=build_case_payload(case),
                headers=auth_headers,
            )
            resp.raise_for_status()
            case_id = resp.json()["data"]["id"]
            cases_created += 1

            for note in case.get("notes", []):
                note_resp = await http.post(
                    f"{base_url}/Api/V8/module",
                    json=build_note_payload(
                        case_id=case_id,
                        filename=note["filename"],
                        content_b64=note["content_b64"],
                    ),
                    headers=auth_headers,
                )
                note_resp.raise_for_status()
                notes_created += 1

    return {
        "policies": policies_created,
        "providers": providers_created,
        "cases": cases_created,
        "notes": notes_created,
    }


def main(argv: list[str] | None = None) -> int:
    import asyncio

    fixture_path = Path(__file__).resolve().parent.parent / "tests" / "fixtures" / "claims" / "seed_claims.json"
    if not fixture_path.exists():
        print(f"error: fixture not found at {fixture_path}", file=sys.stderr)
        return 2

    counts = asyncio.run(seed_all(fixture_path))
    print(f"seeded: {counts}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
