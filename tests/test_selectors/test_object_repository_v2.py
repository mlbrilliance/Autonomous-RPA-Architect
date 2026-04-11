"""Tests for v2 hierarchical Object Repository, variable helpers, and UI Library generation."""

from __future__ import annotations

import json

from rpa_architect.ir.schema import ProcessIR, Step, SystemInfo, Transaction, UIAction
from rpa_architect.selectors.object_repository import (
    ObjectRepositoryElementV2,
    ObjectRepositoryScreenV2,
    extract_selector_variables,
    generate_object_repository,
    generate_object_repository_v2,
    resolve_selector_variables,
)
from rpa_architect.selectors.ui_library_gen import generate_ui_library


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_ir(
    process_name: str = "TestProcess",
    systems: list[SystemInfo] | None = None,
    transactions: list[Transaction] | None = None,
) -> ProcessIR:
    return ProcessIR(
        process_name=process_name,
        systems=systems or [],
        transactions=transactions or [],
    )


def _simple_ir() -> ProcessIR:
    """IR with one web system, one transaction, one step, one action."""
    return _make_ir(
        systems=[SystemInfo(name="MyWebApp", type="web", login_required=True)],
        transactions=[
            Transaction(
                name="Login",
                steps=[
                    Step(
                        id="S001",
                        type="login_sequence",
                        system_ref="MyWebApp",
                        actions=[
                            UIAction(action="type_into", target="Username Field", confidence=0.9),
                            UIAction(action="type_into", target="Password Field", confidence=0.9),
                            UIAction(action="click", target="Login Button", confidence=0.85),
                        ],
                    ),
                ],
            )
        ],
    )


def _multi_app_ir() -> ProcessIR:
    """IR with two systems and steps referencing each."""
    return _make_ir(
        process_name="MultiAppProcess",
        systems=[
            SystemInfo(name="WebPortal", type="web"),
            SystemInfo(name="SapGui", type="sap"),
        ],
        transactions=[
            Transaction(
                name="Transfer",
                steps=[
                    Step(id="S001", type="ui_flow", system_ref="WebPortal", actions=[]),
                    Step(id="S002", type="ui_flow", system_ref="SapGui", actions=[]),
                ],
            )
        ],
    )


# ---------------------------------------------------------------------------
# Test v2 hierarchical output structure
# ---------------------------------------------------------------------------


class TestV2HierarchicalStructure:
    def test_output_has_descriptor(self):
        ir = _simple_ir()
        selectors = {"S001_Username_0": "<webctrl tag='input' id='user' />"}
        files = generate_object_repository_v2(ir, selectors)
        assert ".objects/descriptor.json" in files

    def test_element_files_in_correct_subdirectories(self):
        ir = _simple_ir()
        selectors = {"S001_Username_0": "<webctrl tag='input' id='user' />"}
        files = generate_object_repository_v2(ir, selectors)
        expected_path = ".objects/MyWebApp/1.0/MyWebApp/S001_Username_0.json"
        assert expected_path in files

    def test_element_json_content(self):
        ir = _simple_ir()
        selectors = {"S001_Username_0": "<webctrl tag='input' id='user' />"}
        files = generate_object_repository_v2(ir, selectors)
        elem_path = ".objects/MyWebApp/1.0/MyWebApp/S001_Username_0.json"
        data = json.loads(files[elem_path])
        assert data["displayName"] == "S001_Username_0"
        assert data["selectorXml"] == "<webctrl tag='input' id='user' />"
        assert data["uiFramework"] == "default"
        assert "elementId" in data
        assert "variables" in data


class TestV2Descriptor:
    def test_schema_version_is_2(self):
        ir = _simple_ir()
        selectors = {"S001_Username_0": "<webctrl tag='input' id='user' />"}
        files = generate_object_repository_v2(ir, selectors)
        desc = json.loads(files[".objects/descriptor.json"])
        assert desc["schemaVersion"] == "2.0"

    def test_descriptor_project_name(self):
        ir = _simple_ir()
        selectors = {"S001_Username_0": "<webctrl tag='input' id='user' />"}
        files = generate_object_repository_v2(ir, selectors)
        desc = json.loads(files[".objects/descriptor.json"])
        assert desc["projectName"] == "TestProcess"

    def test_descriptor_applications_structure(self):
        ir = _simple_ir()
        selectors = {"S001_Username_0": "<webctrl tag='input' id='user' />"}
        files = generate_object_repository_v2(ir, selectors)
        desc = json.loads(files[".objects/descriptor.json"])
        assert "applications" in desc
        assert len(desc["applications"]) == 1
        app = desc["applications"][0]
        assert app["name"] == "MyWebApp"
        assert app["version"] == "1.0"
        assert app["type"] == "web"
        assert len(app["screens"]) == 1
        assert app["screens"][0]["elementCount"] == 1


# ---------------------------------------------------------------------------
# Multiple apps / screens
# ---------------------------------------------------------------------------


class TestMultipleAppsAndScreens:
    def test_two_apps_produce_two_application_entries(self):
        ir = _multi_app_ir()
        selectors = {
            "S001_Field_0": "<webctrl tag='input' />",
            "S002_Field_0": "<wnd cls='SAP' />",
        }
        files = generate_object_repository_v2(ir, selectors)
        desc = json.loads(files[".objects/descriptor.json"])
        app_names = [a["name"] for a in desc["applications"]]
        assert "WebPortal" in app_names
        assert "SapGui" in app_names

    def test_sap_app_type(self):
        ir = _multi_app_ir()
        selectors = {"S002_Field_0": "<wnd cls='SAP' />"}
        files = generate_object_repository_v2(ir, selectors)
        desc = json.loads(files[".objects/descriptor.json"])
        sap_app = [a for a in desc["applications"] if a["name"] == "SapGui"][0]
        assert sap_app["type"] == "sap"


# ---------------------------------------------------------------------------
# Empty selectors
# ---------------------------------------------------------------------------


class TestEmptySelectors:
    def test_empty_selectors_returns_empty_dict(self):
        ir = _simple_ir()
        assert generate_object_repository_v2(ir, {}) == {}


# ---------------------------------------------------------------------------
# Variable extraction and resolution
# ---------------------------------------------------------------------------


class TestVariableExtraction:
    def test_single_variable(self):
        sel = "<webctrl tag='input' id='{{username}}' />"
        assert extract_selector_variables(sel) == ["username"]

    def test_multiple_variables(self):
        sel = "<webctrl url='{{appUrl}}/{{pagePath}}' />"
        result = extract_selector_variables(sel)
        assert result == ["appUrl", "pagePath"]

    def test_no_variables(self):
        sel = "<webctrl tag='input' id='user' />"
        assert extract_selector_variables(sel) == []

    def test_duplicate_variables(self):
        sel = "<webctrl id='{{x}}' name='{{x}}' />"
        assert extract_selector_variables(sel) == ["x", "x"]


class TestVariableResolution:
    def test_resolve_single(self):
        sel = "<webctrl id='{{username}}' />"
        result = resolve_selector_variables(sel, {"username": "admin"})
        assert result == "<webctrl id='admin' />"

    def test_resolve_multiple(self):
        sel = "<webctrl url='{{host}}/{{path}}' />"
        result = resolve_selector_variables(sel, {"host": "https://app.com", "path": "login"})
        assert result == "<webctrl url='https://app.com/login' />"

    def test_unresolved_variable_kept(self):
        sel = "<webctrl id='{{missing}}' />"
        result = resolve_selector_variables(sel, {})
        assert result == "<webctrl id='{{missing}}' />"


# ---------------------------------------------------------------------------
# Backward compatibility (v1)
# ---------------------------------------------------------------------------


class TestBackwardCompatibility:
    def test_v1_still_works(self):
        ir = _simple_ir()
        selectors = {"S001_Username_0": "<webctrl tag='input' id='user' />"}
        files = generate_object_repository(ir, selectors)
        assert ".objects/descriptor.json" in files
        desc = json.loads(files[".objects/descriptor.json"])
        assert desc["schemaVersion"] == "1.0"
        assert "screens" in desc

    def test_v1_empty_selectors(self):
        ir = _simple_ir()
        assert generate_object_repository(ir, {}) == {}


# ---------------------------------------------------------------------------
# UI Library generation
# ---------------------------------------------------------------------------


class TestUILibraryGeneration:
    def _make_screens(self) -> list[ObjectRepositoryScreenV2]:
        return [
            ObjectRepositoryScreenV2(
                name="LoginScreen",
                elements=[
                    ObjectRepositoryElementV2(
                        element_id="elem-001",
                        display_name="Username Field",
                        selector_xml="<webctrl tag='input' id='username' />",
                    ),
                    ObjectRepositoryElementV2(
                        element_id="elem-002",
                        display_name="Password Field",
                        selector_xml="<webctrl tag='input' id='password' />",
                    ),
                ],
            ),
        ]

    def test_project_json_present(self):
        files = generate_ui_library("MyApp", "1.0", self._make_screens())
        assert "project.json" in files

    def test_project_json_type(self):
        files = generate_ui_library("MyApp", "1.0", self._make_screens())
        proj = json.loads(files["project.json"])
        assert proj["projectType"] == "UILibrary"

    def test_project_json_version(self):
        files = generate_ui_library("MyApp", "2.5", self._make_screens())
        proj = json.loads(files["project.json"])
        assert proj["projectVersion"] == "2.5"

    def test_descriptor_present(self):
        files = generate_ui_library("MyApp", "1.0", self._make_screens())
        assert ".objects/descriptor.json" in files

    def test_descriptor_schema_version(self):
        files = generate_ui_library("MyApp", "1.0", self._make_screens())
        desc = json.loads(files[".objects/descriptor.json"])
        assert desc["schemaVersion"] == "2.0"

    def test_element_files_created(self):
        files = generate_ui_library("MyApp", "1.0", self._make_screens())
        assert ".objects/MyApp/1.0/LoginScreen/Username_Field.json" in files
        assert ".objects/MyApp/1.0/LoginScreen/Password_Field.json" in files

    def test_empty_screens(self):
        files = generate_ui_library("MyApp", "1.0", [])
        assert "project.json" in files
        assert ".objects/descriptor.json" in files
        desc = json.loads(files[".objects/descriptor.json"])
        assert desc["applications"][0]["screens"] == []
