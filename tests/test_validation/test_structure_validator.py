"""Tests for structure_validator — Stream F: config-driven architecture checks."""
from __future__ import annotations

from pathlib import Path

import pytest

from rpa_architect.validation.structure_validator import (
    ValidationIssue,
    _check_config_driven_architecture,
    _check_project_json,
    _check_required_files,
    _check_reframework_structure,
    validate_structure,
)


# ===================================================================
# _check_config_driven_architecture
# ===================================================================

class TestCheckConfigDrivenArchitecture:

    def test_detects_hardcoded_url_in_cs(self, tmp_path: Path):
        (tmp_path / "project.json").write_text("{}", encoding="utf-8")
        wf = tmp_path / "CodedWorkflows"
        wf.mkdir()
        (wf / "Process.cs").write_text(
            'var url = "https://myapp.example.com/api/v1";',
            encoding="utf-8",
        )
        issues = _check_config_driven_architecture(tmp_path)
        url_issues = [i for i in issues if "Hardcoded URL" in i.message]
        assert len(url_issues) >= 1
        assert url_issues[0].severity == "info"

    def test_detects_hardcoded_url_in_xaml(self, tmp_path: Path):
        wf = tmp_path / "Workflows"
        wf.mkdir()
        (wf / "Process.xaml").write_text(
            '<Assign Value="https://prod.mycompany.com/api" />',
            encoding="utf-8",
        )
        issues = _check_config_driven_architecture(tmp_path)
        url_issues = [i for i in issues if "Hardcoded URL" in i.message]
        assert len(url_issues) >= 1

    def test_ignores_schema_urls(self, tmp_path: Path):
        wf = tmp_path / "Workflows"
        wf.mkdir()
        (wf / "Main.xaml").write_text(
            '<Activity xmlns="http://schemas.microsoft.com/netfx/2009/xaml/activities" />',
            encoding="utf-8",
        )
        issues = _check_config_driven_architecture(tmp_path)
        url_issues = [i for i in issues if "Hardcoded URL" in i.message]
        assert url_issues == []

    def test_ignores_localhost_urls(self, tmp_path: Path):
        wf = tmp_path / "Workflows"
        wf.mkdir()
        (wf / "Dev.cs").write_text(
            'var url = "http://localhost:5000/api";',
            encoding="utf-8",
        )
        issues = _check_config_driven_architecture(tmp_path)
        url_issues = [i for i in issues if "Hardcoded URL" in i.message]
        assert url_issues == []

    def test_detects_hardcoded_credential(self, tmp_path: Path):
        wf = tmp_path / "Workflows"
        wf.mkdir()
        (wf / "Login.cs").write_text(
            'var conn = "password=\"PLACEHOLDER_TEST_VALUE\"";',
            encoding="utf-8",
        )
        issues = _check_config_driven_architecture(tmp_path)
        cred_issues = [i for i in issues if "credential" in i.message.lower()]
        assert len(cred_issues) >= 1
        assert cred_issues[0].severity == "warning"

    def test_skips_framework_directory(self, tmp_path: Path):
        fw = tmp_path / "Framework"
        fw.mkdir()
        (fw / "InitAllSettings.xaml").write_text(
            '<Assign Value="https://orchestrator.uipath.com/api" />',
            encoding="utf-8",
        )
        issues = _check_config_driven_architecture(tmp_path)
        assert issues == []

    def test_skips_objects_directory(self, tmp_path: Path):
        obj = tmp_path / ".objects"
        obj.mkdir()
        (obj / "screen.xaml").write_text(
            'password="hunter2"',
            encoding="utf-8",
        )
        issues = _check_config_driven_architecture(tmp_path)
        assert issues == []

    def test_no_issues_on_clean_project(self, tmp_path: Path):
        wf = tmp_path / "Workflows"
        wf.mkdir()
        (wf / "Process.cs").write_text(
            'var config = in_Config["URL"];\nvar result = api.Call(config);',
            encoding="utf-8",
        )
        issues = _check_config_driven_architecture(tmp_path)
        assert issues == []


# ===================================================================
# validate_structure (integration)
# ===================================================================

class TestValidateStructure:

    def test_nonexistent_directory(self, tmp_path: Path):
        issues = validate_structure(tmp_path / "nonexistent")
        assert len(issues) == 1
        assert issues[0].severity == "error"
        assert "does not exist" in issues[0].message

    def test_empty_directory_returns_issues(self, tmp_path: Path):
        issues = validate_structure(tmp_path)
        # At minimum, project.json is missing
        assert any(i.message == "Project manifest is missing." for i in issues)

    def test_valid_project_minimal(self, tmp_path: Path):
        (tmp_path / "project.json").write_text(
            '{"name": "Test", "main": "Main.xaml", "dependencies": {}}',
            encoding="utf-8",
        )
        (tmp_path / "Main.xaml").write_text("<Activity />", encoding="utf-8")
        (tmp_path / "Process.xaml").write_text("<Activity />", encoding="utf-8")
        issues = validate_structure(tmp_path)
        errors = [i for i in issues if i.severity == "error"]
        assert errors == []

    def test_includes_config_driven_check(self, tmp_path: Path):
        (tmp_path / "project.json").write_text(
            '{"name": "Test", "main": "Main.xaml", "dependencies": {}}',
            encoding="utf-8",
        )
        wf = tmp_path / "Workflows"
        wf.mkdir()
        (wf / "Login.cs").write_text(
            'var x = "apikey=\"sk-12345\"";',
            encoding="utf-8",
        )
        issues = validate_structure(tmp_path)
        cred_issues = [i for i in issues if "credential" in i.message.lower()]
        assert len(cred_issues) >= 1


class TestCheckProjectJson:

    def test_invalid_json(self, tmp_path: Path):
        (tmp_path / "project.json").write_text("not json{{{", encoding="utf-8")
        issues = _check_project_json(tmp_path)
        assert any(i.severity == "error" and "not valid JSON" in i.message for i in issues)

    def test_missing_fields(self, tmp_path: Path):
        (tmp_path / "project.json").write_text("{}", encoding="utf-8")
        issues = _check_project_json(tmp_path)
        missing = [i for i in issues if "missing recommended field" in i.message]
        assert len(missing) >= 2  # name, main, dependencies

    def test_unusual_expression_language(self, tmp_path: Path):
        (tmp_path / "project.json").write_text(
            '{"name": "X", "main": "Main.xaml", "dependencies": {}, "expressionLanguage": "Python"}',
            encoding="utf-8",
        )
        issues = _check_project_json(tmp_path)
        assert any("Unusual expressionLanguage" in i.message for i in issues)
