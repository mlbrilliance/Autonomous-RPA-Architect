"""Tests for the queue-transaction methods added in EV2-4.

Uses respx to mock Orchestrator OData. Covers:
  - start_transaction (lease next item in queue)
  - set_transaction_result (mark Successful or Failed)
  - get_queue_item (fetch by id)
  - list_queue_items (with status filter)
  - release_queue_item (abandon in-progress item)
"""

from __future__ import annotations

import json

import httpx
import pytest
import respx

from rpa_architect.platform.sdk_client import UiPathClient

ORG = "testorg"
TENANT = "DefaultTenant"
TOKEN_URL = f"https://cloud.uipath.com/{ORG}/identity_/connect/token"
BASE = f"https://cloud.uipath.com/{ORG}/{TENANT}/orchestrator_/odata"


def _make_client() -> UiPathClient:
    return UiPathClient(
        url="https://cloud.uipath.com",
        org=ORG,
        tenant_name=TENANT,
        client_id="test-client",
        client_secret="test-secret",
        folder="Shared",
    )


@pytest.fixture(autouse=True)
def _mock_token() -> respx.MockRouter:
    with respx.mock(assert_all_called=False) as router:
        router.post(TOKEN_URL).respond(
            200, json={"access_token": "fake-bearer", "expires_in": 3600}
        )
        # Folder resolution — return id=42 for any folder lookup.
        router.get(url__regex=rf"{BASE}/Folders.*").respond(
            200, json={"value": [{"Id": 42}]}
        )
        yield router


# ---------------------------------------------------------------------------
# start_transaction
# ---------------------------------------------------------------------------


async def test_start_transaction_posts_correct_odata_action(
    _mock_token: respx.MockRouter,
) -> None:
    url = f"{BASE}/Queues/UiPathODataSvc.StartTransaction"
    route = _mock_token.post(url).respond(
        200,
        json={
            "Id": 12345,
            "Reference": "CLM-00042",
            "Key": "abc-xyz",
            "SpecificContent": {"claim_id": "CLM-00042"},
            "Status": "InProgress",
        },
    )

    client = _make_client()
    item = await client.start_transaction("MedicalClaims", "robot-01")

    assert item is not None
    assert item.item_id == "12345"
    assert item.reference == "CLM-00042"
    assert item.specific_content == {"claim_id": "CLM-00042"}
    assert route.called
    body = json.loads(route.calls.last.request.content)
    assert body["transactionData"]["Name"] == "MedicalClaims"
    assert body["transactionData"]["RobotIdentifier"] == "robot-01"
    await client.close()


async def test_start_transaction_returns_none_on_empty_queue(
    _mock_token: respx.MockRouter,
) -> None:
    url = f"{BASE}/Queues/UiPathODataSvc.StartTransaction"
    _mock_token.post(url).respond(204)

    client = _make_client()
    item = await client.start_transaction("MedicalClaims", "robot-01")
    assert item is None
    await client.close()


# ---------------------------------------------------------------------------
# set_transaction_result
# ---------------------------------------------------------------------------


async def test_set_transaction_result_marks_successful(
    _mock_token: respx.MockRouter,
) -> None:
    url = f"{BASE}/QueueItems(12345)/UiPathODataSvc.SetTransactionResult"
    route = _mock_token.post(url).respond(200, json={})

    client = _make_client()
    await client.set_transaction_result(
        transaction_id="12345",
        is_successful=True,
        output={"verdict": "AutoApprove"},
    )

    assert route.called
    body = json.loads(route.calls.last.request.content)
    assert body["transactionResult"]["IsSuccessful"] is True
    assert body["transactionResult"]["Output"] == {"verdict": "AutoApprove"}
    await client.close()


async def test_set_transaction_result_records_business_exception(
    _mock_token: respx.MockRouter,
) -> None:
    url = f"{BASE}/QueueItems(67890)/UiPathODataSvc.SetTransactionResult"
    route = _mock_token.post(url).respond(200, json={})

    client = _make_client()
    await client.set_transaction_result(
        transaction_id="67890",
        is_successful=False,
        output={"verdict": "Deny"},
        business_error="policy expired",
    )

    assert route.called
    body = json.loads(route.calls.last.request.content)
    result = body["transactionResult"]
    assert result["IsSuccessful"] is False
    dump = json.dumps(result)
    assert "BusinessException" in dump
    assert "policy expired" in dump
    await client.close()


# ---------------------------------------------------------------------------
# get_queue_item
# ---------------------------------------------------------------------------


async def test_get_queue_item_returns_specific_content(
    _mock_token: respx.MockRouter,
) -> None:
    url = f"{BASE}/QueueItems(12345)"
    _mock_token.get(url).respond(
        200,
        json={
            "Id": 12345,
            "Reference": "CLM-00042",
            "Status": "InProgress",
            "SpecificContent": {"claim_id": "CLM-00042", "payload_b64": "abc"},
        },
    )

    client = _make_client()
    item = await client.get_queue_item("12345")
    assert item.item_id == "12345"
    assert item.reference == "CLM-00042"
    assert item.specific_content["payload_b64"] == "abc"
    await client.close()


# ---------------------------------------------------------------------------
# list_queue_items
# ---------------------------------------------------------------------------


async def test_list_queue_items_filters_by_status(
    _mock_token: respx.MockRouter,
) -> None:
    route = _mock_token.get(url__regex=rf"{BASE}/QueueItems\?.*").respond(
        200,
        json={
            "value": [
                {
                    "Id": 1,
                    "Reference": "CLM-1",
                    "Status": "Successful",
                    "SpecificContent": {},
                },
                {
                    "Id": 2,
                    "Reference": "CLM-2",
                    "Status": "Successful",
                    "SpecificContent": {},
                },
            ]
        },
    )

    client = _make_client()
    items = await client.list_queue_items("MedicalClaims", status="Successful", top=10)

    assert len(items) == 2
    assert all(i.status == "Successful" for i in items)
    assert route.called
    req_url = str(route.calls.last.request.url)
    assert "Status%20eq%20'Successful'" in req_url
    assert "MedicalClaims" in req_url
    await client.close()


# ---------------------------------------------------------------------------
# release_queue_item
# ---------------------------------------------------------------------------


async def test_release_queue_item_abandons_in_progress(
    _mock_token: respx.MockRouter,
) -> None:
    url = f"{BASE}/QueueItems(555)/UiPathODataSvc.SetTransactionResult"
    route = _mock_token.post(url).respond(200, json={})

    client = _make_client()
    await client.release_queue_item("555", retry=True)
    assert route.called
    await client.close()
