"""Tests for UiPath Orchestrator REST client (mocked HTTP)."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from rpa_architect.platform.sdk_client import Asset, JobStatus, QueueItem, UiPathClient


def _mock_response(status_code: int = 200, json_data: dict | None = None) -> httpx.Response:
    """Create a mock httpx.Response."""
    resp = MagicMock(spec=httpx.Response)
    resp.status_code = status_code
    resp.json.return_value = json_data or {}
    resp.raise_for_status = MagicMock()
    if status_code >= 400:
        resp.raise_for_status.side_effect = httpx.HTTPStatusError(
            f"HTTP {status_code}", request=MagicMock(), response=resp,
        )
    return resp


@pytest.fixture
def client() -> UiPathClient:
    return UiPathClient(
        url="https://cloud.uipath.com",
        tenant_id="test-tenant",
        client_id="test-client-id",
        client_secret="test-secret",
        org="test-org",
    )


@pytest.fixture
def mock_http() -> AsyncMock:
    return AsyncMock(spec=httpx.AsyncClient)


class TestAuthentication:
    @pytest.mark.asyncio
    async def test_auth_token_acquired(self, client: UiPathClient, mock_http: AsyncMock):
        mock_http.post.return_value = _mock_response(200, {
            "access_token": "test-token-abc",
            "expires_in": 3600,
        })

        with patch.object(client, "_http", mock_http):
            token = await client._ensure_token()

        assert token == "test-token-abc"
        mock_http.post.assert_called_once()
        call_args = mock_http.post.call_args
        assert "identity_/connect/token" in call_args[0][0]

    @pytest.mark.asyncio
    async def test_auth_failure_raises(self, client: UiPathClient, mock_http: AsyncMock):
        mock_http.post.return_value = _mock_response(401)

        with patch.object(client, "_http", mock_http):
            with pytest.raises(httpx.HTTPStatusError):
                await client._ensure_token()

    @pytest.mark.asyncio
    async def test_missing_credentials_raises(self):
        client = UiPathClient(url="https://cloud.uipath.com")
        with pytest.raises(RuntimeError, match="client_id and client_secret"):
            await client._ensure_token()


class TestQueueOperations:
    @pytest.mark.asyncio
    async def test_create_queue(self, client: UiPathClient, mock_http: AsyncMock):
        mock_http.post.return_value = _mock_response(200, {
            "access_token": "tok", "expires_in": 3600,
        })
        mock_http.request.return_value = _mock_response(200, {"Id": 42})

        with patch.object(client, "_http", mock_http):
            queue_id = await client.create_queue("TestQueue", "desc")

        assert queue_id == "42"
        req_call = mock_http.request.call_args
        assert req_call[0][0] == "POST"
        assert "QueueDefinitions" in req_call[0][1]

    @pytest.mark.asyncio
    async def test_add_queue_item(self, client: UiPathClient, mock_http: AsyncMock):
        mock_http.post.return_value = _mock_response(200, {
            "access_token": "tok", "expires_in": 3600,
        })
        mock_http.request.return_value = _mock_response(200, {"Id": 99})

        with patch.object(client, "_http", mock_http):
            item = await client.add_queue_item("Q1", "ref-1", {"key": "value"})

        assert isinstance(item, QueueItem)
        assert item.item_id == "99"
        assert item.reference == "ref-1"


class TestAssetOperations:
    @pytest.mark.asyncio
    async def test_get_asset(self, client: UiPathClient, mock_http: AsyncMock):
        mock_http.post.return_value = _mock_response(200, {
            "access_token": "tok", "expires_in": 3600,
        })
        mock_http.request.return_value = _mock_response(200, {
            "value": [{"Name": "MyAsset", "Value": "secret", "ValueType": "Text"}],
        })

        with patch.object(client, "_http", mock_http):
            asset = await client.get_asset("MyAsset")

        assert isinstance(asset, Asset)
        assert asset.name == "MyAsset"
        assert asset.value == "secret"

    @pytest.mark.asyncio
    async def test_get_asset_not_found(self, client: UiPathClient, mock_http: AsyncMock):
        mock_http.post.return_value = _mock_response(200, {
            "access_token": "tok", "expires_in": 3600,
        })
        mock_http.request.return_value = _mock_response(200, {"value": []})

        with patch.object(client, "_http", mock_http):
            with pytest.raises(LookupError, match="not found"):
                await client.get_asset("Missing")


class TestJobOperations:
    @pytest.mark.asyncio
    async def test_invoke_process(self, client: UiPathClient, mock_http: AsyncMock):
        mock_http.post.return_value = _mock_response(200, {
            "access_token": "tok", "expires_in": 3600,
        })
        mock_http.request.return_value = _mock_response(200, {
            "value": [{"Id": 123}],
        })

        with patch.object(client, "_http", mock_http):
            job_id = await client.invoke_process("release-key-1")

        assert job_id == "123"

    @pytest.mark.asyncio
    async def test_get_job_status(self, client: UiPathClient, mock_http: AsyncMock):
        mock_http.post.return_value = _mock_response(200, {
            "access_token": "tok", "expires_in": 3600,
        })
        mock_http.request.return_value = _mock_response(200, {
            "State": "Successful", "Info": "Completed",
        })

        with patch.object(client, "_http", mock_http):
            status = await client.get_job_status("123")

        assert isinstance(status, JobStatus)
        assert status.state == "Successful"


class TestFolderOperations:
    @pytest.mark.asyncio
    async def test_create_folder(self, client: UiPathClient, mock_http: AsyncMock):
        mock_http.post.return_value = _mock_response(200, {
            "access_token": "tok", "expires_in": 3600,
        })
        mock_http.request.return_value = _mock_response(200, {"Id": 7})

        with patch.object(client, "_http", mock_http):
            folder_id = await client.create_folder("MyFolder")

        assert folder_id == "7"

    @pytest.mark.asyncio
    async def test_get_folder_not_found(self, client: UiPathClient, mock_http: AsyncMock):
        mock_http.post.return_value = _mock_response(200, {
            "access_token": "tok", "expires_in": 3600,
        })
        mock_http.request.return_value = _mock_response(200, {"value": []})

        with patch.object(client, "_http", mock_http):
            with pytest.raises(LookupError, match="not found"):
                await client.get_folder("Missing")


class TestTokenRefresh:
    @pytest.mark.asyncio
    async def test_cached_token_reused(self, client: UiPathClient, mock_http: AsyncMock):
        """Token should not be re-fetched while still valid."""
        mock_http.post.return_value = _mock_response(200, {
            "access_token": "tok-1", "expires_in": 3600,
        })

        with patch.object(client, "_http", mock_http):
            tok1 = await client._ensure_token()
            tok2 = await client._ensure_token()

        assert tok1 == tok2 == "tok-1"
        assert mock_http.post.call_count == 1  # only one auth call

    @pytest.mark.asyncio
    async def test_expired_token_refreshed(self, client: UiPathClient, mock_http: AsyncMock):
        """Token should be re-fetched after expiry."""
        mock_http.post.return_value = _mock_response(200, {
            "access_token": "tok-new", "expires_in": 3600,
        })

        with patch.object(client, "_http", mock_http):
            # Force token to look expired
            client._token = "tok-old"
            client._token_expiry = 0.0
            tok = await client._ensure_token()

        assert tok == "tok-new"


class TestODataPagination:
    @pytest.mark.asyncio
    async def test_list_processes_follows_next_link(self, client: UiPathClient, mock_http: AsyncMock):
        mock_http.post.return_value = _mock_response(200, {
            "access_token": "tok", "expires_in": 3600,
        })

        page1 = {
            "value": [{"Key": "k1", "Name": "Proc1"}],
            "@odata.nextLink": "https://cloud.uipath.com/test-org/test-tenant/orchestrator_/odata/Releases?$skip=1",
        }
        page2 = {
            "value": [{"Key": "k2", "Name": "Proc2"}],
        }
        mock_http.request.side_effect = [
            _mock_response(200, page1),
            _mock_response(200, page2),
        ]

        with patch.object(client, "_http", mock_http):
            procs = await client.list_processes()

        assert len(procs) == 2
        assert procs[0]["name"] == "Proc1"
        assert procs[1]["name"] == "Proc2"
        assert mock_http.request.call_count == 2


class TestNetworkErrors:
    @pytest.mark.asyncio
    async def test_connection_error_propagates(self, client: UiPathClient, mock_http: AsyncMock):
        mock_http.post.return_value = _mock_response(200, {
            "access_token": "tok", "expires_in": 3600,
        })
        mock_http.request.side_effect = httpx.ConnectError("Connection refused")

        with patch.object(client, "_http", mock_http):
            with pytest.raises(httpx.ConnectError):
                await client.create_queue("test")

    @pytest.mark.asyncio
    async def test_server_error_raises(self, client: UiPathClient, mock_http: AsyncMock):
        mock_http.post.return_value = _mock_response(200, {
            "access_token": "tok", "expires_in": 3600,
        })
        mock_http.request.return_value = _mock_response(500)

        with patch.object(client, "_http", mock_http):
            with pytest.raises(httpx.HTTPStatusError):
                await client.get_asset("broken")
