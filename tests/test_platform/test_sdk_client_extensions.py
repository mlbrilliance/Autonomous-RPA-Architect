"""Offline tests for the SDK client methods added in Phase F.

Uses :mod:`respx` to mock httpx calls so we can verify request/response
contracts without hitting a real Orchestrator. Live coverage is in
``tests/test_platform/test_sdk_client_live.py`` (gated behind
``@pytest.mark.live`` and skipped by default).
"""

from __future__ import annotations

import json
from pathlib import Path

import httpx
import pytest
import respx

from rpa_architect.platform.sdk_client import Asset, UiPathClient

ORG = "testorg"
TENANT = "tenant-guid"
URL = "https://cloud.uipath.com"
TOKEN_URL = f"{URL}/{ORG}/identity_/connect/token"
BASE = f"{URL}/{ORG}/{TENANT}/orchestrator_/odata"


def _make_client() -> UiPathClient:
    return UiPathClient(
        url=URL,
        org=ORG,
        tenant_id=TENANT,
        client_id="test-id",
        client_secret="test-secret",
        folder="Shared",
    )


@pytest.fixture(autouse=True)
def _mock_token() -> respx.MockRouter:
    with respx.mock(assert_all_called=False) as router:
        router.post(TOKEN_URL).respond(
            200, json={"access_token": "fake-bearer", "expires_in": 3600}
        )
        yield router


# ---------------------------------------------------------------------------
# OAuth scopes
# ---------------------------------------------------------------------------


async def test_ensure_token_requests_all_required_scopes(
    _mock_token: respx.MockRouter,
) -> None:
    client = _make_client()
    await client._ensure_token()
    # The autouse fixture's token route was hit; inspect the request body.
    token_route = _mock_token.routes[0]
    assert token_route.called
    body = token_route.calls.last.request.content.decode()
    for scope in (
        "OR.Execution",
        "OR.Jobs",
        "OR.Queues",
        "OR.Assets",
        "OR.Folders",
        "OR.Machines",
        "OR.Robots",
        "OR.Settings",
    ):
        assert scope in body, f"missing scope {scope}"
    await client.close()


# ---------------------------------------------------------------------------
# upload_package
# ---------------------------------------------------------------------------


async def test_upload_package_posts_multipart_to_uploadpackage_endpoint(
    tmp_path: Path,
    _mock_token: respx.MockRouter,
) -> None:
    nupkg = tmp_path / "Test.1.0.0.nupkg"
    nupkg.write_bytes(b"PK\x03\x04fake nupkg bytes")

    upload_url = (
        f"{BASE}/Processes/UiPath.Server.Configuration.OData.UploadPackage"
    )
    upload_route = _mock_token.post(upload_url).respond(
        200, json={"value": [{"Key": "Test:1.0.0", "ProcessKey": "Test_env"}]}
    )

    client = _make_client()
    result = await client.upload_package(nupkg)

    assert upload_route.called
    request = upload_route.calls.last.request
    # Multipart content-type set automatically by httpx.
    assert b"multipart/form-data" in request.headers["content-type"].encode()
    assert b"PK\x03\x04fake nupkg bytes" in request.content
    assert "value" in result
    await client.close()


async def test_upload_package_raises_on_missing_file(tmp_path: Path) -> None:
    client = _make_client()
    with pytest.raises(FileNotFoundError):
        await client.upload_package(tmp_path / "nonexistent.nupkg")
    await client.close()


async def test_upload_package_propagates_http_error(
    tmp_path: Path,
    _mock_token: respx.MockRouter,
) -> None:
    nupkg = tmp_path / "Test.1.0.0.nupkg"
    nupkg.write_bytes(b"x")
    upload_url = (
        f"{BASE}/Processes/UiPath.Server.Configuration.OData.UploadPackage"
    )
    _mock_token.post(upload_url).respond(401, json={"error": "unauthorized"})

    client = _make_client()
    with pytest.raises(httpx.HTTPStatusError):
        await client.upload_package(nupkg)
    await client.close()


# ---------------------------------------------------------------------------
# ensure_queue
# ---------------------------------------------------------------------------


async def test_ensure_queue_returns_existing_id_when_present(
    _mock_token: respx.MockRouter,
) -> None:
    list_url = f"{BASE}/QueueDefinitions"
    _mock_token.get(url__regex=rf"^{list_url}.*").respond(
        200, json={"value": [{"Id": 42, "Name": "OdooInvoices"}]}
    )

    client = _make_client()
    qid = await client.ensure_queue("OdooInvoices")
    assert qid == "42"
    await client.close()


async def test_ensure_queue_creates_when_missing(
    _mock_token: respx.MockRouter,
) -> None:
    list_url = f"{BASE}/QueueDefinitions"
    _mock_token.get(url__regex=rf"^{list_url}.*").respond(200, json={"value": []})
    create_route = _mock_token.post(list_url).respond(
        200, json={"Id": 123, "Name": "OdooInvoices"}
    )

    client = _make_client()
    qid = await client.ensure_queue("OdooInvoices", description="Inbox")
    assert qid == "123"
    assert create_route.called
    body = json.loads(create_route.calls.last.request.content)
    assert body["Name"] == "OdooInvoices"
    assert body["Description"] == "Inbox"
    await client.close()


# ---------------------------------------------------------------------------
# ensure_asset
# ---------------------------------------------------------------------------


async def test_ensure_asset_creates_when_missing(
    _mock_token: respx.MockRouter,
) -> None:
    """ensure_asset tries POST first; on 200/201 it's done (no GET/PUT)."""
    list_url = f"{BASE}/Assets"
    create_route = _mock_token.post(list_url).respond(
        200, json={"Id": 1, "Name": "OdooBaseURL", "ValueType": "Text"}
    )

    client = _make_client()
    asset = await client.ensure_asset("OdooBaseURL", "https://x")
    assert isinstance(asset, Asset)
    assert asset.value == "https://x"
    assert create_route.called
    # The new POST payload must include StringValue + ValueScope.
    body = json.loads(create_route.calls.last.request.content)
    assert body["StringValue"] == "https://x"
    assert body["ValueScope"] == "Global"
    await client.close()


async def test_ensure_asset_updates_existing(_mock_token: respx.MockRouter) -> None:
    """ensure_asset tries POST first; on 409 it GETs by filter and PUTs."""
    list_url = f"{BASE}/Assets"
    # 1. POST returns 409 (already exists).
    _mock_token.post(list_url).respond(
        409, json={"message": "The name OdooBaseURL is already used.", "errorCode": 1001}
    )
    # 2. GET $filter returns the existing record.
    _mock_token.get(url__regex=rf"^{list_url}.*").respond(
        200, json={"value": [{"Id": 7, "Name": "OdooBaseURL", "StringValue": "old"}]}
    )
    # 3. PUT updates it.
    update_route = _mock_token.put(f"{BASE}/Assets(7)").respond(204)

    client = _make_client()
    asset = await client.ensure_asset("OdooBaseURL", "https://new.ngrok-free.app")
    assert asset.value == "https://new.ngrok-free.app"
    assert update_route.called
    body = json.loads(update_route.calls.last.request.content)
    # 2025.10 schema: StringValue (not Value) + ValueScope=Global + ValueType.
    assert body["StringValue"] == "https://new.ngrok-free.app"
    assert body["ValueScope"] == "Global"
    assert body["ValueType"] == "Text"
    await client.close()


async def test_ensure_asset_tolerates_empty_filter_after_409(
    _mock_token: respx.MockRouter,
) -> None:
    """When POST 409s and GET $filter returns empty (Cloud scoping quirk),
    ensure_asset must still succeed (no-op) instead of raising."""
    list_url = f"{BASE}/Assets"
    _mock_token.post(list_url).respond(
        409, json={"message": "already exists", "errorCode": 1001}
    )
    _mock_token.get(url__regex=rf"^{list_url}.*").respond(200, json={"value": []})

    client = _make_client()
    asset = await client.ensure_asset("OdooBaseURL", "https://x")
    assert asset.value == "https://x"
    await client.close()


# ---------------------------------------------------------------------------
# get_robot_logs (smoke check that the new path still works)
# ---------------------------------------------------------------------------


async def test_get_robot_logs_filters_by_job_id(_mock_token: respx.MockRouter) -> None:
    # Match any RobotLogs query — httpx URL-encodes the OData filter spaces.
    logs_route = _mock_token.get(url__regex=rf"^{BASE}/RobotLogs.*").respond(
        200,
        json={
            "value": [
                {"Id": 1, "Level": "Info", "Message": "Started", "TimeStamp": "2026-04-11T00:00:00Z"},
                {"Id": 2, "Level": "Info", "Message": "Done", "TimeStamp": "2026-04-11T00:01:00Z"},
            ]
        },
    )

    client = _make_client()
    logs = await client.get_robot_logs("job-1")
    assert len(logs) == 2
    assert logs[0]["Message"] == "Started"
    # The captured request must reference the job key.
    captured_url = str(logs_route.calls.last.request.url)
    assert "job-1" in captured_url
    await client.close()
