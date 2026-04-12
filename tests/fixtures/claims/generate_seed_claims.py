"""Generate the deterministic 100-claim seed fixture for the SLA proof.

Run with:
    python tests/fixtures/claims/generate_seed_claims.py

Emits tests/fixtures/claims/seed_claims.json with:
  - 10 policies (1 expired for fault #1)
  - 15 providers (1 out-of-network for fault #3)
  - 100 cases (95 clean + 5 faulty at known indices)
  - fault_indices dict mapping fault_type → case index

Fault indices are spread across the 100-case sequence so the SLA run
encounters them at different times during the dispatch loop.
"""

from __future__ import annotations

import json
from pathlib import Path

OUTPUT = Path(__file__).parent / "seed_claims.json"

# Deterministic fault positions across the 100-case sequence.
FAULT_INDICES = {
    "expired_policy": 12,
    "fraud_velocity": 37,
    "out_of_network": 54,
    "missing_docs": 71,
    "amount_over_threshold": 88,
}

# Claimant names for the rotation (used by clean cases).
CLAIMANTS = [
    "Alice Johnson", "Bob Martinez", "Carol Nguyen", "David Patel",
    "Emma Wilson", "Frank Rodriguez", "Grace Kim", "Henry Brown",
    "Isabel Garcia", "Jack Thompson", "Karen Davis", "Luis Hernandez",
    "Maria Lopez", "Nathan Clark", "Olivia Wright", "Peter Anderson",
    "Quinn Walker", "Rachel Taylor", "Samuel Lewis", "Tina Chen",
]

# The fraud-velocity victim. Used ≥5 times.
FRAUD_VELOCITY_CLAIMANT = "Victor Vandermolen"

# Providers: 15 total, 14 in-network + 1 out-of-network.
PROVIDERS_IN_NETWORK = [
    {"npi": f"1{i:09d}", "name": f"In-Network Clinic {i}", "in_network": True,
     "specialty_code": code}
    for i, code in enumerate(
        ["207R00000X", "208000000X", "207X00000X", "207Q00000X", "208D00000X",
         "207T00000X", "207V00000X", "208600000X", "207W00000X", "207Y00000X",
         "207Z00000X", "208100000X", "208200000X", "208400000X"],
        start=1,
    )
]
OUT_OF_NETWORK_PROVIDER = {
    "npi": "9999999999",
    "name": "Out-of-Network Specialty",
    "in_network": False,
    "specialty_code": "207R00000X",
}
PROVIDERS = PROVIDERS_IN_NETWORK + [OUT_OF_NETWORK_PROVIDER]

# Policies: 10 total, 9 active + 1 expired.
ACTIVE_POLICIES = [
    {
        "policy_number": f"POL-100{i}",
        "holder": CLAIMANTS[i - 1],
        "coverage_start": "2025-01-01",
        "coverage_end": "2026-12-31",
        "deductible_remaining": 500.00 + i * 100,
        "out_of_pocket_max": 5000.00,
    }
    for i in range(1, 10)
]
EXPIRED_POLICY = {
    "policy_number": "POL-9999",
    "holder": "Expired Eddie",
    "coverage_start": "2022-01-01",
    "coverage_end": "2023-12-31",
    "deductible_remaining": 0.00,
    "out_of_pocket_max": 5000.00,
}
POLICIES = ACTIVE_POLICIES + [EXPIRED_POLICY]

# Procedure codes (realistic E&M + common medical codes).
PROCEDURE_CODES = [
    "99213", "99214", "99215", "99203", "99204", "99205",
    "93000", "80053", "85025", "71045",
]

DIAGNOSIS_CODES = [
    "M79.3", "I10", "E11.9", "J06.9", "K21.0", "R51", "M25.511",
    "R05", "R07.9", "G43.909",
]


def _build_clean_case(idx: int) -> dict:
    """Build a clean (non-faulty) case at the given 0-based index."""
    policy = ACTIVE_POLICIES[idx % len(ACTIVE_POLICIES)]
    return {
        "claim_id": f"CLM-{idx:05d}",
        "policy_number": policy["policy_number"],
        "claimant_name": policy["holder"],
        "diagnosis_code": DIAGNOSIS_CODES[idx % len(DIAGNOSIS_CODES)],
        "procedure_code": PROCEDURE_CODES[idx % len(PROCEDURE_CODES)],
        "total_amount": 200.00 + (idx % 50) * 15.00,
        "currency": "USD",
        "submitted_at": f"2026-04-{10 + (idx % 5):02d}T{(idx % 12) + 8:02d}:00:00Z",
        "provider_npi": PROVIDERS_IN_NETWORK[idx % len(PROVIDERS_IN_NETWORK)]["npi"],
        "notes": [
            {"filename": f"discharge_summary_{idx}.pdf", "content_b64": "JVBERi0xLjQKJSA="},
            {"filename": f"lab_results_{idx}.pdf", "content_b64": "JVBERi0xLjQKJSA="},
        ],
    }


def _inject_faults(cases: list[dict]) -> None:
    """Replace clean cases at fault indices with deliberately-broken ones."""
    # Fault 1: expired policy
    idx = FAULT_INDICES["expired_policy"]
    cases[idx] = {
        **_build_clean_case(idx),
        "policy_number": EXPIRED_POLICY["policy_number"],
        "claimant_name": EXPIRED_POLICY["holder"],
    }

    # Fault 2: fraud velocity — 5 cases total for same claimant, current is the 5th
    idx = FAULT_INDICES["fraud_velocity"]
    cases[idx] = {
        **_build_clean_case(idx),
        "claimant_name": FRAUD_VELOCITY_CLAIMANT,
    }
    # Inject 4 prior cases with the same claimant at earlier (clean) indices
    prior_slots = [2, 8, 20, 31]  # arbitrary positions before idx 37
    for slot in prior_slots:
        cases[slot] = {
            **cases[slot],
            "claimant_name": FRAUD_VELOCITY_CLAIMANT,
            "submitted_at": "2026-04-05T10:00:00Z",
        }

    # Fault 3: out-of-network provider
    idx = FAULT_INDICES["out_of_network"]
    cases[idx] = {
        **_build_clean_case(idx),
        "provider_npi": OUT_OF_NETWORK_PROVIDER["npi"],
    }

    # Fault 4: missing docs (only 1 note, procedure 99203 requires ≥2)
    idx = FAULT_INDICES["missing_docs"]
    cases[idx] = {
        **_build_clean_case(idx),
        "procedure_code": "99203",
        "notes": [{"filename": "incomplete.pdf", "content_b64": "JVBERi0xLjQKJSA="}],
    }

    # Fault 5: amount exceeds $10k threshold
    idx = FAULT_INDICES["amount_over_threshold"]
    cases[idx] = {
        **_build_clean_case(idx),
        "total_amount": 15000.00,
    }


def main() -> None:
    cases = [_build_clean_case(i) for i in range(100)]
    _inject_faults(cases)

    data = {
        "policies": POLICIES,
        "providers": PROVIDERS,
        "cases": cases,
        "fault_indices": FAULT_INDICES,
    }

    OUTPUT.write_text(json.dumps(data, indent=2), encoding="utf-8")
    print(f"wrote {OUTPUT} with {len(cases)} cases, "
          f"{len(POLICIES)} policies, {len(PROVIDERS)} providers")


if __name__ == "__main__":
    main()
