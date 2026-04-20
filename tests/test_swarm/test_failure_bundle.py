"""Tests for lifecycle.swarm.failure_bundle — Orchestrator failure capture.

We use httpx.MockTransport (no respx dep) to simulate Orchestrator responses.
"""

from __future__ import annotations

import io
import zipfile
from datetime import datetime, timezone

import httpx
import pytest

from rpa_architect.lifecycle.state import FailureBundle
from rpa_architect.lifecycle.swarm.failure_bundle import (
    FailureBundleFetcher,
    build_package_bytes,
)
from rpa_architect.platform.sdk_client import UiPathClient


def _make_nupkg(xaml_content: str) -> bytes:
    """Build an in-memory .nupkg (zip) containing a Main.xaml."""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("lib/net6.0-windows/Main.xaml", xaml_content)
        z.writestr("Invoice.nuspec", "<package />")
    return buf.getvalue()


SAMPLE_XAML = """<?xml version="1.0"?>
<Activity xmlns="http://schemas.microsoft.com/netfx/2009/xaml/activities"
          xmlns:ui="http://schemas.uipath.com/workflow/activities"
          xmlns:x="http://schemas.microsoft.com/winfx/2006/xaml">
  <Sequence DisplayName="Main"/>
</Activity>
"""


def _mock_transport_for_failure() -> httpx.MockTransport:
    """Mock Orchestrator that serves a faulted job, its logs, and a .nupkg."""
    nupkg_bytes = _make_nupkg(SAMPLE_XAML)

    def handler(request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        if "connect/token" in url:
            return httpx.Response(200, json={"access_token": "x", "expires_in": 3600})
        if "/Folders" in url and "$filter" in url:
            return httpx.Response(200, json={"value": [{"Id": 1}]})
        if "/Jobs(abc123)" in url:
            return httpx.Response(
                200,
                json={
                    "Key": "abc123",
                    "State": "Faulted",
                    "Info": "SelectorNotFoundException: Could not find UI element "
                    "matching <webctrl id='submit' />",
                    "StartTime": "2026-04-20T10:00:00Z",
                    "EndTime": "2026-04-20T10:00:05Z",
                    "ReleaseName": "Invoice",
                },
            )
        if "/RobotLogs" in url:
            return httpx.Response(
                200,
                json={
                    "value": [
                        {
                            "TimeStamp": "2026-04-20T10:00:04Z",
                            "Level": "Error",
                            "Message": "UiElement not found: <webctrl id='submit' />",
                        },
                        {
                            "TimeStamp": "2026-04-20T10:00:03Z",
                            "Level": "Info",
                            "Message": "Executing: Click Submit",
                        },
                    ]
                },
            )
        if "/Processes/UiPath.Server.Configuration.OData.DownloadPackage" in url:
            return httpx.Response(200, content=nupkg_bytes)
        if "/Processes" in url and "$filter" in url:
            return httpx.Response(
                200,
                json={"value": [{"Key": "Invoice", "Version": "1.0.0"}]},
            )
        if "/Releases" in url and "$filter" in url:
            return httpx.Response(
                200,
                json={"value": [{"Key": "rel-abc", "ProcessKey": "Invoice", "ProcessVersion": "1.0.0"}]},
            )
        return httpx.Response(404, json={"error": f"unexpected {url}"})

    return httpx.MockTransport(handler)


class TestFailureBundleFetcher:
    @pytest.mark.asyncio
    async def test_fetch_returns_failure_bundle(self) -> None:
        client = UiPathClient(
            url="https://cloud.uipath.com",
            org="myorg",
            tenant_name="mytenant",
            client_id="cid",
            client_secret="csec",
            folder="Default",
        )
        client._http = httpx.AsyncClient(transport=_mock_transport_for_failure())

        fetcher = FailureBundleFetcher(client)
        bundle = await fetcher.fetch("abc123")

        assert isinstance(bundle, FailureBundle)
        assert bundle.job_id == "abc123"
        assert bundle.state == "Faulted"
        assert "SelectorNotFoundException" in bundle.exception_message
        assert len(bundle.robot_logs) == 2
        assert bundle.process_key == "Invoice"

    @pytest.mark.asyncio
    async def test_fetch_includes_main_xaml_from_package(self) -> None:
        client = UiPathClient(
            url="https://cloud.uipath.com",
            org="myorg",
            tenant_name="mytenant",
            client_id="cid",
            client_secret="csec",
            folder="Default",
        )
        client._http = httpx.AsyncClient(transport=_mock_transport_for_failure())

        fetcher = FailureBundleFetcher(client)
        bundle = await fetcher.fetch("abc123")

        assert "Main.xaml" in bundle.xaml_files
        assert "<Sequence" in bundle.xaml_files["Main.xaml"]


class TestBuildPackageBytes:
    def test_extracts_single_main_xaml(self) -> None:
        nupkg = _make_nupkg(SAMPLE_XAML)
        xaml_files = build_package_bytes(nupkg)
        assert "Main.xaml" in xaml_files
        assert "<Sequence" in xaml_files["Main.xaml"]

    def test_ignores_non_xaml_entries(self) -> None:
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as z:
            z.writestr("lib/net6.0-windows/Main.xaml", SAMPLE_XAML)
            z.writestr("lib/net6.0-windows/project.json", "{}")
            z.writestr("Invoice.nuspec", "<package/>")
        xaml_files = build_package_bytes(buf.getvalue())
        assert list(xaml_files.keys()) == ["Main.xaml"]

    def test_extracts_multiple_xamls(self) -> None:
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as z:
            z.writestr("lib/net6.0-windows/Main.xaml", SAMPLE_XAML)
            z.writestr("lib/net6.0-windows/Framework/InitAllSettings.xaml", SAMPLE_XAML)
            z.writestr("lib/net6.0-windows/Process.xaml", SAMPLE_XAML)
        xaml_files = build_package_bytes(buf.getvalue())
        assert set(xaml_files.keys()) == {
            "Main.xaml",
            "Framework/InitAllSettings.xaml",
            "Process.xaml",
        }


class TestFailureBundleModel:
    def test_round_trip(self) -> None:
        bundle = FailureBundle(
            job_id="j1",
            process_key="Invoice",
            release_key="rel-1",
            state="Faulted",
            exception_message="boom",
            exception_type="SelectorNotFoundException",
            started_at=datetime(2026, 4, 20, tzinfo=timezone.utc),
            ended_at=datetime(2026, 4, 20, tzinfo=timezone.utc),
            robot_logs=[{"Level": "Error", "Message": "boom"}],
            xaml_files={"Main.xaml": SAMPLE_XAML},
            screenshot_paths=[],
            folder="Default",
        )
        dumped = bundle.model_dump()
        restored = FailureBundle.model_validate(dumped)
        assert restored.job_id == "j1"
        assert restored.exception_type == "SelectorNotFoundException"
