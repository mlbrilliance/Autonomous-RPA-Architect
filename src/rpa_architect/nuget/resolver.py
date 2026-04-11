"""Real-time NuGet package version resolution against UiPath feeds."""
from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from urllib.request import urlopen, Request
from urllib.error import URLError

logger = logging.getLogger(__name__)

# UiPath NuGet v3 feed endpoints
UIPATH_NUGET_INDEX = "https://pkgs.dev.azure.com/uipath/Public.Feeds/_packaging/UiPath-Official/nuget/v3/index.json"
NUGET_ORG_V3 = "https://api.nuget.org/v3/index.json"

@dataclass
class NuGetPackageInfo:
    """Resolved NuGet package information."""
    package_id: str
    version: str
    source: str = "uipath-official"
    resolved_at: float = field(default_factory=time.time)
    is_fallback: bool = False

# In-memory cache: package_id -> NuGetPackageInfo
_CACHE: dict[str, NuGetPackageInfo] = {}
_CACHE_TTL = 3600  # 1 hour

def _fetch_json(url: str, timeout: int = 10) -> dict | list | None:
    """Fetch JSON from a URL with timeout."""
    try:
        req = Request(url, headers={"Accept": "application/json", "User-Agent": "rpa-architect/1.0"})
        with urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except (URLError, json.JSONDecodeError, OSError) as e:
        logger.debug("Failed to fetch %s: %s", url, e)
        return None

def _get_service_url(index_url: str, service_type: str) -> str | None:
    """Get a service URL from a NuGet v3 index."""
    data = _fetch_json(index_url)
    if not data or "resources" not in data:
        return None
    for resource in data["resources"]:
        rtype = resource.get("@type", "")
        if service_type in rtype:
            return resource.get("@id")
    return None

def _resolve_from_feed(package_id: str, index_url: str, source_name: str,
                        prerelease: bool = False) -> NuGetPackageInfo | None:
    """Resolve latest version of a package from a NuGet v3 feed."""
    # Try SearchQueryService first
    search_url = _get_service_url(index_url, "SearchQueryService")
    if search_url:
        query_url = f"{search_url}?q={package_id}&take=1&prerelease={str(prerelease).lower()}"
        data = _fetch_json(query_url)
        if data and "data" in data:
            for item in data["data"]:
                if item.get("id", "").lower() == package_id.lower():
                    version = item.get("version", "")
                    if version:
                        return NuGetPackageInfo(
                            package_id=item["id"],
                            version=version,
                            source=source_name,
                        )

    # Fallback: try PackageBaseAddress (flat container)
    base_url = _get_service_url(index_url, "PackageBaseAddress")
    if base_url:
        versions_url = f"{base_url}{package_id.lower()}/index.json"
        data = _fetch_json(versions_url)
        if data and "versions" in data:
            versions = data["versions"]
            if not prerelease:
                versions = [v for v in versions if "-" not in v]
            if versions:
                return NuGetPackageInfo(
                    package_id=package_id,
                    version=versions[-1],  # Latest
                    source=source_name,
                )

    return None

def resolve_package(package_id: str, prerelease: bool = False,
                     use_cache: bool = True) -> NuGetPackageInfo:
    """Resolve the latest version of a NuGet package.

    Tries UiPath Official feed first, then nuget.org, then falls back
    to known_packages defaults.
    """
    # Check cache
    if use_cache and package_id in _CACHE:
        cached = _CACHE[package_id]
        if time.time() - cached.resolved_at < _CACHE_TTL:
            return cached

    # Try UiPath Official feed
    result = _resolve_from_feed(package_id, UIPATH_NUGET_INDEX, "uipath-official", prerelease)

    # Try nuget.org
    if not result:
        result = _resolve_from_feed(package_id, NUGET_ORG_V3, "nuget.org", prerelease)

    # Fallback to known defaults
    if not result:
        from rpa_architect.nuget.known_packages import DEFAULT_VERSIONS
        default_version = DEFAULT_VERSIONS.get(package_id)
        if default_version:
            result = NuGetPackageInfo(
                package_id=package_id,
                version=default_version,
                source="fallback",
                is_fallback=True,
            )
            logger.warning("Using fallback version for %s: %s", package_id, default_version)
        else:
            logger.error("Cannot resolve package: %s", package_id)
            result = NuGetPackageInfo(
                package_id=package_id,
                version="0.0.0",
                source="unknown",
                is_fallback=True,
            )

    # Cache result
    if use_cache:
        _CACHE[package_id] = result

    return result

def resolve_all_packages(package_ids: list[str], prerelease: bool = False) -> dict[str, NuGetPackageInfo]:
    """Resolve multiple packages."""
    return {pid: resolve_package(pid, prerelease) for pid in package_ids}

def clear_cache() -> None:
    """Clear the version resolution cache."""
    _CACHE.clear()

def resolve_project_dependencies(activities_used: list[str]) -> dict[str, str]:
    """Given a list of activity names, resolve all required NuGet packages and versions.

    Returns dict of package_id -> version suitable for project.json.
    """
    from rpa_architect.nuget.known_packages import get_package_for_activity

    packages_needed: set[str] = set()
    for activity in activities_used:
        pkg = get_package_for_activity(activity)
        if pkg:
            packages_needed.add(pkg)

    resolved = resolve_all_packages(list(packages_needed))
    return {pid: info.version for pid, info in resolved.items()}
