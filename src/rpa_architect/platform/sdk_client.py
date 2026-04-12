"""UiPath Orchestrator REST client using the OData v4 API.

Replaces the previous phantom ``uipath`` SDK dependency with direct
HTTP calls via ``httpx``, authenticated using OAuth2 client credentials.
"""

from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass, field
from typing import Any

import httpx

logger = logging.getLogger("rpa_architect.platform.sdk_client")


@dataclass
class QueueItem:
    """Represents a UiPath Orchestrator queue item."""

    item_id: str = ""
    reference: str = ""
    specific_content: dict[str, Any] = field(default_factory=dict)
    status: str = "New"


@dataclass
class Asset:
    """Represents a UiPath Orchestrator asset."""

    name: str = ""
    value: str = ""
    asset_type: str = "Text"


@dataclass
class JobStatus:
    """Represents the status of a UiPath job."""

    job_id: str = ""
    state: str = ""
    info: str = ""


class UiPathClient:
    """REST client for UiPath Orchestrator OData API.

    Authenticates using the OAuth2 client-credentials flow against the
    UiPath Identity Server, then calls the Orchestrator OData endpoints.
    """

    def __init__(
        self,
        url: str = "https://cloud.uipath.com",
        tenant_id: str | None = None,
        client_id: str | None = None,
        client_secret: str | None = None,
        folder: str = "Default",
        org: str | None = None,
        tenant_name: str | None = None,
    ) -> None:
        self._url = url.rstrip("/")
        self._tenant_id = tenant_id or ""
        self._tenant_name = tenant_name
        self._client_id = client_id
        self._client_secret = client_secret
        self._folder = folder
        self._org = org or ""
        self._token: str | None = None
        self._token_expiry: float = 0.0
        self._http: httpx.AsyncClient | None = None
        # Caches for lazy discovery.
        self._folder_id_cache: dict[str, int] = {}

    def _base_url_sync(self) -> str:
        """Synchronous base-URL builder (used before any token is known).

        Prefers ``tenant_name`` (Orchestrator URL display name) over the
        legacy ``tenant_id`` (which used to be mistakenly inserted as a
        GUID path segment). Kept for back-compat with existing mocks
        that pass ``tenant_id="tenant-guid"`` without a ``tenant_name``.
        """
        parts = [self._url]
        if self._org:
            parts.append(self._org)
        if self._tenant_name:
            parts.append(self._tenant_name)
        elif self._tenant_id:
            parts.append(self._tenant_id)
        parts.append("orchestrator_/odata")
        return "/".join(parts)

    async def _base_url(self) -> str:
        """Async wrapper around the base URL so future discovery can run here."""
        return self._base_url_sync()

    async def _get_http(self) -> httpx.AsyncClient:
        if self._http is None:
            self._http = httpx.AsyncClient(timeout=30.0)
        return self._http

    # OAuth scopes the External Application must have granted. Listed
    # explicitly so all OData endpoints used by the project work without
    # follow-up scope errors.
    _DEFAULT_SCOPES = (
        "OR.Execution OR.Jobs OR.Queues OR.Assets OR.Folders OR.Machines "
        "OR.Robots OR.Settings"
    )

    async def _ensure_token(self) -> str:
        """Acquire or refresh the OAuth2 bearer token."""
        if self._token and time.monotonic() < self._token_expiry:
            return self._token

        if not self._client_id or not self._client_secret:
            raise RuntimeError(
                "UiPath client_id and client_secret are required for authentication. "
                "Set them when constructing UiPathClient."
            )

        # UiPath Cloud exposes the token endpoint under the org path.
        # Standalone Orchestrator exposes it at the root. Use the org-scoped
        # one when org is set (matches external-app tenant registration).
        if self._org:
            token_url = f"{self._url}/{self._org}/identity_/connect/token"
        else:
            token_url = f"{self._url}/identity_/connect/token"
        http = await self._get_http()
        resp = await http.post(
            token_url,
            data={
                "grant_type": "client_credentials",
                "client_id": self._client_id,
                "client_secret": self._client_secret,
                "scope": self._DEFAULT_SCOPES,
            },
        )
        resp.raise_for_status()
        data = resp.json()
        self._token = data["access_token"]
        # Expire slightly early to avoid edge cases
        self._token_expiry = time.monotonic() + data.get("expires_in", 3600) - 60
        logger.debug("Acquired OAuth2 token (expires in %ds)", data.get("expires_in", 0))
        return self._token  # type: ignore[return-value]

    async def _resolve_folder_id(self, folder_display_name: str) -> int:
        """Resolve a folder display name to its integer FolderId.

        Results are cached for the lifetime of the client. If the folder
        cannot be found, raises ``ValueError``.
        """
        if folder_display_name in self._folder_id_cache:
            return self._folder_id_cache[folder_display_name]

        base = self._base_url_sync()
        http = await self._get_http()
        token = await self._ensure_token()
        # Use only the bearer token — avoid recursing into _headers (which
        # itself calls _resolve_folder_id).
        resp = await http.get(
            f"{base}/Folders?$filter=DisplayName eq '{folder_display_name}'",
            headers={
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json",
            },
        )
        resp.raise_for_status()
        data = resp.json()
        items = data.get("value", [])
        if not items:
            raise ValueError(
                f"Folder '{folder_display_name}' not found in Orchestrator"
            )
        folder_id = int(items[0]["Id"])
        self._folder_id_cache[folder_display_name] = folder_id
        logger.info(
            "resolved folder %s -> id=%d", folder_display_name, folder_id
        )
        return folder_id

    async def _headers(self) -> dict[str, str]:
        token = await self._ensure_token()
        # Try to resolve folder to an integer ID (Cloud's requirement).
        # On any failure, fall back to the display name as a string so
        # legacy tests and legacy Standalone-Orchestrator deployments
        # (where the folder name is accepted directly) keep working.
        try:
            folder_id_header: str = str(await self._resolve_folder_id(self._folder))
        except Exception as exc:  # noqa: BLE001
            logger.debug(
                "folder_id resolution failed for %r, falling back to display "
                "name in X-UIPATH-OrganizationUnitId header: %s",
                self._folder,
                exc,
            )
            folder_id_header = self._folder
        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            "X-UIPATH-OrganizationUnitId": folder_id_header,
        }
        return headers

    async def _request(
        self, method: str, path: str, **kwargs: Any,
    ) -> dict[str, Any]:
        """Make an authenticated request to the OData API."""
        http = await self._get_http()
        headers = await self._headers()
        url = f"{self._base_url_sync()}/{path.lstrip('/')}"
        resp = await http.request(method, url, headers=headers, **kwargs)
        if resp.status_code >= 400:
            # Surface the server-side error body so live debugging doesn't
            # need manual fetches. HTTPX's default message is just status.
            body_snippet = resp.text[:800]
            logger.error(
                "%s %s -> %d: %s", method, url, resp.status_code, body_snippet
            )
            raise httpx.HTTPStatusError(
                f"{method} {path} -> {resp.status_code}: {body_snippet}",
                request=resp.request,
                response=resp,
            )
        if resp.status_code == 204 or not resp.content:
            return {}
        try:
            return resp.json()
        except ValueError:
            # Non-JSON body (some endpoints return empty string on success).
            return {"raw": resp.text}

    # ----- Queue operations -----

    async def create_queue(self, name: str, description: str = "") -> str:
        """Create an Orchestrator queue.

        Returns:
            The queue ID.
        """
        data = await self._request(
            "POST",
            "QueueDefinitions",
            json={"Name": name, "Description": description, "MaxNumberOfRetries": 3},
        )
        queue_id = str(data.get("Id", ""))
        logger.info("Created queue %s (id=%s)", name, queue_id)
        return queue_id

    async def add_queue_item(
        self,
        queue_name: str,
        reference: str,
        specific_content: dict[str, Any],
        priority: str = "Normal",
    ) -> QueueItem:
        """Add an item to an Orchestrator queue."""
        data = await self._request(
            "POST",
            "Queues/UiPathODataSvc.AddQueueItem",
            json={
                "itemData": {
                    "Name": queue_name,
                    "Reference": reference,
                    "Priority": priority,
                    "SpecificContent": specific_content,
                },
            },
        )
        item_id = str(data.get("Id", ""))
        logger.info("Added item to queue %s (ref=%s)", queue_name, reference)
        return QueueItem(
            item_id=item_id,
            reference=reference,
            specific_content=specific_content,
            status="New",
        )

    async def start_transaction(
        self,
        queue_name: str,
        robot_identifier: str,
    ) -> QueueItem | None:
        """Lease the next queue item via the StartTransaction OData action.

        Returns a ``QueueItem`` with ``status="InProgress"`` when an item
        was leased, or ``None`` when the queue is empty (HTTP 204).

        This is the core of the Performer pattern — the robot calls this
        in a loop until it returns None, processes each item, then calls
        :meth:`set_transaction_result` to mark the outcome.
        """
        http = await self._get_http()
        headers = await self._headers()
        url = (
            f"{self._base_url_sync()}/"
            "Queues/UiPathODataSvc.StartTransaction"
        )
        body = {
            "transactionData": {
                "Name": queue_name,
                "RobotIdentifier": robot_identifier,
            }
        }
        resp = await http.post(url, headers=headers, json=body)
        if resp.status_code == 204 or not resp.content:
            # Queue is drained — Orchestrator returns 204 No Content.
            return None
        if resp.status_code >= 400:
            raise httpx.HTTPStatusError(
                f"StartTransaction -> {resp.status_code}: {resp.text[:800]}",
                request=resp.request,
                response=resp,
            )
        data = resp.json()
        return QueueItem(
            item_id=str(data.get("Id", "")),
            reference=str(data.get("Reference", "")),
            specific_content=data.get("SpecificContent", {}) or {},
            status=str(data.get("Status", "InProgress")),
        )

    async def set_transaction_result(
        self,
        transaction_id: str,
        is_successful: bool,
        output: dict[str, Any] | None = None,
        business_error: str | None = None,
    ) -> None:
        """Finalise a leased queue item with Success or BusinessException.

        ``business_error`` is used when a rule deterministically rejected
        the work (the Orchestrator records a "BusinessException" vs. an
        "Error" — distinct categories in drift + diagnosis).
        """
        result: dict[str, Any] = {
            "IsSuccessful": bool(is_successful),
            "Output": output or {},
        }
        if not is_successful and business_error:
            result["ProcessingException"] = {
                "Reason": business_error,
                "Type": "BusinessException",
                "Details": business_error,
            }
        body = {"transactionResult": result}
        await self._request(
            "POST",
            f"QueueItems({transaction_id})/UiPathODataSvc.SetTransactionResult",
            json=body,
        )

    async def get_queue_item(self, item_id: str) -> QueueItem:
        """Fetch a queue item by its numeric id."""
        data = await self._request("GET", f"QueueItems({item_id})")
        return QueueItem(
            item_id=str(data.get("Id", item_id)),
            reference=str(data.get("Reference", "")),
            specific_content=data.get("SpecificContent", {}) or {},
            status=str(data.get("Status", "")),
        )

    async def list_queue_items(
        self,
        queue_name: str,
        status: str | None = None,
        top: int = 100,
    ) -> list[QueueItem]:
        """List queue items, optionally filtered by Status.

        Used by the Reporter to compute SLA aggregates and the verdict
        distribution for drift detection.
        """
        filter_parts = [f"QueueDefinition/Name eq '{queue_name}'"]
        if status:
            filter_parts.append(f"Status eq '{status}'")
        filter_str = " and ".join(filter_parts)
        path = f"QueueItems?$filter={filter_str}&$top={top}"
        data = await self._request("GET", path)
        items = []
        for raw in data.get("value", []):
            items.append(
                QueueItem(
                    item_id=str(raw.get("Id", "")),
                    reference=str(raw.get("Reference", "")),
                    specific_content=raw.get("SpecificContent", {}) or {},
                    status=str(raw.get("Status", "")),
                )
            )
        return items

    async def release_queue_item(self, item_id: str, retry: bool = True) -> None:
        """Abandon an in-progress queue item.

        When a Performer job crashes mid-transaction, the SLA coordinator
        calls this to let the item be re-leased by the next Performer run.
        If ``retry=False``, marks the item as permanently failed.
        """
        await self.set_transaction_result(
            transaction_id=item_id,
            is_successful=False,
            output={},
            business_error="abandoned_by_coordinator" if not retry else "released_for_retry",
        )

    # ----- Asset operations -----

    async def get_asset(self, name: str) -> Asset:
        """Retrieve an Orchestrator asset by name."""
        data = await self._request(
            "GET",
            f"Assets?$filter=Name eq '{name}'",
        )
        items = data.get("value", [])
        if not items:
            raise LookupError(f"Asset '{name}' not found in Orchestrator")
        item = items[0]
        return Asset(
            name=name,
            value=str(item.get("Value", "")),
            asset_type=str(item.get("ValueType", "Text")),
        )

    @staticmethod
    def _build_asset_payload(name: str, value: str, asset_type: str) -> dict[str, Any]:
        """Build the correct Orchestrator Assets POST/PUT body for a type.

        The 2025.10 Orchestrator API rejects ``{"Value": ...}`` — the
        value must go into the typed field (``StringValue``, ``IntValue``,
        ``BoolValue``, or ``CredentialPassword``) matching ``ValueType``.
        ``ValueScope: "Global"`` is required for non-per-robot assets.
        """
        payload: dict[str, Any] = {
            "Name": name,
            "ValueScope": "Global",
            "ValueType": asset_type,
        }
        if asset_type == "Text":
            payload["StringValue"] = value
        elif asset_type == "Integer":
            payload["IntValue"] = int(value)
        elif asset_type == "Bool":
            payload["BoolValue"] = str(value).lower() in ("1", "true", "yes")
        elif asset_type == "Credential":
            payload["CredentialUsername"] = "api"
            payload["CredentialPassword"] = value
        else:
            # Unknown type — fall back to text.
            payload["ValueType"] = "Text"
            payload["StringValue"] = value
        return payload

    async def create_asset(
        self,
        name: str,
        value: str,
        asset_type: str = "Text",
    ) -> Asset:
        """Create an Orchestrator asset with the correct typed body."""
        payload = self._build_asset_payload(name, value, asset_type)
        await self._request("POST", "Assets", json=payload)
        logger.info("Created asset %s (%s)", name, asset_type)
        return Asset(name=name, value=value, asset_type=asset_type)

    # ----- Job / Process operations -----

    async def _discover_unattended_robot_ids(self) -> list[int]:
        """Return the ids of any Unattended robots visible in the tenant.

        Used by ``invoke_process`` to fall back to ``Strategy: "Specific"``
        when the modern/classic count-based strategies fail because the
        current folder has no machine template assigned to it.
        """
        try:
            data = await self._request("GET", "Robots")
        except Exception as exc:  # noqa: BLE001
            logger.debug("Could not list robots: %s", exc)
            return []
        ids: list[int] = []
        for rob in data.get("value", []):
            if rob.get("Type") in ("Unattended", "NonProduction", "Development"):
                try:
                    ids.append(int(rob["Id"]))
                except (KeyError, TypeError, ValueError):
                    pass
        return ids

    async def invoke_process(
        self,
        process_key: str,
        input_arguments: dict[str, Any] | None = None,
    ) -> str:
        """Start a UiPath process (job) by release key.

        Tries ``ModernJobsCount`` first, then ``JobsCount``, then falls
        back to ``Strategy: "Specific"`` with auto-discovered Unattended
        robot IDs. The explicit RobotIds path is necessary on UiPath
        Community Cloud when the free unattended robot isn't assigned
        to the target folder's machine pool.

        Returns:
            The job ID of the first created job.
        """
        base_start_info: dict[str, Any] = {
            "ReleaseKey": process_key,
            "InputArguments": (
                json.dumps(input_arguments) if input_arguments else "{}"
            ),
        }
        strategies: list[tuple[str, dict[str, Any]]] = [
            (
                "ModernJobsCount",
                {"startInfo": {**base_start_info, "Strategy": "ModernJobsCount", "JobsCount": 1}},
            ),
            (
                "JobsCount",
                {"startInfo": {**base_start_info, "Strategy": "JobsCount", "JobsCount": 1}},
            ),
        ]
        # Discover robots for the "Specific" fallback.
        robot_ids = await self._discover_unattended_robot_ids()
        if robot_ids:
            strategies.append(
                (
                    "Specific",
                    {
                        "startInfo": {
                            **base_start_info,
                            "Strategy": "Specific",
                            "RobotIds": robot_ids,
                        }
                    },
                )
            )

        last_exc: Exception | None = None
        for name, payload in strategies:
            try:
                data = await self._request(
                    "POST",
                    "Jobs/UiPath.Server.Configuration.OData.StartJobs",
                    json=payload,
                )
                jobs = data.get("value", [])
                if not jobs:
                    raise RuntimeError(
                        f"StartJobs returned 0 jobs (strategy={name})"
                    )
                job_id = str(jobs[0].get("Id", jobs[0].get("Key", "")))
                logger.info(
                    "Invoked process %s -> job %s (strategy=%s)",
                    process_key,
                    job_id,
                    name,
                )
                return job_id
            except Exception as exc:  # noqa: BLE001
                last_exc = exc
                logger.debug("StartJobs strategy %s failed: %s", name, exc)
                continue
        raise RuntimeError(
            f"All StartJobs strategies failed for release '{process_key}'. "
            f"Last error: {last_exc}"
        ) from last_exc

    async def get_job_status(self, job_id: str) -> JobStatus:
        """Get the status of a UiPath job."""
        data = await self._request("GET", f"Jobs({job_id})")
        return JobStatus(
            job_id=job_id,
            state=str(data.get("State", "Unknown")),
            info=str(data.get("Info", "")),
        )

    async def list_processes(self, max_pages: int = 10) -> list[dict[str, str]]:
        """List available processes (releases) in the current folder.

        Follows OData ``@odata.nextLink`` for paginated results.
        """
        results: list[dict[str, str]] = []
        path = "Releases"

        for _ in range(max_pages):
            data = await self._request("GET", path)
            for p in data.get("value", []):
                results.append({
                    "key": str(p.get("Key", "")),
                    "name": str(p.get("Name", "")),
                })
            next_link = data.get("@odata.nextLink")
            if not next_link:
                break
            # nextLink is an absolute URL — extract the path portion
            if next_link.startswith("http"):
                base = self._base_url_sync()
                path = next_link.removeprefix(base).lstrip("/")
            else:
                path = next_link

        return results

    # ----- Release operations -----

    async def update_release_to_specific_version(
        self,
        release_id: int | str,
        package_version: str,
    ) -> dict[str, Any]:
        """Point an existing release at a specific package version."""
        data = await self._request(
            "POST",
            f"Releases({release_id})/"
            "UiPath.Server.Configuration.OData.UpdateToSpecificPackageVersion",
            json={"packageVersion": package_version},
        )
        logger.info(
            "updated release %s to version %s", release_id, package_version
        )
        return data

    async def create_release(
        self,
        package_id: str,
        process_name: str,
        environment_id: str | None = None,
        process_version: str = "1.0.0",
        idempotent: bool = True,
    ) -> dict[str, Any]:
        """Create a release (process) in Orchestrator from a published package.

        UiPath 2025.10 requires ``ProcessVersion`` on Releases POST.
        When ``idempotent=True`` (default), a 409 Conflict (release name
        already exists) triggers a GET to return the existing record
        instead of raising.

        Returns:
            The created or existing release record with Key, ProcessKey, etc.
        """
        payload: dict[str, Any] = {
            "Name": process_name,
            "ProcessKey": process_name,
            "ProcessVersion": process_version,
            "Description": "Deployed by RPA Architect lifecycle agent",
        }
        if environment_id:
            payload["EnvironmentId"] = environment_id

        try:
            data = await self._request("POST", "Releases", json=payload)
            logger.info(
                "Created release for %s (key=%s)",
                process_name,
                data.get("Key", ""),
            )
            return data
        except httpx.HTTPStatusError as exc:
            if not idempotent or exc.response.status_code != 409:
                raise
        # 409 — look up the existing release by name and return it.
        existing = await self._request(
            "GET",
            f"Releases?$filter=Name eq '{process_name}'",
        )
        items = existing.get("value", [])
        if not items:
            raise RuntimeError(
                f"Release '{process_name}' returned 409 on create but was "
                "not found on subsequent lookup"
            )
        release = items[0]
        logger.info(
            "Reusing existing release %s (key=%s)",
            process_name,
            release.get("Key", ""),
        )
        return release

    # ----- Job listing & logs -----

    async def list_jobs(
        self,
        process_key: str,
        since: Any | None = None,
        states: list[str] | None = None,
    ) -> list[dict[str, Any]]:
        """List jobs for a process, optionally filtered by time and state.

        Args:
            process_key: Release key to filter by.
            since: Only return jobs started after this datetime.
            states: Filter to these job states (e.g. ["Successful", "Faulted"]).

        Returns:
            List of job OData records.
        """
        filters = [f"ReleaseName eq '{process_key}' or ReleaseKey eq '{process_key}'"]
        if since is not None:
            ts = since.strftime("%Y-%m-%dT%H:%M:%SZ")
            filters.append(f"StartTime ge {ts}")
        if states:
            state_filter = " or ".join(f"State eq '{s}'" for s in states)
            filters.append(f"({state_filter})")

        filter_str = " and ".join(filters)
        path = f"Jobs?$filter={filter_str}&$orderby=StartTime desc&$top=100"

        data = await self._request("GET", path)
        return data.get("value", [])

    async def get_robot_logs(self, job_id: str) -> list[dict[str, Any]]:
        """Fetch robot execution logs for a specific job.

        Returns:
            List of RobotLog OData records.
        """
        path = f"RobotLogs?$filter=JobKey eq '{job_id}'&$orderby=TimeStamp desc&$top=50"
        data = await self._request("GET", path)
        return data.get("value", [])

    # ----- Bucket operations -----

    async def upload_to_bucket(
        self,
        bucket_name: str,
        file_path: str,
        blob_name: str | None = None,
    ) -> str:
        """Upload a file to an Orchestrator storage bucket.

        Returns:
            The blob storage path.
        """
        # Look up bucket ID
        bucket_data = await self._request(
            "GET",
            f"Buckets?$filter=Name eq '{bucket_name}'",
        )
        buckets = bucket_data.get("value", [])
        if not buckets:
            raise LookupError(f"Bucket '{bucket_name}' not found")
        bucket_id = buckets[0]["Id"]

        blob = blob_name or file_path.rsplit("/", 1)[-1]

        http = await self._get_http()
        headers = await self._headers()
        del headers["Content-Type"]  # let httpx set multipart boundary
        url = (
            f"{self._base_url_sync()}/Buckets({bucket_id})"
            f"/UiPath.Server.Configuration.OData.UploadFile"
        )

        with open(file_path, "rb") as f:
            resp = await http.post(
                url,
                headers=headers,
                files={"file": (blob, f)},
            )
        resp.raise_for_status()
        logger.info("Uploaded %s to bucket %s", file_path, bucket_name)
        return f"{bucket_name}/{blob}"

    # ----- Package upload (NuGet feed) -----

    async def upload_package(
        self,
        nupkg_path: Any,
        *,
        idempotent: bool = True,
    ) -> dict[str, Any]:
        """Upload a .nupkg to the Orchestrator NuGet feed.

        Calls ``Processes/UiPath.Server.Configuration.OData.UploadPackage``
        with a multipart form containing the .nupkg bytes. Returns the
        decoded JSON response which includes the resulting process key.

        When ``idempotent=True`` (default), a 409 Conflict (package already
        exists) is not treated as an error — the existing package can be
        used directly. Set ``idempotent=False`` for strict CI pipelines
        that always want a fresh version.
        """
        from pathlib import Path

        path = Path(nupkg_path)
        if not path.exists():
            raise FileNotFoundError(f".nupkg not found: {path}")

        http = await self._get_http()
        headers = await self._headers()
        # Multipart upload — let httpx set the Content-Type boundary.
        headers.pop("Content-Type", None)

        url = (
            f"{self._base_url_sync()}/Processes/"
            "UiPath.Server.Configuration.OData.UploadPackage"
        )

        with open(path, "rb") as f:
            resp = await http.post(
                url,
                headers=headers,
                files={"file": (path.name, f, "application/octet-stream")},
            )
        if resp.status_code == 409 and idempotent:
            logger.info(
                "Package %s already exists in Orchestrator (409) — "
                "continuing idempotently", path.name
            )
            return {"already_exists": True, "filename": path.name}
        resp.raise_for_status()
        try:
            data = resp.json()
        except ValueError:
            data = {"raw": resp.text}
        logger.info("Uploaded package %s to Orchestrator feed", path.name)
        return data

    # ----- Idempotent ensure helpers -----

    async def ensure_queue(self, name: str, description: str = "") -> str:
        """Return the queue id, creating the queue if it doesn't already exist."""
        try:
            existing = await self._request(
                "GET", f"QueueDefinitions?$filter=Name eq '{name}'"
            )
            items = existing.get("value", [])
            if items:
                qid = str(items[0].get("Id", ""))
                logger.info("ensure_queue: %s already exists (id=%s)", name, qid)
                return qid
        except httpx.HTTPStatusError:
            # Fall through to create.
            pass
        return await self.create_queue(name, description)

    async def ensure_asset(
        self,
        name: str,
        value: str,
        asset_type: str = "Text",
    ) -> Asset:
        """Create an asset, or update its value if it already exists.

        Tries create-first and falls back to GET+PUT on 409 Conflict.
        This avoids an OData filter round-trip that in 2025.10 Cloud
        sometimes returns an empty list for assets that exist (folder
        scoping differences between API and UI).
        """
        try:
            return await self.create_asset(name, value, asset_type)
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code != 409:
                raise
        # Exists — look it up by name and PUT the new value.
        existing = await self._request(
            "GET", f"Assets?$filter=Name eq '{name}'"
        )
        items = existing.get("value", [])
        if not items:
            # The UI filter may return nothing even though the asset exists —
            # probably a scoping issue. Treat the 409 as success and move on.
            logger.info(
                "ensure_asset: %s already exists (could not re-fetch); "
                "skipping update",
                name,
            )
            return Asset(name=name, value=value, asset_type=asset_type)
        asset_id = items[0].get("Id")
        try:
            await self._request(
                "PUT",
                f"Assets({asset_id})",
                json=self._build_asset_payload(name, value, asset_type),
            )
            logger.info("ensure_asset: updated %s (id=%s)", name, asset_id)
        except httpx.HTTPStatusError as exc:
            # 404 here means the asset is scoped to a different folder than
            # the one in X-UIPATH-OrganizationUnitId. Treat as success:
            # the asset already exists, we just can't reach it to update it
            # through this folder. The caller will still see the desired
            # Asset record as the return value.
            if exc.response.status_code == 404:
                logger.warning(
                    "ensure_asset: %s (id=%s) exists in a different folder "
                    "scope; skipping update. Value in that scope is "
                    "unchanged — rotate manually via the UI if needed.",
                    name,
                    asset_id,
                )
            else:
                raise
        return Asset(name=name, value=value, asset_type=asset_type)

    # ----- Folder operations -----

    async def create_folder(self, name: str, **kwargs: Any) -> str:
        """Create an Orchestrator folder.

        Returns:
            The folder ID.
        """
        data = await self._request(
            "POST",
            "Folders",
            json={"DisplayName": name, "ProvisionType": "Manual", **kwargs},
        )
        folder_id = str(data.get("Id", ""))
        logger.info("Created folder %s (id=%s)", name, folder_id)
        return folder_id

    async def get_folder(self, name: str, **kwargs: Any) -> dict[str, Any]:
        """Retrieve an Orchestrator folder by display name.

        Raises:
            LookupError: If the folder is not found.
        """
        data = await self._request(
            "GET",
            f"Folders?$filter=DisplayName eq '{name}'",
        )
        items = data.get("value", [])
        if not items:
            raise LookupError(f"Folder '{name}' not found")
        return items[0]

    async def close(self) -> None:
        """Close the underlying HTTP client."""
        if self._http is not None:
            await self._http.aclose()
            self._http = None
