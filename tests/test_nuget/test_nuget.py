"""Tests for NuGet resolution."""
from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import pytest

from rpa_architect.nuget.known_packages import (
    ACTIVITY_PACKAGE_MAP,
    DEFAULT_VERSIONS,
    get_default_version,
    get_package_for_activity,
    get_required_packages,
)
from rpa_architect.nuget.resolver import (
    NuGetPackageInfo,
    clear_cache,
    resolve_package,
    resolve_project_dependencies,
    _CACHE,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def _clear_resolver_cache():
    """Clear the NuGet cache before and after each test."""
    clear_cache()
    yield
    clear_cache()


# ===================================================================
# get_package_for_activity()
# ===================================================================

class TestGetPackageForActivity:

    def test_nclick_returns_ui_automation(self):
        result = get_package_for_activity("NClick")
        assert result == "UiPath.UIAutomation.Activities"

    def test_assign_returns_system_activities(self):
        result = get_package_for_activity("Assign")
        assert result == "UiPath.System.Activities"

    def test_unknown_returns_none(self):
        result = get_package_for_activity("CompletelyUnknownActivity123")
        assert result is None

    def test_log_message(self):
        result = get_package_for_activity("LogMessage")
        assert result == "UiPath.System.Activities"

    def test_read_range(self):
        result = get_package_for_activity("ReadRange")
        assert result == "UiPath.Excel.Activities"

    def test_http_client(self):
        result = get_package_for_activity("HttpClient")
        assert result == "UiPath.WebAPI.Activities"

    def test_case_sensitive(self):
        """Activity names are case-sensitive; 'nclick' should not match 'NClick'."""
        result = get_package_for_activity("nclick")
        assert result is None


# ===================================================================
# get_required_packages()
# ===================================================================

class TestGetRequiredPackages:

    def test_single_known_activity(self):
        packages = get_required_packages(["NClick"])
        assert "UiPath.UIAutomation.Activities" in packages
        # Standard packages are always included
        assert "UiPath.System.Activities" in packages

    def test_multiple_activities(self):
        packages = get_required_packages(["NClick", "Assign", "ReadRange"])
        assert "UiPath.UIAutomation.Activities" in packages
        assert "UiPath.System.Activities" in packages
        assert "UiPath.Excel.Activities" in packages

    def test_unknown_activities_ignored(self):
        packages = get_required_packages(["FakeActivity"])
        # Should still have standard packages
        assert "UiPath.System.Activities" in packages
        assert "UiPath.UIAutomation.Activities" in packages

    def test_empty_list(self):
        packages = get_required_packages([])
        # Should still have standard packages
        assert "UiPath.System.Activities" in packages
        assert "UiPath.UIAutomation.Activities" in packages

    def test_returns_set(self):
        packages = get_required_packages(["Assign", "If", "While"])
        assert isinstance(packages, set)

    def test_deduplication(self):
        """Multiple activities from the same package should only appear once."""
        packages = get_required_packages(["Assign", "If", "While", "Sequence", "ForEach"])
        # All these are in UiPath.System.Activities, count should be 1
        system_count = sum(1 for p in packages if p == "UiPath.System.Activities")
        assert system_count == 1


# ===================================================================
# get_default_version()
# ===================================================================

class TestGetDefaultVersion:

    def test_known_package(self):
        version = get_default_version("UiPath.System.Activities")
        assert isinstance(version, str)
        assert version  # Non-empty
        # Should match the version in DEFAULT_VERSIONS
        assert version == DEFAULT_VERSIONS["UiPath.System.Activities"]

    def test_unknown_package_returns_1_0_0(self):
        version = get_default_version("Some.Unknown.Package")
        assert version == "1.0.0"

    def test_version_format(self):
        """Versions should be in semver-like format."""
        for pkg_id, version in DEFAULT_VERSIONS.items():
            parts = version.split(".")
            assert len(parts) >= 2, f"{pkg_id} version '{version}' doesn't look like semver"


# ===================================================================
# resolve_package() -- with mocked network
# ===================================================================

class TestResolvePackage:

    @patch("rpa_architect.nuget.resolver._resolve_from_feed", return_value=None)
    def test_fallback_when_network_unavailable(self, mock_resolve):
        """When network is unavailable, should fall back to known defaults."""
        result = resolve_package("UiPath.System.Activities", use_cache=False)
        assert isinstance(result, NuGetPackageInfo)
        assert result.package_id == "UiPath.System.Activities"
        assert result.is_fallback is True
        assert result.version == DEFAULT_VERSIONS["UiPath.System.Activities"]

    @patch("rpa_architect.nuget.resolver._resolve_from_feed", return_value=None)
    def test_unknown_package_fallback_returns_0_0_0(self, mock_resolve):
        """Unknown package with no network should return 0.0.0."""
        result = resolve_package("Totally.Unknown.Package", use_cache=False)
        assert result.version == "0.0.0"
        assert result.is_fallback is True
        assert result.source == "unknown"

    @patch("rpa_architect.nuget.resolver._resolve_from_feed")
    def test_successful_resolution_from_feed(self, mock_resolve):
        mock_resolve.return_value = NuGetPackageInfo(
            package_id="UiPath.System.Activities",
            version="99.0.1",
            source="uipath-official",
        )
        result = resolve_package("UiPath.System.Activities", use_cache=False)
        assert result.version == "99.0.1"
        assert result.is_fallback is False

    @patch("rpa_architect.nuget.resolver._resolve_from_feed", return_value=None)
    def test_caching(self, mock_resolve):
        """Repeated calls should use cached result."""
        r1 = resolve_package("UiPath.System.Activities", use_cache=True)
        first_call_count = mock_resolve.call_count
        assert first_call_count >= 1  # At least one call to resolve

        r2 = resolve_package("UiPath.System.Activities", use_cache=True)
        # The second call should use cache -- no additional calls to _resolve_from_feed
        assert mock_resolve.call_count == first_call_count
        assert r1.version == r2.version

    @patch("rpa_architect.nuget.resolver._resolve_from_feed")
    def test_uipath_feed_tried_first(self, mock_resolve):
        """The UiPath official feed should be tried before nuget.org."""
        # Return a result on first call (uipath feed)
        mock_resolve.side_effect = [
            NuGetPackageInfo(
                package_id="UiPath.System.Activities",
                version="24.10.7",
                source="uipath-official",
            ),
        ]
        result = resolve_package("UiPath.System.Activities", use_cache=False)
        assert result.source == "uipath-official"
        # Only one call should be made since the first feed succeeded
        assert mock_resolve.call_count == 1


# ===================================================================
# resolve_project_dependencies()
# ===================================================================

class TestResolveProjectDependencies:

    @patch("rpa_architect.nuget.resolver._resolve_from_feed", return_value=None)
    def test_returns_correct_packages(self, mock_resolve):
        deps = resolve_project_dependencies(["NClick", "ReadRange"])
        assert "UiPath.UIAutomation.Activities" in deps
        assert "UiPath.Excel.Activities" in deps
        # Each value should be a version string
        for pkg_id, version in deps.items():
            assert isinstance(version, str)
            assert version

    @patch("rpa_architect.nuget.resolver._resolve_from_feed", return_value=None)
    def test_unknown_activities_excluded(self, mock_resolve):
        deps = resolve_project_dependencies(["FakeActivity123"])
        # Unknown activities don't map to any package, so result should be empty
        assert len(deps) == 0


# ===================================================================
# clear_cache()
# ===================================================================

class TestClearCache:

    @patch("rpa_architect.nuget.resolver._resolve_from_feed", return_value=None)
    def test_clear_cache_works(self, mock_resolve):
        resolve_package("UiPath.System.Activities", use_cache=True)
        assert len(_CACHE) > 0

        clear_cache()
        assert len(_CACHE) == 0


# ===================================================================
# NuGetPackageInfo dataclass
# ===================================================================

class TestNuGetPackageInfo:

    def test_basic_construction(self):
        info = NuGetPackageInfo(
            package_id="UiPath.System.Activities",
            version="24.10.7",
        )
        assert info.package_id == "UiPath.System.Activities"
        assert info.version == "24.10.7"
        assert info.source == "uipath-official"  # default
        assert info.is_fallback is False  # default

    def test_fallback_flag(self):
        info = NuGetPackageInfo(
            package_id="X",
            version="1.0.0",
            source="fallback",
            is_fallback=True,
        )
        assert info.is_fallback is True

    def test_resolved_at_auto_set(self):
        info = NuGetPackageInfo(package_id="X", version="1.0")
        assert info.resolved_at > 0

    def test_custom_source(self):
        info = NuGetPackageInfo(
            package_id="X",
            version="2.0",
            source="nuget.org",
        )
        assert info.source == "nuget.org"


# ===================================================================
# ACTIVITY_PACKAGE_MAP completeness
# ===================================================================

class TestActivityPackageMapCompleteness:

    def test_all_standard_activities_mapped(self):
        """Key UiPath activities should be present in the map."""
        expected = [
            "Assign", "If", "ForEach", "While", "Sequence",
            "TryCatch", "NClick", "NTypeInto", "ReadRange",
            "LogMessage", "AddQueueItem", "GetRobotCredential",
        ]
        for activity in expected:
            assert activity in ACTIVITY_PACKAGE_MAP, f"Missing: {activity}"

    def test_all_values_are_valid_package_ids(self):
        for activity, package in ACTIVITY_PACKAGE_MAP.items():
            assert package.startswith("UiPath."), (
                f"Activity '{activity}' maps to '{package}' which doesn't start with 'UiPath.'"
            )
