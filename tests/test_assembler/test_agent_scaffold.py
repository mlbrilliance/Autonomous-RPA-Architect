"""Tests for the UiPath Python SDK agent scaffold generator."""

from __future__ import annotations

import json

import pytest

from rpa_architect.assembler.agent_scaffold_gen import (
    _to_snake_case,
    generate_agent_scaffold,
)


class TestToSnakeCase:
    """Tests for the snake_case conversion helper."""

    def test_simple_name(self):
        assert _to_snake_case("InvoiceProcessing") == "invoice_processing"

    def test_spaces_and_hyphens(self):
        assert _to_snake_case("My Cool-Process") == "my_cool_process"

    def test_already_snake(self):
        assert _to_snake_case("already_snake") == "already_snake"

    def test_empty_string(self):
        assert _to_snake_case("") == "unnamed_process"

    def test_special_characters(self):
        assert _to_snake_case("Process@#$%123") == "process_123"


class TestGenerateAgentScaffold:
    """Tests for generate_agent_scaffold."""

    def test_returns_five_files(self):
        result = generate_agent_scaffold("TestProcess")
        assert set(result.keys()) == {
            "uipath.json",
            "entry-points.json",
            "pyproject.toml",
            "main.py",
            "test_main.py",
        }

    def test_uipath_json_structure(self):
        result = generate_agent_scaffold("TestProcess")
        data = json.loads(result["uipath.json"])
        assert data == {"functions": {"main": "main.py:main"}}

    def test_entry_points_json_default(self):
        result = generate_agent_scaffold("TestProcess")
        data = json.loads(result["entry-points.json"])
        assert "entryPoints" in data
        assert len(data["entryPoints"]) == 1
        ep = data["entryPoints"][0]
        assert ep["name"] == "main"
        assert ep["module"] == "main"
        assert ep["function"] == "main"
        assert ep["type"] == "function"

    def test_pyproject_toml_snake_case_name(self):
        result = generate_agent_scaffold("Invoice Processing")
        toml = result["pyproject.toml"]
        assert 'name = "invoice_processing"' in toml

    def test_pyproject_toml_dependencies(self):
        result = generate_agent_scaffold("Test")
        toml = result["pyproject.toml"]
        assert 'dependencies = ["uipath>=2.10"]' in toml

    def test_pyproject_toml_description(self):
        result = generate_agent_scaffold("Test", description="My description")
        toml = result["pyproject.toml"]
        assert 'description = "My description"' in toml

    def test_main_py_has_uipath_import(self):
        result = generate_agent_scaffold("TestProcess")
        main = result["main.py"]
        assert "from uipath import UiPath" in main

    def test_main_py_has_process_name(self):
        result = generate_agent_scaffold("My Process")
        main = result["main.py"]
        assert "My Process" in main

    def test_custom_entry_points(self):
        custom_eps = [
            {"name": "run", "module": "runner", "function": "run", "type": "function"},
            {"name": "setup", "module": "setup", "function": "init", "type": "function"},
        ]
        result = generate_agent_scaffold("Test", entry_points=custom_eps)
        data = json.loads(result["entry-points.json"])
        assert len(data["entryPoints"]) == 2
        assert data["entryPoints"][0]["name"] == "run"
        assert data["entryPoints"][1]["name"] == "setup"

    def test_pyproject_toml_python_version(self):
        result = generate_agent_scaffold("Test")
        toml = result["pyproject.toml"]
        assert 'requires-python = ">=3.11"' in toml
