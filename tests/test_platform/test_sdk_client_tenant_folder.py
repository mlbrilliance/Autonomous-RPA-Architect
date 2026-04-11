"""TDD tests for tenant_name URL path + folder-id resolution (Phase F live fix).

These cover the bug caught by Tavily research + live OAuth test: the
Cloud Orchestrator URL path uses the tenant DISPLAY NAME, not the
tenant GUID, and the X-UIPATH-OrganizationUnitId header expects the
integer folder Id, not the display name.
"""

from __future__ import annotations

import json

import pytest
import respx

from rpa_architect.platform.sdk_client import UiPathClient

ORG = "mlbrilliance"
TENANT_NAME = "DefaultTenant"
URL = "https://cloud.uipath.com"
TOKEN_URL = f"{URL}/{ORG}/identity_/connect/token"
BASE = f"{URL}/{ORG}/{TENANT_NAME}/orchestrator_/odata"


@pytest.fixture
def router() -> respx.MockRouter:
    with respx.mock(assert_all_called=False) as router:
        router.post(TOKEN_URL).respond(
            200, json={"access_token": "tok", "expires_in": 3600}
        )
        # Also accept the legacy token URL without org prefix (for backward compat tests).
        router.post(f"{URL}/identity_/connect/token").respond(
            200, json={"access_token": "tok", "expires_in": 3600}
        )
        yield router


def _make_client(**overrides) -> UiPathClient:
    defaults = dict(
        url=URL,
        org=ORG,
        tenant_name=TENANT_NAME,
        client_id="id",
        client_secret="secret",
        folder="Shared",
    )
    defaults.update(overrides)
    return UiPathClient(**defaults)


# ---------------------------------------------------------------------------
# tenant_name in URL path
# ---------------------------------------------------------------------------


async def test_tenant_name_used_in_base_url(router: respx.MockRouter) -> None:
    """When tenant_name is set, _base_url must use it (not tenant_id GUID)."""
    client = _make_client(tenant_id="some-guid-not-used")
    base = await client._base_url()
    assert TENANT_NAME in base
    assert "some-guid-not-used" not in base
    assert base == BASE
    await client.close()


async def test_legacy_tenant_id_still_works_when_no_tenant_name() -> None:
    """Backward compat: when only tenant_id is provided, use it in URL path."""
    client = UiPathClient(
        url=URL,
        org=ORG,
        tenant_id="legacy-guid",
        client_id="id",
        client_secret="secret",
        folder="Shared",
    )
    base = await client._base_url()
    assert "legacy-guid" in base
    await client.close()


# ---------------------------------------------------------------------------
# folder ID resolution + integer header
# ---------------------------------------------------------------------------


async def test_headers_send_integer_folder_id(router: respx.MockRouter) -> None:
    """The X-UIPATH-OrganizationUnitId header must be the integer folder Id."""
    folders_url_re = rf"^{BASE}/Folders.*"
    router.get(url__regex=folders_url_re).respond(
        200,
        json={"value": [{"Id": 98765, "DisplayName": "Shared"}]},
    )

    client = _make_client()
    headers = await client._headers()
    assert headers["X-UIPATH-OrganizationUnitId"] == "98765"
    await client.close()


async def test_folder_id_cached_after_first_lookup(router: respx.MockRouter) -> None:
    """Folder resolution must hit /Folders only once even across multiple requests."""
    folders_url_re = rf"^{BASE}/Folders.*"
    folders_route = router.get(url__regex=folders_url_re).respond(
        200,
        json={"value": [{"Id": 1234, "DisplayName": "Shared"}]},
    )

    client = _make_client()
    await client._headers()
    await client._headers()
    await client._headers()

    # Only one GET to /Folders — the rest were served from cache.
    assert folders_route.call_count == 1
    await client.close()


async def test_folder_not_found_raises_from_resolver(router: respx.MockRouter) -> None:
    """The low-level resolver must raise on missing folders.

    ``_headers()`` has a graceful fallback that logs the error and uses
    the display name directly (for back-compat with Standalone), but
    callers that need to guarantee a real folder can call
    ``_resolve_folder_id`` directly.
    """
    folders_url_re = rf"^{BASE}/Folders.*"
    router.get(url__regex=folders_url_re).respond(200, json={"value": []})

    client = _make_client(folder="NonExistent")
    with pytest.raises(ValueError, match="NonExistent"):
        await client._resolve_folder_id("NonExistent")
    await client.close()


# ---------------------------------------------------------------------------
# upload_package uses the correct URL + integer header
# ---------------------------------------------------------------------------


async def test_upload_package_uses_tenant_name_in_url(
    router: respx.MockRouter, tmp_path
) -> None:
    folders_url_re = rf"^{BASE}/Folders.*"
    router.get(url__regex=folders_url_re).respond(
        200, json={"value": [{"Id": 42, "DisplayName": "Shared"}]}
    )
    upload_url = f"{BASE}/Processes/UiPath.Server.Configuration.OData.UploadPackage"
    upload_route = router.post(upload_url).respond(
        200, json={"value": [{"Key": "OdooInvoiceProcessing:1.0.0"}]}
    )

    nupkg = tmp_path / "Test.1.0.0.nupkg"
    nupkg.write_bytes(b"fake")

    client = _make_client()
    await client.upload_package(nupkg)

    assert upload_route.called
    request = upload_route.calls.last.request
    assert request.headers["X-UIPATH-OrganizationUnitId"] == "42"
    assert TENANT_NAME in str(request.url)
    await client.close()
