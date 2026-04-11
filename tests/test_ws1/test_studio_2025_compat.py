"""Tests for WS1: Studio 2025.10 Compatibility.

Validates NuGet version updates, UIAutomation rename, project.json schema,
WaitScreenReady generator, and XL-BP009 deprecation lint rule.
"""
from __future__ import annotations

import json
import xml.etree.ElementTree as ET

import pytest

from rpa_architect.generators import generate_activity, get_generator, list_generators
from rpa_architect.generators.base import reset_counter
from rpa_architect.nuget.known_packages import (
    ACTIVITY_PACKAGE_MAP,
    DEFAULT_VERSIONS,
    STANDARD_PACKAGES,
    _PACKAGE_ALIASES,
    get_default_version,
    get_package_for_activity,
    get_required_packages,
    resolve_package_alias,
)
from rpa_architect.xaml_lint import lint_xaml, LintSeverity


@pytest.fixture(autouse=True)
def _reset_counter():
    reset_counter(1)
    yield
    reset_counter(1)


# ===================================================================
# NuGet 25.10 Version Updates
# ===================================================================

class TestNuGet2510Versions:

    def test_system_activities_version_is_25_10(self):
        assert DEFAULT_VERSIONS["UiPath.System.Activities"] == "25.10.0"

    def test_ui_automation_version_is_25_10(self):
        assert DEFAULT_VERSIONS["UiPath.UIAutomation.Activities"] == "25.10.16"

    def test_excel_activities_version_is_3_x(self):
        version = DEFAULT_VERSIONS["UiPath.Excel.Activities"]
        assert version.startswith("3."), f"Expected 3.x, got {version}"

    def test_mail_activities_version_is_2_x(self):
        version = DEFAULT_VERSIONS["UiPath.Mail.Activities"]
        assert version.startswith("2."), f"Expected 2.x, got {version}"

    def test_webapi_activities_version_is_2_x(self):
        version = DEFAULT_VERSIONS["UiPath.WebAPI.Activities"]
        assert version.startswith("2."), f"Expected 2.x, got {version}"

    def test_testing_activities_version_is_25_10(self):
        assert DEFAULT_VERSIONS["UiPath.Testing.Activities"] == "25.10.0"

    def test_form_activities_version_is_25_10(self):
        assert DEFAULT_VERSIONS["UiPath.Form.Activities"] == "25.10.0"

    def test_all_versions_are_valid_semver(self):
        for pkg, version in DEFAULT_VERSIONS.items():
            parts = version.split(".")
            assert len(parts) >= 2, f"{pkg}: '{version}' is not valid semver"
            # First part should be numeric
            assert parts[0].isdigit(), f"{pkg}: '{version}' first part not numeric"


# ===================================================================
# UIAutomationNext → UIAutomation Rename
# ===================================================================

class TestUIAutomationRename:

    def test_nclick_maps_to_uiautomation(self):
        assert get_package_for_activity("NClick") == "UiPath.UIAutomation.Activities"

    def test_ntypeinto_maps_to_uiautomation(self):
        assert get_package_for_activity("NTypeInto") == "UiPath.UIAutomation.Activities"

    def test_all_n_activities_use_uiautomation(self):
        n_activities = [k for k in ACTIVITY_PACKAGE_MAP if k.startswith("N")]
        for activity in n_activities:
            pkg = ACTIVITY_PACKAGE_MAP[activity]
            assert pkg == "UiPath.UIAutomation.Activities", (
                f"{activity} still maps to {pkg}"
            )

    def test_standard_packages_use_uiautomation(self):
        assert "UiPath.UIAutomation.Activities" in STANDARD_PACKAGES
        assert "UiPath.UIAutomationNext.Activities" not in STANDARD_PACKAGES

    def test_alias_resolves_next_to_current(self):
        resolved = resolve_package_alias("UiPath.UIAutomationNext.Activities")
        assert resolved == "UiPath.UIAutomation.Activities"

    def test_alias_passthrough_for_unknown(self):
        assert resolve_package_alias("UiPath.System.Activities") == "UiPath.System.Activities"

    def test_get_default_version_resolves_alias(self):
        version = get_default_version("UiPath.UIAutomationNext.Activities")
        assert version == DEFAULT_VERSIONS["UiPath.UIAutomation.Activities"]

    def test_no_uiautomationnext_in_default_versions(self):
        assert "UiPath.UIAutomationNext.Activities" not in DEFAULT_VERSIONS

    def test_wait_screen_ready_maps_to_uiautomation(self):
        assert get_package_for_activity("WaitScreenReady") == "UiPath.UIAutomation.Activities"


# ===================================================================
# project.json Schema Updates
# ===================================================================

class TestProjectJsonSchema:

    def test_project_json_has_tool_version_25_10(self):
        from rpa_architect.assembler.project_json_gen import _PROJECT_JSON_TEMPLATE
        assert _PROJECT_JSON_TEMPLATE["toolVersion"] == "25.10.0"

    def test_project_json_has_studio_version_25_10(self):
        from rpa_architect.assembler.project_json_gen import _PROJECT_JSON_TEMPLATE
        assert _PROJECT_JSON_TEMPLATE["studioVersion"] == "25.10.0.0"

    def test_project_json_has_target_framework(self):
        from rpa_architect.assembler.project_json_gen import _PROJECT_JSON_TEMPLATE
        assert _PROJECT_JSON_TEMPLATE["targetFramework"] == "Portable"

    def test_project_json_has_main_field(self):
        """Legacy `main` field is required — without it, the UiPath robot
        runtime throws `ArgumentNullException: Value cannot be null
        (Parameter 'path2')` inside RobotRunner.InitWorkflowApplication.
        Verified live against cloud.uipath.com in the Odoo build.
        """
        from rpa_architect.assembler.project_json_gen import _PROJECT_JSON_TEMPLATE
        assert "main" in _PROJECT_JSON_TEMPLATE
        assert _PROJECT_JSON_TEMPLATE["main"] == "Main.xaml"

    def test_project_json_runtime_has_net_version(self):
        from rpa_architect.assembler.project_json_gen import _PROJECT_JSON_TEMPLATE
        assert _PROJECT_JSON_TEMPLATE["runtimeOptions"]["netVersion"] == "net6.0"

    def test_default_dependencies_use_25_10_versions(self):
        from rpa_architect.assembler.project_json_gen import _DEFAULT_DEPENDENCIES
        for pkg, version_range in _DEFAULT_DEPENDENCIES.items():
            assert "25." in version_range or "2." in version_range or "3." in version_range, (
                f"{pkg} dependency '{version_range}' doesn't use 25.10 era version"
            )

    def test_default_dependencies_no_uiautomation_in_portable_mode(self):
        # Pivoted to Cross-Platform / Portable: UI Automation is REMOVED
        # from defaults because Portable runtime can't load it. The
        # CodedWorkflow handles all logic via HttpClient.
        from rpa_architect.assembler.project_json_gen import _DEFAULT_DEPENDENCIES
        assert "UiPath.UIAutomation.Activities" not in _DEFAULT_DEPENDENCIES
        assert "UiPath.System.Activities" in _DEFAULT_DEPENDENCIES
        assert "UiPath.WebAPI.Activities" in _DEFAULT_DEPENDENCIES

    def test_project_profile_uses_numeric_enum(self):
        # Studio 25.10 ProjectProfile is now a numeric enum (0=Development,
        # 1=Production). String "Development" is rejected by the
        # WorkflowCompiler — verified live in Phase E.
        from rpa_architect.assembler.project_json_gen import _PROJECT_JSON_TEMPLATE
        assert _PROJECT_JSON_TEMPLATE["designOptions"]["projectProfile"] == 0

    def test_xaml_namespaces_use_mscorlib(self):
        from rpa_architect.generators.base import _XAML_NAMESPACES
        scg = _XAML_NAMESPACES["xmlns:scg"]
        sco = _XAML_NAMESPACES["xmlns:sco"]
        assert "mscorlib" in scg, f"scg uses wrong assembly: {scg}"
        assert "mscorlib" in sco, f"sco uses wrong assembly: {sco}"

    def test_wiring_namespace_uses_mscorlib(self):
        from rpa_architect.wiring.wiring_engine import _NS
        assert "mscorlib" in _NS["scg"]

    def test_variable_injector_namespace_uses_mscorlib(self):
        from rpa_architect.wiring.variable_injector import _NS
        assert "mscorlib" in _NS["scg"]


# ===================================================================
# WaitScreenReady Generator
# ===================================================================

class TestWaitScreenReadyGenerator:

    def test_generator_registered(self):
        info = get_generator("wait_screen_ready")
        assert info is not None
        assert info.name == "wait_screen_ready"
        assert info.category == "UI Automation"

    def test_generates_xml(self):
        xml = generate_activity("wait_screen_ready")
        assert "WaitScreenReady" in xml
        assert "ui:WaitScreenReady" in xml

    def test_default_timeout(self):
        xml = generate_activity("wait_screen_ready")
        assert 'TimeoutMS="30000"' in xml

    def test_custom_timeout(self):
        xml = generate_activity("wait_screen_ready", timeout_ms=60000)
        assert 'TimeoutMS="60000"' in xml

    def test_custom_display_name(self):
        xml = generate_activity("wait_screen_ready", display_name="Wait for Login Screen")
        assert 'DisplayName="Wait for Login Screen"' in xml

    def test_self_closing_tag(self):
        xml = generate_activity("wait_screen_ready")
        assert xml.strip().endswith("/>")

    def test_has_viewstate_ref(self):
        xml = generate_activity("wait_screen_ready")
        assert "sap2010:WorkflowViewState.IdRef" in xml
        assert "WaitScreenReady_" in xml

    def test_generator_count_increased(self):
        gens = list_generators()
        assert len(gens) >= 80  # Was 79 in v0.2.0, +1 for wait_screen_ready (+ coded API gens)


# ===================================================================
# XL-BP009: Deprecated Classic Activities Lint Rule
# ===================================================================

class TestDeprecatedClassicActivitiesLint:

    def _make_xaml(self, body: str) -> str:
        return (
            '<?xml version="1.0" encoding="utf-8"?>\n'
            '<Activity xmlns="http://schemas.microsoft.com/netfx/2009/xaml/activities"'
            ' xmlns:ui="http://schemas.uipath.com/workflow/activities"'
            ' xmlns:x="http://schemas.microsoft.com/winfx/2006/xaml"'
            ' xmlns:sap2010="http://schemas.microsoft.com/netfx/2010/xaml/activities/presentation">\n'
            '  <Sequence DisplayName="Main">\n'
            f'    {body}\n'
            '  </Sequence>\n'
            '</Activity>'
        )

    def test_detects_classic_click(self):
        xaml = self._make_xaml('<Click DisplayName="Click Submit" />')
        issues = lint_xaml(xaml)
        bp009 = [i for i in issues if i.rule_id == "XL-BP009"]
        assert len(bp009) >= 1
        assert "NClick" in bp009[0].suggestion

    def test_detects_classic_type_into(self):
        xaml = self._make_xaml('<TypeInto DisplayName="Type Username" />')
        issues = lint_xaml(xaml)
        bp009 = [i for i in issues if i.rule_id == "XL-BP009"]
        assert len(bp009) >= 1
        assert "NTypeInto" in bp009[0].suggestion

    def test_detects_classic_get_text(self):
        xaml = self._make_xaml('<GetText DisplayName="Get Value" />')
        issues = lint_xaml(xaml)
        bp009 = [i for i in issues if i.rule_id == "XL-BP009"]
        assert len(bp009) >= 1

    def test_detects_classic_send_hotkey(self):
        xaml = self._make_xaml('<SendHotkey Key="Enter" />')
        issues = lint_xaml(xaml)
        bp009 = [i for i in issues if i.rule_id == "XL-BP009"]
        assert len(bp009) >= 1
        assert "NKeyboardShortcuts" in bp009[0].suggestion

    def test_ignores_modern_nclick(self):
        xaml = self._make_xaml('<ui:NClick DisplayName="Click Submit" />')
        issues = lint_xaml(xaml)
        bp009 = [i for i in issues if i.rule_id == "XL-BP009"]
        assert len(bp009) == 0

    def test_severity_is_warning(self):
        xaml = self._make_xaml('<Click />')
        issues = lint_xaml(xaml)
        bp009 = [i for i in issues if i.rule_id == "XL-BP009"]
        assert bp009[0].severity == LintSeverity.WARNING

    def test_no_duplicate_for_same_classic_type(self):
        xaml = self._make_xaml(
            '<Click DisplayName="Click A" />\n'
            '    <Click DisplayName="Click B" />'
        )
        issues = lint_xaml(xaml)
        bp009 = [i for i in issues if i.rule_id == "XL-BP009"]
        # Should only report once per classic activity type
        assert len(bp009) == 1

    def test_clean_modern_workflow_no_bp009(self):
        xaml = self._make_xaml(
            '<ui:NClick DisplayName="Click" />\n'
            '    <ui:NTypeInto Text="hello" />\n'
            '    <ui:LogMessage Message="Done" />'
        )
        issues = lint_xaml(xaml)
        bp009 = [i for i in issues if i.rule_id == "XL-BP009"]
        assert len(bp009) == 0

    def test_lint_engine_has_21_rules(self):
        """The default engine should now have 21 rules (20 original + BP009)."""
        from rpa_architect.xaml_lint.engine import create_default_engine
        engine = create_default_engine()
        assert engine.rule_count == 21
