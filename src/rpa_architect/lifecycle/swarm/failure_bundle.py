"""Fetch and assemble a :class:`FailureBundle` from UiPath Orchestrator.

The :class:`FailureBundleFetcher` composes three Orchestrator endpoints:

1. ``GET Jobs({id})`` — state, exception info, ReleaseName, timing.
2. ``GET RobotLogs?$filter=JobKey eq '{id}'`` — per-step execution log.
3. ``POST Processes/UiPath.Server.Configuration.OData.DownloadPackage`` —
   the deployed ``.nupkg`` as bytes; we unzip it and surface every
   ``.xaml`` entry.

The resulting :class:`FailureBundle` is the only input the swarm's
specialists consume — they never talk to Orchestrator directly.
"""

from __future__ import annotations

import io
import logging
import re
import zipfile
from datetime import datetime
from typing import Any

import httpx

from rpa_architect.lifecycle.state import FailureBundle
from rpa_architect.platform.sdk_client import UiPathClient

logger = logging.getLogger("rpa_architect.lifecycle.swarm.failure_bundle")


class FailureBundleFetcher:
    """Composer that turns a job id into a :class:`FailureBundle`."""

    def __init__(self, client: UiPathClient) -> None:
        self._client = client

    async def fetch(self, job_id: str) -> FailureBundle:
        job = await self._client.get_job_details(job_id)
        logs = await self._client.get_robot_logs(job_id)

        release_name = str(job.get("ReleaseName", ""))
        release_key = await _lookup_release_key(self._client, release_name)
        package_bytes = await self._client.download_package_nupkg(release_name)
        xaml_files = build_package_bytes(package_bytes) if package_bytes else {}

        info = str(job.get("Info", ""))
        exception_type = _parse_exception_type(info)

        return FailureBundle(
            job_id=job_id,
            process_key=release_name,
            release_key=release_key,
            state=str(job.get("State", "")),
            exception_message=info,
            exception_type=exception_type,
            started_at=_parse_ts(job.get("StartTime")),
            ended_at=_parse_ts(job.get("EndTime")),
            robot_logs=list(logs),
            xaml_files=xaml_files,
            screenshot_paths=_extract_screenshot_paths(logs),
            folder=self._client._folder,  # intentional: read client's configured folder
        )


def build_package_bytes(nupkg_bytes: bytes) -> dict[str, str]:
    """Extract every ``.xaml`` entry from a ``.nupkg`` into a relative-path map.

    UiPath packages embed XAML under ``lib/net6.0-windows/`` (Portable) or
    ``lib/net45/`` (legacy). We strip the library prefix so downstream code
    sees paths rooted at the project (``Main.xaml``, ``Framework/Init.xaml``).
    """
    out: dict[str, str] = {}
    with zipfile.ZipFile(io.BytesIO(nupkg_bytes)) as z:
        for name in z.namelist():
            if not name.endswith(".xaml"):
                continue
            rel = _strip_lib_prefix(name)
            content = z.read(name).decode("utf-8", errors="replace")
            out[rel] = content
    return out


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------


_LIB_PREFIX_RE = re.compile(r"^lib/[^/]+/")


def _strip_lib_prefix(name: str) -> str:
    return _LIB_PREFIX_RE.sub("", name)


_EXCEPTION_RE = re.compile(r"\b([A-Z][A-Za-z0-9_]*Exception)\b")


def _parse_exception_type(info: str) -> str:
    """Heuristically pull an exception class name from job info text."""
    m = _EXCEPTION_RE.search(info or "")
    return m.group(1) if m else ""


def _parse_ts(value: Any) -> datetime | None:
    if not value:
        return None
    if isinstance(value, datetime):
        return value
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None


def _extract_screenshot_paths(logs: list[dict[str, Any]]) -> list[str]:
    """Look for screenshot references in robot logs.

    UiPath attaches screenshot URLs via ``screenshotUrl`` / ``ScreenshotFileName``
    fields on error-level entries. We surface whatever we find; callers decide
    whether to fetch them.
    """
    out: list[str] = []
    for entry in logs:
        for key in ("screenshotUrl", "ScreenshotFileName", "ScreenshotUrl"):
            val = entry.get(key)
            if val:
                out.append(str(val))
    return out


async def _lookup_release_key(client: UiPathClient, release_name: str) -> str:
    if not release_name:
        return ""
    try:
        data = await client._request(
            "GET",
            f"Releases?$filter=Name eq '{release_name}'&$top=1",
        )
        items = data.get("value", [])
        if items:
            return str(items[0].get("Key", ""))
    except httpx.HTTPStatusError as exc:
        logger.debug("release key lookup failed for %s: %s", release_name, exc)
    return ""
