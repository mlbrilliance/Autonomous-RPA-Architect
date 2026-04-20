"""Staging validator: deploy a patched package to a staging folder and run it."""

from __future__ import annotations

from datetime import datetime, timezone

import httpx
import pytest

from rpa_architect.lifecycle.state import FailureBundle, FixCandidate, StagingResult, XamlPatch
from rpa_architect.lifecycle.swarm.staging_validator import StagingValidator
from rpa_architect.platform.sdk_client import UiPathClient


def _mock_transport(outcome: str) -> httpx.MockTransport:
    def handler(request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        if "connect/token" in url:
            return httpx.Response(200, json={"access_token": "x", "expires_in": 3600})
        if "/Folders" in url and "$filter" in url:
            return httpx.Response(200, json={"value": [{"Id": 7}]})
        if "/Releases" in url and request.method == "POST":
            return httpx.Response(200, json={"Key": "rel-staging", "ProcessKey": "Invoice-staging"})
        if "/Releases" in url and "$filter" in url:
            return httpx.Response(200, json={"value": [{"Key": "rel-staging"}]})
        if "StartJobs" in url:
            return httpx.Response(200, json={"value": [{"Key": "job-staging-1", "Id": 9}]})
        if "/Jobs(" in url:
            return httpx.Response(
                200,
                json={
                    "Key": "job-staging-1",
                    "State": outcome,
                    "Info": "" if outcome == "Successful" else "boom",
                    "StartTime": "2026-04-20T12:00:00Z",
                    "EndTime": "2026-04-20T12:00:05Z",
                },
            )
        if "UploadPackage" in url or "Packages" in url:
            return httpx.Response(200, json={"Key": "Invoice-staging"})
        return httpx.Response(404, json={"error": f"unexpected {url}"})

    return httpx.MockTransport(handler)


def _client() -> UiPathClient:
    c = UiPathClient(
        url="https://cloud.uipath.com",
        org="myorg",
        tenant_name="mytenant",
        client_id="cid",
        client_secret="csec",
        folder="Shared/Staging",
    )
    return c


def _candidate() -> FixCandidate:
    return FixCandidate(
        specialist="selector_repair",
        confidence=0.8,
        diagnosis_category="selector_drift",
        patches=[
            XamlPatch(
                file_path="Main.xaml",
                target_xpath="/a:Activity",
                attribute="Selector",
                old_value="old",
                new_value="new",
            )
        ],
        patched_xaml={"Main.xaml": "<Activity>patched</Activity>"},
    )


def _bundle() -> FailureBundle:
    return FailureBundle(
        job_id="prod-job-1",
        process_key="Invoice",
        state="Faulted",
        exception_message="boom",
        exception_type="SelectorNotFoundException",
        started_at=datetime(2026, 4, 20, tzinfo=timezone.utc),
        ended_at=datetime(2026, 4, 20, tzinfo=timezone.utc),
    )


class TestStagingValidator:
    @pytest.mark.asyncio
    async def test_success_outcome(self) -> None:
        client = _client()
        client._http = httpx.AsyncClient(transport=_mock_transport("Successful"))
        validator = StagingValidator(client=client, staging_folder="Shared/Staging")
        result = await validator.validate(_bundle(), _candidate())
        assert isinstance(result, StagingResult)
        assert result.success is True
        assert result.candidate_specialist == "selector_repair"
        assert result.job_id == "job-staging-1"

    @pytest.mark.asyncio
    async def test_failure_outcome(self) -> None:
        client = _client()
        client._http = httpx.AsyncClient(transport=_mock_transport("Faulted"))
        validator = StagingValidator(client=client, staging_folder="Shared/Staging")
        result = await validator.validate(_bundle(), _candidate())
        assert result.success is False
        assert "boom" in result.message

    @pytest.mark.asyncio
    async def test_refuses_zero_patch_candidate(self) -> None:
        client = _client()
        client._http = httpx.AsyncClient(transport=_mock_transport("Successful"))
        validator = StagingValidator(client=client, staging_folder="Shared/Staging")
        candidate = FixCandidate(
            specialist="business_rule",
            confidence=0.9,
            diagnosis_category="business_rule_violation",
        )
        with pytest.raises(ValueError, match="no patches"):
            await validator.validate(_bundle(), candidate)
