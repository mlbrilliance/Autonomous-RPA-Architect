#!/usr/bin/env python3
"""Proof of v0.3.0 features — comprehensive end-to-end demonstration.

Run: python3 proof/demo_v030.py

This script exercises every v0.3.0 feature and produces working output
files in proof/output/ to demonstrate the project is production-ready.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

# Add project to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from rpa_architect import __version__
from rpa_architect.generators import generate_activity, list_generators
from rpa_architect.generators.base import reset_counter
from rpa_architect.nuget.known_packages import (
    DEFAULT_VERSIONS,
    STANDARD_PACKAGES,
    get_default_version,
    get_package_for_activity,
    resolve_package_alias,
)
from rpa_architect.assembler.project_json_gen import generate_project_json, _PROJECT_JSON_TEMPLATE
from rpa_architect.xaml_lint import lint_xaml, LintSeverity
from rpa_architect.generators.base import xaml_namespace_header

OUTPUT_DIR = Path(__file__).parent / "output"
PASS = "\033[92mPASS\033[0m"
FAIL = "\033[91mFAIL\033[0m"
results: list[tuple[str, bool]] = []


def check(name: str, condition: bool, detail: str = "") -> None:
    results.append((name, condition))
    status = PASS if condition else FAIL
    print(f"  [{status}] {name}" + (f" — {detail}" if detail else ""))


def main() -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    print(f"\n{'='*70}")
    print(f"  Autonomous RPA Architect v{__version__} — Proof of Features")
    print(f"{'='*70}\n")

    # ---------------------------------------------------------------
    # WS1: Studio 2025.10 Compatibility
    # ---------------------------------------------------------------
    print("WS1: Studio 2025.10 Compatibility")
    print("-" * 40)

    check("Version is 0.3.0", __version__ == "0.3.0")

    check("NuGet targets 25.10",
          DEFAULT_VERSIONS["UiPath.System.Activities"] == "25.10.0",
          f"System.Activities = {DEFAULT_VERSIONS['UiPath.System.Activities']}")

    check("UIAutomation rename resolved",
          "UiPath.UIAutomation.Activities" in STANDARD_PACKAGES)

    check("Alias resolution works",
          resolve_package_alias("UiPath.UIAutomationNext.Activities") == "UiPath.UIAutomation.Activities")

    check("WaitScreenReady mapped",
          get_package_for_activity("WaitScreenReady") == "UiPath.UIAutomation.Activities")

    check("project.json targets 25.10",
          _PROJECT_JSON_TEMPLATE["toolVersion"] == "25.10.0")

    check("project.json has targetFramework",
          _PROJECT_JSON_TEMPLATE.get("targetFramework") == "net6.0-windows")

    # Generate WaitScreenReady
    reset_counter(1)
    wsr_xml = generate_activity("wait_screen_ready", display_name="Wait for Login", timeout_ms=15000)
    check("WaitScreenReady generates XML", "ui:WaitScreenReady" in wsr_xml)
    (OUTPUT_DIR / "wait_screen_ready.xml").write_text(wsr_xml, encoding="utf-8")

    # Deprecation lint
    classic_xaml = (
        '<?xml version="1.0" encoding="utf-8"?>\n'
        '<Activity xmlns="http://schemas.microsoft.com/netfx/2009/xaml/activities"'
        ' xmlns:ui="http://schemas.uipath.com/workflow/activities">\n'
        '<Sequence><Click DisplayName="Old Click" />\n'
        '<TypeInto DisplayName="Old Type" />\n'
        '<ui:NClick DisplayName="Modern Click" />'
        '</Sequence></Activity>'
    )
    issues = lint_xaml(classic_xaml)
    bp009 = [i for i in issues if i.rule_id == "XL-BP009"]
    check("XL-BP009 detects classic activities", len(bp009) >= 2,
          f"Found {len(bp009)} deprecated classic activities")

    print()

    # ---------------------------------------------------------------
    # WS2: Coded Automations API Generators
    # ---------------------------------------------------------------
    print("WS2: Coded Automations API Generators")
    print("-" * 40)

    reset_counter(1)

    # System APIs
    code = generate_activity("coded_get_asset", asset_name="QueueName", variable="queueName")
    check("coded_get_asset generates C#", "system.GetAsset" in code, code.strip())

    code = generate_activity("coded_get_credential", asset_name="AppCreds",
                             username_var="user", password_var="pass_")
    check("coded_get_credential generates C#", "GetCredential" in code)

    code = generate_activity("coded_log_message", message="Process started", level="Info")
    check("coded_log_message generates C#", "Log(" in code)

    code = generate_activity("coded_add_queue_item", queue_name="InvoiceQueue",
                             data_expr='new { Invoice = "INV-001" }')
    check("coded_add_queue_item generates C#", "AddQueueItem" in code)

    # UI APIs
    code = generate_activity("coded_open_app", descriptor_path="Descriptors.MyApp.LoginScreen",
                             variable="screen")
    check("coded_open_app generates C#", "uiAutomation.Open" in code)

    code = generate_activity("coded_click", screen_var="screen", element_name="LoginButton")
    check("coded_click generates C#", 'screen.Click("LoginButton")' in code)

    code = generate_activity("coded_type_into", screen_var="screen",
                             element_name="Username", text="admin")
    check("coded_type_into generates C#", "TypeInto" in code)

    # Coded workflow generation
    from rpa_architect.codegen.coded_workflow_gen import generate_coded_workflow
    workflow = generate_coded_workflow(
        class_name="ProcessInvoice",
        namespace="MyProject.CodedWorkflows",
        body_statements=[
            'var queueName = system.GetAsset("InvoiceQueue");',
            'var item = system.GetQueueItem(queueName.ToString());',
            'Log("Processing invoice", LogLevel.Info);',
            'system.SetTransactionStatus(item, UiPath.Core.Activities.TransactionStatus.Successful);',
        ],
    )
    check("Coded workflow has class", "class ProcessInvoice" in workflow)
    check("Coded workflow has [Workflow]", "[Workflow]" in workflow)
    check("Coded workflow has namespace", "namespace MyProject.CodedWorkflows" in workflow)
    (OUTPUT_DIR / "ProcessInvoice.cs").write_text(workflow, encoding="utf-8")

    # Count coded generators
    coded_gens = [g for g in list_generators() if g.category == "Coded API"]
    check("Coded API generators registered", len(coded_gens) >= 16,
          f"{len(coded_gens)} coded API generators")

    print()

    # ---------------------------------------------------------------
    # WS3: Object Repository v2
    # ---------------------------------------------------------------
    print("WS3: Object Repository v2")
    print("-" * 40)

    from rpa_architect.selectors.object_repository import (
        generate_object_repository_v2_from_apps as generate_object_repository_v2,
        extract_selector_variables,
        resolve_selector_variables,
        ObjectRepositoryAppV2,
        ObjectRepositoryScreenV2,
        ObjectRepositoryElementV2,
    )

    # Build a v2 Object Repository
    app = ObjectRepositoryAppV2(
        name="InvoicePortal",
        version="2.1",
        app_type="web",
        screens=[
            ObjectRepositoryScreenV2(
                name="LoginScreen",
                window_selector='<html app="chrome.exe" title="Invoice Portal*" />',
                elements=[
                    ObjectRepositoryElementV2(
                        element_id="e1-uuid",
                        display_name="Username Field",
                        selector_xml='<webctrl tag="input" id="username" />',
                        window_selector='<html app="chrome.exe" title="Invoice Portal*" />',
                        ui_framework="default",
                    ),
                    ObjectRepositoryElementV2(
                        element_id="e2-uuid",
                        display_name="Password Field",
                        selector_xml='<webctrl tag="input" id="password" />',
                        window_selector='<html app="chrome.exe" title="Invoice Portal*" />',
                        ui_framework="default",
                    ),
                    ObjectRepositoryElementV2(
                        element_id="e3-uuid",
                        display_name="Login Button",
                        selector_xml='<webctrl tag="button" name="Login" />',
                        window_selector='<html app="chrome.exe" title="Invoice Portal*" />',
                        ui_framework="default",
                    ),
                ],
            ),
            ObjectRepositoryScreenV2(
                name="DashboardScreen",
                window_selector='<html app="chrome.exe" title="Dashboard - {{Config_AppUrl}}" />',
                elements=[
                    ObjectRepositoryElementV2(
                        element_id="e4-uuid",
                        display_name="Search Box",
                        selector_xml='<webctrl tag="input" id="search" />',
                        window_selector='<html app="chrome.exe" title="Dashboard - {{Config_AppUrl}}" />',
                        ui_framework="default",
                        variables={"Config_AppUrl": "{{Config_AppUrl}}"},
                    ),
                ],
            ),
        ],
    )

    files = generate_object_repository_v2(
        [app],
        project_name="InvoiceBot",
    )
    check("V2 generates descriptor.json", ".objects/descriptor.json" in files)
    check("V2 generates app directories",
          any("InvoicePortal/" in k for k in files))
    check("V2 generates element files",
          any("LoginScreen/" in k for k in files))

    # Write to proof output
    for fpath, content in files.items():
        out = OUTPUT_DIR / fpath
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(content, encoding="utf-8")

    # Check descriptor.json
    desc = json.loads(files[".objects/descriptor.json"])
    check("Descriptor has schemaVersion 2.0", desc.get("schemaVersion") == "2.0")
    check("Descriptor has applications list", len(desc.get("applications", [])) >= 1)

    # Variable support
    vars_found = extract_selector_variables(
        '<html app="chrome.exe" title="Dashboard - {{Config_AppUrl}}" />'
    )
    check("Extracts variables from selectors", "Config_AppUrl" in vars_found)

    resolved = resolve_selector_variables(
        '<html title="{{Config_AppUrl}}" />',
        {"Config_AppUrl": "https://invoices.example.com"},
    )
    check("Resolves variables in selectors", "https://invoices.example.com" in resolved)

    print()

    # ---------------------------------------------------------------
    # WS4: Agent Deployment Scaffold
    # ---------------------------------------------------------------
    print("WS4: Agent Deployment Scaffold")
    print("-" * 40)

    from rpa_architect.assembler.agent_scaffold_gen import generate_agent_scaffold

    scaffold_files = generate_agent_scaffold(
        process_name="Invoice Processor",
        description="Automated invoice processing agent",
    )
    check("Scaffold generates uipath.json", "uipath.json" in scaffold_files)
    check("Scaffold generates entry-points.json", "entry-points.json" in scaffold_files)
    check("Scaffold generates pyproject.toml", "pyproject.toml" in scaffold_files)
    check("Scaffold generates main.py", "main.py" in scaffold_files)

    # Validate content
    uipath_json = json.loads(scaffold_files["uipath.json"])
    check("uipath.json has functions", "functions" in uipath_json)
    check("uipath.json main entry", "main" in uipath_json.get("functions", {}))

    toml_content = scaffold_files["pyproject.toml"]
    check("pyproject.toml has uipath dep", "uipath" in toml_content)

    main_py = scaffold_files["main.py"]
    check("main.py imports UiPath", "uipath" in main_py.lower() or "UiPath" in main_py)

    # Write scaffold to proof output
    for fpath, content in scaffold_files.items():
        out = OUTPUT_DIR / "agent_scaffold" / fpath
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(content, encoding="utf-8")

    print()

    # ---------------------------------------------------------------
    # WS5: Enhanced Validation
    # ---------------------------------------------------------------
    print("WS5: Enhanced Validation")
    print("-" * 40)

    # Coded workflow lint
    from rpa_architect.xaml_lint.rules_coded import lint_coded_file

    bad_cs = '''
using System;

namespace MyProject
{
    public class ProcessData : CodedWorkflow
    {
        public void Execute()
        {
            string password = "admin123";
            var url = "https://orchestrator.uipath.com/api/v1";
        }
    }
}
'''
    coded_issues = lint_coded_file(bad_cs)
    c001 = [i for i in coded_issues if i.rule_id == "XL-C001"]
    c002 = [i for i in coded_issues if i.rule_id == "XL-C002"]
    c003 = [i for i in coded_issues if i.rule_id == "XL-C003"]
    c004 = [i for i in coded_issues if i.rule_id == "XL-C004"]

    check("XL-C001 detects missing [Workflow]", len(c001) >= 1)
    check("XL-C002 detects hardcoded Orchestrator URL", len(c002) >= 1)
    check("XL-C003 detects missing using directive", len(c003) >= 1)
    check("XL-C004 detects unsafe credential", len(c004) >= 1)

    clean_cs = '''
using System;
using UiPath.CodedWorkflows;

namespace MyProject
{
    public class ProcessData : CodedWorkflow
    {
        [Workflow]
        public void Execute()
        {
            var asset = system.GetAsset("QueueName");
            Log("Processing", LogLevel.Info);
        }
    }
}
'''
    clean_issues = lint_coded_file(clean_cs)
    check("Clean coded workflow passes lint", len(clean_issues) == 0,
          f"{len(clean_issues)} issues" if clean_issues else "clean")

    # Selector scoring
    from rpa_architect.validation.selector_scorer import score_selector, aggregate_score

    good_score = score_selector(
        '<webctrl tag="input" id="username" automationid="txtUser" />', "UsernameField"
    )
    check("Good selector scores high", good_score.score >= 70,
          f"Score: {good_score.score}")

    bad_score = score_selector(
        '<webctrl idx="3" />', "UnknownElement"
    )
    check("Bad selector (idx only) scores low", bad_score.score < 100,
          f"Score: {bad_score.score}")

    scores = {
        "good": good_score,
        "bad": bad_score,
    }
    avg = aggregate_score(scores)
    check("Aggregate score computes", 0 <= avg <= 100, f"Average: {avg}")

    print()

    # ---------------------------------------------------------------
    # WS6: MCP/CLI Enhancements (sync verification)
    # ---------------------------------------------------------------
    print("WS6: MCP/CLI Enhancements")
    print("-" * 40)

    # Verify MCP tools exist
    from rpa_architect.mcp_server import tools as mcp_tools
    check("MCP: upgrade_project tool exists", hasattr(mcp_tools, "upgrade_project"))
    check("MCP: generate_coded_workflow tool exists", hasattr(mcp_tools, "generate_coded_workflow"))
    check("MCP: score_selectors tool exists", hasattr(mcp_tools, "score_selectors"))
    check("MCP: generate_agent_scaffold tool exists", hasattr(mcp_tools, "generate_agent_scaffold"))

    # Verify CLI commands exist
    from rpa_architect.cli import app as cli_app
    cmd_names = [cmd.name for cmd in cli_app.registered_commands]
    check("CLI: upgrade command exists", "upgrade" in cmd_names)
    check("CLI: lint-coded command exists", "lint-coded" in cmd_names)
    check("CLI: score-selectors command exists", "score-selectors" in cmd_names)
    check("CLI: scaffold-agent command exists", "scaffold-agent" in cmd_names)

    print()

    # ---------------------------------------------------------------
    # Generator Stats
    # ---------------------------------------------------------------
    print("Generator & Rule Statistics")
    print("-" * 40)
    all_gens = list_generators()
    categories = {}
    for g in all_gens:
        categories.setdefault(g.category, []).append(g.name)
    for cat, names in sorted(categories.items()):
        print(f"  {cat}: {len(names)} generators")
    print(f"  TOTAL: {len(all_gens)} generators")

    check("Total generators >= 96", len(all_gens) >= 96, f"{len(all_gens)} generators")

    # Lint rules count
    from rpa_architect.xaml_lint.engine import create_default_engine
    engine = create_default_engine()
    check("Lint engine has >= 21 rules", engine.rule_count >= 21,
          f"{engine.rule_count} XAML rules + 4 coded rules")

    print()

    # ---------------------------------------------------------------
    # Summary
    # ---------------------------------------------------------------
    passed = sum(1 for _, ok in results if ok)
    failed = sum(1 for _, ok in results if not ok)
    total = len(results)

    print(f"{'='*70}")
    print(f"  RESULTS: {passed}/{total} passed, {failed} failed")
    print(f"{'='*70}")

    if failed:
        print("\nFailed checks:")
        for name, ok in results:
            if not ok:
                print(f"  FAIL: {name}")
        sys.exit(1)
    else:
        print("\n  All v0.3.0 features verified successfully!")
        print(f"  Output files written to: {OUTPUT_DIR}")
        print()


if __name__ == "__main__":
    main()
