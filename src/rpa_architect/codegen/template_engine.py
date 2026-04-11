"""Jinja2 template engine with UiPath-specific filters."""

from __future__ import annotations

import html
import re
from pathlib import Path
from typing import Any

import jinja2


# ---------------------------------------------------------------------------
# Custom Jinja2 filters
# ---------------------------------------------------------------------------

def _split_words(value: str) -> list[str]:
    """Split a string into words, handling snake_case, camelCase, PascalCase, spaces, hyphens."""
    # First split on underscores, spaces, hyphens
    parts = re.split(r"[_\s\-]+", value)
    words: list[str] = []
    for part in parts:
        if not part:
            continue
        # Split camelCase/PascalCase boundaries: insert split before uppercase letters
        sub = re.sub(r"([a-z0-9])([A-Z])", r"\1_\2", part)
        sub = re.sub(r"([A-Z]+)([A-Z][a-z])", r"\1_\2", sub)
        words.extend(w for w in sub.split("_") if w)
    return words


def pascal_case(value: str) -> str:
    """Convert a string to PascalCase.

    Examples:
        >>> pascal_case("get_transaction_data")
        'GetTransactionData'
        >>> pascal_case("my workflow name")
        'MyWorkflowName'
    """
    return "".join(word.capitalize() for word in _split_words(value))


def camel_case(value: str) -> str:
    """Convert a string to camelCase.

    Examples:
        >>> camel_case("GetTransactionData")
        'getTransactionData'
        >>> camel_case("my_field_name")
        'myFieldName'
    """
    words = _split_words(value)
    if not words:
        return ""
    return words[0].lower() + "".join(w.capitalize() for w in words[1:])


_PYTHON_TO_CSHARP_TYPES: dict[str, str] = {
    "str": "string",
    "string": "string",
    "int": "int",
    "integer": "int",
    "float": "double",
    "double": "double",
    "decimal": "decimal",
    "bool": "bool",
    "boolean": "bool",
    "date": "DateTime",
    "datetime": "DateTime",
    "list": "List<object>",
    "dict": "Dictionary<string, object>",
    "dictionary": "Dictionary<string, object>",
    "datatable": "DataTable",
    "datarow": "DataRow",
    "object": "object",
    "void": "void",
    "": "object",
}


def csharp_type(value: str) -> str:
    """Map a type name to its C# equivalent.

    Examples:
        >>> csharp_type("str")
        'string'
        >>> csharp_type("DataTable")
        'DataTable'
    """
    return _PYTHON_TO_CSHARP_TYPES.get(value.lower().strip(), value)


def xml_escape(value: str) -> str:
    """Escape a string for safe embedding in XML/XAML.

    Uses the standard HTML/XML entity escaping for &, <, >, ", '.
    """
    return html.escape(value, quote=True)


# ---------------------------------------------------------------------------
# Default built-in templates (used when no templates/ directory exists)
# ---------------------------------------------------------------------------

_BUILTIN_TEMPLATES: dict[str, str] = {
    "workflow_generic.cs.j2": '''\
using System;
using System.Collections.Generic;
using System.Data;
using UiPath.CodedWorkflows;
using UiPath.CodedWorkflows.Interfaces;
using UiPath.Core.Activities;

namespace CodedWorkflows
{
    /// <summary>
    /// {{ description | default("Auto-generated coded workflow.") }}
    /// </summary>
    public class {{ workflow_name | pascal_case }} : CodedWorkflow
    {
        {% for svc in services %}
        [Service]
        public {{ svc.split(".")[-1] }} _{{ svc.split(".")[-1] | camel_case }} { get; set; }
        {% endfor %}

        [Workflow]
        public void Execute()
        {
            try
            {
                Log("Starting {{ workflow_name }}...", LogLevel.Info);
                {% for step in steps %}

                // Step: {{ step.get("name", "Step " ~ loop.index) }}
                // {{ step.get("description", "") }}
                {% endfor %}

                Log("Completed {{ workflow_name }} successfully.", LogLevel.Info);
            }
            catch (Exception ex)
            {
                Log($"Error in {{ workflow_name }}: {ex.Message}", LogLevel.Error);
                throw;
            }
        }
    }
}
''',
    "workflow_ui_automation.cs.j2": '''\
using System;
using System.Collections.Generic;
using System.Data;
using UiPath.CodedWorkflows;
using UiPath.CodedWorkflows.Interfaces;
using UiPath.Core.Activities;
using UiPath.UIAutomationNext.API.Contracts;
using UiPath.UIAutomationNext.API.Models;

namespace CodedWorkflows
{
    /// <summary>
    /// {{ description | default("UI Automation coded workflow.") }}
    /// </summary>
    public class {{ workflow_name | pascal_case }} : CodedWorkflow
    {
        {% for svc in services %}
        [Service]
        public {{ svc.split(".")[-1] }} _{{ svc.split(".")[-1] | camel_case }} { get; set; }
        {% endfor %}

        [Workflow]
        public void Execute()
        {
            try
            {
                Log("Starting UI automation: {{ workflow_name }}...", LogLevel.Info);
                {% for step in steps %}

                // Step {{ loop.index }}: {{ step.get("name", "Unnamed") }}
                // Action: {{ step.get("action", "interact") }}
                // Target: {{ step.get("target", "N/A") }}
                {% if step.get("selector") %}
                // Selector: {{ step.get("selector") | xml_escape }}
                {% endif %}
                {% endfor %}

                Log("UI automation {{ workflow_name }} completed.", LogLevel.Info);
            }
            catch (Exception ex)
            {
                Log($"UI automation error in {{ workflow_name }}: {ex.Message}", LogLevel.Error);
                TakeScreenshot("Error_{{ workflow_name }}");
                throw;
            }
        }

        private void TakeScreenshot(string name)
        {
            try
            {
                Log($"Capturing screenshot: {name}", LogLevel.Info);
            }
            catch
            {
                // Best-effort screenshot
            }
        }
    }
}
''',
    "workflow_data_transform.cs.j2": '''\
using System;
using System.Collections.Generic;
using System.Data;
using System.Linq;
using UiPath.CodedWorkflows;
using UiPath.CodedWorkflows.Interfaces;
using UiPath.Core.Activities;

namespace CodedWorkflows
{
    /// <summary>
    /// {{ description | default("Data transformation coded workflow.") }}
    /// </summary>
    public class {{ workflow_name | pascal_case }} : CodedWorkflow
    {
        {% for svc in services %}
        [Service]
        public {{ svc.split(".")[-1] }} _{{ svc.split(".")[-1] | camel_case }} { get; set; }
        {% endfor %}

        [Workflow]
        public DataTable Execute(DataTable inputData)
        {
            try
            {
                Log("Starting data transform: {{ workflow_name }}...", LogLevel.Info);
                Log($"Input rows: {inputData.Rows.Count}", LogLevel.Info);

                var outputData = inputData.Clone();
                {% for step in steps %}

                // Transform step {{ loop.index }}: {{ step.get("name", "Transform") }}
                // {{ step.get("description", "") }}
                {% endfor %}

                Log($"Transform complete. Output rows: {outputData.Rows.Count}", LogLevel.Info);
                return outputData;
            }
            catch (Exception ex)
            {
                Log($"Data transform error in {{ workflow_name }}: {ex.Message}", LogLevel.Error);
                throw;
            }
        }
    }
}
''',
    "workflow_api_call.cs.j2": '''\
using System;
using System.Collections.Generic;
using System.Net.Http;
using System.Text.Json;
using System.Threading.Tasks;
using UiPath.CodedWorkflows;
using UiPath.CodedWorkflows.Interfaces;
using UiPath.Core.Activities;

namespace CodedWorkflows
{
    /// <summary>
    /// {{ description | default("API integration coded workflow.") }}
    /// </summary>
    public class {{ workflow_name | pascal_case }} : CodedWorkflow
    {
        {% for svc in services %}
        [Service]
        public {{ svc.split(".")[-1] }} _{{ svc.split(".")[-1] | camel_case }} { get; set; }
        {% endfor %}

        [Workflow]
        public async Task<string> Execute(string endpoint, string method = "GET", string body = null)
        {
            try
            {
                Log($"Calling API: {method} {endpoint}", LogLevel.Info);
                {% for step in steps %}

                // API step {{ loop.index }}: {{ step.get("name", "API Call") }}
                // {{ step.get("description", "") }}
                {% endfor %}

                await Task.CompletedTask;
                Log("API call {{ workflow_name }} completed.", LogLevel.Info);
                return "{}";
            }
            catch (Exception ex)
            {
                Log($"API error in {{ workflow_name }}: {ex.Message}", LogLevel.Error);
                throw;
            }
        }
    }
}
''',
    "workflow_queue_processing.cs.j2": '''\
using System;
using System.Collections.Generic;
using UiPath.CodedWorkflows;
using UiPath.CodedWorkflows.Interfaces;
using UiPath.Core.Activities;

namespace CodedWorkflows
{
    /// <summary>
    /// {{ description | default("Queue processing coded workflow.") }}
    /// </summary>
    public class {{ workflow_name | pascal_case }} : CodedWorkflow
    {
        {% for svc in services %}
        [Service]
        public {{ svc.split(".")[-1] }} _{{ svc.split(".")[-1] | camel_case }} { get; set; }
        {% endfor %}

        [Workflow]
        public void Execute()
        {
            try
            {
                Log("Starting queue processing: {{ workflow_name }}...", LogLevel.Info);

                // Get transaction item from Orchestrator queue
                {% for step in steps %}

                // Queue step {{ loop.index }}: {{ step.get("name", "Process Item") }}
                // {{ step.get("description", "") }}
                {% endfor %}

                Log("Queue processing {{ workflow_name }} completed.", LogLevel.Info);
            }
            catch (BusinessRuleException brEx)
            {
                Log($"Business rule exception in {{ workflow_name }}: {brEx.Message}", LogLevel.Warn);
                throw;
            }
            catch (Exception ex)
            {
                Log($"System exception in {{ workflow_name }}: {ex.Message}", LogLevel.Error);
                throw;
            }
        }
    }
}
''',
    "dto.cs.j2": '''\
using System;
using System.Collections.Generic;

namespace Models
{
    /// <summary>
    /// Data transfer object: {{ workflow_name }}.
    /// {{ description | default("") }}
    /// </summary>
    public class {{ workflow_name | pascal_case }}
    {
        {% for field in fields %}
        /// <summary>{{ field.get("description", field.get("name", "")) }}</summary>
        public {{ field.get("type", "string") | csharp_type }} {{ field.get("name", "Field" ~ loop.index) | pascal_case }} { get; set; }
        {% endfor %}
        {% if not fields %}
        public string Id { get; set; }
        public string Name { get; set; }
        public DateTime CreatedAt { get; set; } = DateTime.UtcNow;
        {% endif %}

        public override string ToString()
        {
            return $"{{ workflow_name | pascal_case }}({%- if fields -%}{{ fields[0].get("name", "Id") | pascal_case }}={{ '{' }}{{ fields[0].get("name", "Id") | pascal_case }}{{ '}' }}{%- else -%}Id={Id}{%- endif -%})";
        }
    }
}
''',
    "config_wrapper.cs.j2": '''\
using System;
using System.Collections.Generic;
using System.Data;
using UiPath.CodedWorkflows;
using UiPath.Core.Activities;

namespace CodedWorkflows
{
    /// <summary>
    /// Wrapper for REFramework Config.xlsx access in coded workflows.
    /// Provides typed access to Settings, Constants, and Assets sheets.
    /// </summary>
    public class ConfigWrapper : CodedWorkflow
    {
        private Dictionary<string, object> _settings;
        private Dictionary<string, object> _constants;
        private Dictionary<string, object> _assets;

        [Workflow]
        public void Initialize(DataTable configData)
        {
            try
            {
                Log("Initializing ConfigWrapper...", LogLevel.Info);
                _settings = new Dictionary<string, object>(StringComparer.OrdinalIgnoreCase);
                _constants = new Dictionary<string, object>(StringComparer.OrdinalIgnoreCase);
                _assets = new Dictionary<string, object>(StringComparer.OrdinalIgnoreCase);

                if (configData != null)
                {
                    foreach (DataRow row in configData.Rows)
                    {
                        var name = row["Name"]?.ToString() ?? "";
                        var value = row["Value"];
                        var sheet = row.Table.TableName ?? "Settings";

                        switch (sheet)
                        {
                            case "Settings":
                                _settings[name] = value;
                                break;
                            case "Constants":
                                _constants[name] = value;
                                break;
                            case "Assets":
                                _assets[name] = value;
                                break;
                        }
                    }
                }

                Log($"Config loaded: {_settings.Count} settings, {_constants.Count} constants, {_assets.Count} assets.", LogLevel.Info);
            }
            catch (Exception ex)
            {
                Log($"Error initializing config: {ex.Message}", LogLevel.Error);
                throw;
            }
        }

        public string GetSetting(string name, string defaultValue = "")
        {
            return _settings.TryGetValue(name, out var val) ? val?.ToString() ?? defaultValue : defaultValue;
        }

        public string GetConstant(string name, string defaultValue = "")
        {
            return _constants.TryGetValue(name, out var val) ? val?.ToString() ?? defaultValue : defaultValue;
        }

        public string GetAsset(string name, string defaultValue = "")
        {
            return _assets.TryGetValue(name, out var val) ? val?.ToString() ?? defaultValue : defaultValue;
        }
    }
}
''',
    "test.cs.j2": '''\
using System;
using UiPath.CodedWorkflows;
using UiPath.CodedWorkflows.Interfaces;
using UiPath.Core.Activities;

namespace CodedTests
{
    /// <summary>
    /// Test case for {{ target_workflow }}.
    /// </summary>
    public class {{ target_workflow | pascal_case }}Tests : CodedWorkflow
    {
        [TestCase]
        public void Test_{{ target_workflow | pascal_case }}_Execute_Succeeds()
        {
            try
            {
                Log("Running test: {{ target_workflow }} execute succeeds...", LogLevel.Info);

                // Arrange
                // TODO: Set up test data and mocks

                // Act
                // TODO: Invoke {{ target_workflow }}

                // Assert
                // TODO: Verify expected outcomes

                Log("Test passed: {{ target_workflow }} execute succeeds.", LogLevel.Info);
            }
            catch (Exception ex)
            {
                Log($"Test failed: {ex.Message}", LogLevel.Error);
                throw;
            }
        }

        [TestCase]
        public void Test_{{ target_workflow | pascal_case }}_Handles_Error()
        {
            try
            {
                Log("Running test: {{ target_workflow }} handles error...", LogLevel.Info);

                // Arrange
                // TODO: Set up error condition

                // Act & Assert
                // TODO: Verify error handling behavior

                Log("Test passed: {{ target_workflow }} handles error.", LogLevel.Info);
            }
            catch (Exception ex)
            {
                Log($"Test failed: {ex.Message}", LogLevel.Error);
                throw;
            }
        }
    }
}
''',
    "selectors.json.j2": '''\
{
    "selectorRepository": "{{ workflow_name }}",
    "version": "1.0",
    "selectors": [
        {% for name, sel in selectors.items() %}
        {
            "name": "{{ name | xml_escape }}",
            "selector": "{{ sel | xml_escape }}",
            "validated": false
        }{% if not loop.last %},{% endif %}
        {% endfor %}
    ]
}
''',
    "project.json.j2": '''\
{
    "name": "GeneratedRPAProject",
    "projectId": "00000000-0000-0000-0000-000000000000",
    "description": "Auto-generated UiPath project",
    "main": "Main.xaml",
    "dependencies": {
        "UiPath.System.Activities": "[24.10.6]",
        "UiPath.UIAutomation.Activities": "[24.10.8]",
        "UiPath.Excel.Activities": "[2.24.2]",
        "UiPath.Mail.Activities": "[1.23.11]",
        "UiPath.WebAPI.Activities": "[1.20.1]"
    },
    "webServices": [],
    "entitiesRecordStores": [],
    "schemaVersion": "4.0",
    "studioVersion": "24.10.6.0",
    "projectVersion": "1.0.0",
    "runtimeOptions": {
        "autoDispose": false,
        "netFrameworkLazyLoading": false,
        "isPausable": true,
        "isAttended": false,
        "requiresUserInteraction": false,
        "supportsPersistence": false,
        "workflowSerialization": "DataContract",
        "excludedLoggedData": [
            "Private:*",
            "Output:*"
        ],
        "executionType": "Workflow",
        "readyForPiP": false,
        "startsInPiP": false,
        "mustRestoreAllDependencies": true,
        "targetFramework": "Windows"
    },
    "designOptions": {
        "projectProfile": "Developement",
        "outputType": "Process",
        "libraryOptions": {
            "includeOriginalXaml": false,
            "privateWorkflows": []
        }
    },
    "expressionLanguage": "CSharp",
    "isTemplate": false,
    "templateProjectData": {},
    "publishData": {},
    "targetFramework": "Windows"
}
''',
}


class TemplateEngine:
    """Jinja2 template engine with UiPath-specific filters and built-in fallback templates."""

    def __init__(self, templates_dir: Path | str | None = None) -> None:
        """Initialise the engine.

        Args:
            templates_dir: Optional directory containing .j2 templates.
                Falls back to built-in templates when a requested name is not
                found on disk.
        """
        loaders: list[jinja2.BaseLoader] = []

        if templates_dir is not None:
            fs_path = Path(templates_dir)
            if fs_path.is_dir():
                loaders.append(jinja2.FileSystemLoader(str(fs_path)))

        # Built-in dict loader as fallback
        loaders.append(jinja2.DictLoader(_BUILTIN_TEMPLATES))

        self._env = jinja2.Environment(
            loader=jinja2.ChoiceLoader(loaders),
            undefined=jinja2.StrictUndefined,
            keep_trailing_newline=True,
            trim_blocks=True,
            lstrip_blocks=True,
        )

        # Register custom filters
        self._env.filters["pascal_case"] = pascal_case
        self._env.filters["camel_case"] = camel_case
        self._env.filters["csharp_type"] = csharp_type
        self._env.filters["xml_escape"] = xml_escape

    def render(self, template_name: str, context: dict | None = None, **kwargs: Any) -> str:
        """Render a named template with the given context.

        Supports both calling conventions:
        - ``engine.render("t.j2", {"key": "val"})``  (positional dict)
        - ``engine.render("t.j2", key="val")``        (keyword args)

        Args:
            template_name: Template filename (e.g. ``workflow_generic.cs.j2``).
            context: Optional dict of variables passed to the template.
            **kwargs: Additional keyword variables (merged with *context*).

        Returns:
            Rendered string content.
        """
        merged = dict(context) if context else {}
        merged.update(kwargs)
        template = self._env.get_template(template_name)
        return template.render(**merged)

    @property
    def available_templates(self) -> list[str]:
        """List all template names reachable by this engine."""
        return sorted(self._env.loader.list_templates())
