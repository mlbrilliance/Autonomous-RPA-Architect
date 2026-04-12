"""Tests for parsing the medical claims PDD — EV2-8.

The parser must recognise the new multi-process topology marker and
the SuiteCRM system entry, and emit a ProcessIR with:
  - process_topology = "dispatcher_performer_reporter"
  - a SuiteCRM system in the systems list
  - the 5 business rules
  - the queue config
"""

from __future__ import annotations

from pathlib import Path

import pytest

from rpa_architect.ir.schema import ProcessIR
from rpa_architect.parser.pdd_parser import parse_pdd

PDD = Path(__file__).parent.parent / "fixtures" / "pdds" / "medical_claims.md"


@pytest.fixture(scope="module")
def claims_ir() -> ProcessIR:
    return parse_pdd(PDD)


def test_parser_extracts_process_name(claims_ir: ProcessIR) -> None:
    assert "claims" in claims_ir.process_name.lower()


def test_parser_recognises_multi_process_topology(claims_ir: ProcessIR) -> None:
    assert claims_ir.process_topology == "dispatcher_performer_reporter"


def test_parser_extracts_suitecrm_system(claims_ir: ProcessIR) -> None:
    system_names = {s.name for s in claims_ir.systems}
    assert any("suitecrm" in n.lower() for n in system_names), (
        f"no SuiteCRM system found in {system_names}"
    )


def test_parser_extracts_medicalclaim_transaction(claims_ir: ProcessIR) -> None:
    txn_names = {t.name.lower() for t in claims_ir.transactions}
    # Accept either "MedicalClaim" or "ProcessClaim" or similar
    assert any("claim" in n for n in txn_names), (
        f"no claim transaction found in {txn_names}"
    )


def test_parser_extracts_config_keys(claims_ir: ProcessIR) -> None:
    config_keys = set(claims_ir.config.keys())
    # At least the key runtime config should be present
    assert "QueueName" in config_keys or any(
        "queue" in k.lower() for k in config_keys
    )


def test_ir_round_trips_through_json(claims_ir: ProcessIR) -> None:
    json_str = claims_ir.model_dump_json()
    reloaded = ProcessIR.model_validate_json(json_str)
    assert reloaded.process_topology == "dispatcher_performer_reporter"
