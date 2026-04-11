"""End-to-end project generation test for the Odoo invoice processing PDD.

Parses the PDD, runs the full project assembler, and asserts that all
expected artifacts (REFramework XAML, DU subflow, taxonomy.json, Maestro
BPMN, coded workflow, agent scaffold, project.json with DU deps, and
Object Repository) are written to disk.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from rpa_architect.assembler.project_assembler import assemble_project
from rpa_architect.parser.pdd_parser import parse_pdd

PDD_PATH = (
    Path(__file__).parent.parent / "fixtures" / "pdds" / "odoo_invoice_processing.md"
)


@pytest.fixture(scope="module")
async def assembled_project(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """Parse the Odoo PDD and assemble the project to a temp dir."""
    out_dir = tmp_path_factory.mktemp("odoo_project")
    ir = parse_pdd(PDD_PATH)
    await assemble_project(ir, generated_files={}, output_dir=out_dir)
    return out_dir


# ---------------------------------------------------------------------------
# Standard REFramework artifacts
# ---------------------------------------------------------------------------


async def test_main_xaml_written(assembled_project: Path) -> None:
    assert (assembled_project / "Main.xaml").exists()


async def test_portable_project_has_only_minimal_main_xaml(
    assembled_project: Path,
) -> None:
    """Pivoted to Portable Coded Workflow — we no longer ship the
    REFramework stub XAML files (they referenced undeclared variables
    and failed uipcli compile validation). The project should have
    ONLY Main.xaml at the root, a compiled ProcessInvoiceMain.cs, and
    project.json. No Framework/ dir."""
    assert (assembled_project / "Main.xaml").exists()
    assert (assembled_project / "ProcessInvoiceMain.cs").exists()
    assert not (assembled_project / "Framework").exists(), (
        "Framework/ dir should not exist — pivoted to Coded Workflow"
    )


async def test_data_config_xlsx_written(assembled_project: Path) -> None:
    assert (assembled_project / "Data" / "Config.xlsx").exists()


async def test_project_json_written(assembled_project: Path) -> None:
    pj = assembled_project / "project.json"
    assert pj.exists()
    data = json.loads(pj.read_text(encoding="utf-8"))
    assert data["name"] == "OdooInvoiceProcessing"
    assert "UiPath.System.Activities" in data["dependencies"]


# ---------------------------------------------------------------------------
# Document Understanding artifacts (Phase A integration)
# ---------------------------------------------------------------------------


async def test_du_subflow_xaml_NOT_in_package(assembled_project: Path) -> None:
    """DU subflow is NOT bundled — it was design-time fakery that
    failed uipcli compile validation (referenced uidu: activities
    without the IntelligentOCR dep and used undeclared variables).
    The taxonomy is now written as a sibling artifact for design-time
    reference only."""
    assert not (
        assembled_project / "Framework" / "DocumentUnderstandingFlow.xaml"
    ).exists()


async def test_du_taxonomy_json_written_as_sibling(
    assembled_project: Path,
) -> None:
    """The DU taxonomy.json is written as a SIBLING design-time asset
    (not bundled), so humans can import it into Studio Web's Document
    Understanding designer manually."""
    sibling_du = (
        assembled_project.parent
        / f"{assembled_project.name}_document_processing"
    )
    p = sibling_du / "taxonomy.json"
    assert p.exists(), f"taxonomy.json missing at {p}"
    data = json.loads(p.read_text(encoding="utf-8"))
    assert "DocumentTypes" in data
    invoice = data["DocumentTypes"][0]
    assert invoice["Name"] == "Invoice"
    field_names = {f["FieldName"] for f in invoice["Fields"]}
    assert "VendorName" in field_names
    assert "TotalAmount" in field_names


async def test_project_json_includes_du_dependencies(assembled_project: Path) -> None:
    pj = assembled_project / "project.json"
    data = json.loads(pj.read_text(encoding="utf-8"))
    assert "UiPath.IntelligentOCR.Activities" in data["dependencies"]
    # The DocumentUnderstanding ML package name is checked too.
    assert any("DocumentUnderstanding" in k for k in data["dependencies"]), (
        f"got: {list(data['dependencies'].keys())}"
    )


async def test_main_xaml_invokes_coded_workflow(assembled_project: Path) -> None:
    """Main.xaml invokes ProcessInvoiceMain.cs (the real entry point).

    Replaces the old stub that referenced DU subflow — the DU logic
    is now effectively design-time-only on this track. The runtime
    logic is in the compiled C# Coded Workflow.
    """
    main_xaml = (assembled_project / "Main.xaml").read_text(encoding="utf-8")
    assert "InvokeWorkflowFile" in main_xaml
    assert "ProcessInvoiceMain.cs" in main_xaml


# ---------------------------------------------------------------------------
# Maestro BPMN artifact
# ---------------------------------------------------------------------------


async def test_maestro_bpmn_written_to_sibling_dir(assembled_project: Path) -> None:
    """The Maestro BPMN is written next to the project (NOT inside it).

    This is the honest layout: UiPath Maestro has no public deployment
    API as of 25.10, so the BPMN is a design-time artifact for manual
    import into Studio Web. Bundling it inside the .nupkg (as earlier
    versions did) was fakery — Orchestrator just ignores extra files
    inside the package.
    """
    sibling_candidates = list(
        assembled_project.parent.glob(f"{assembled_project.name}_maestro/*.bpmn")
    )
    assert sibling_candidates, "no Maestro BPMN sibling file written"
    content = sibling_candidates[0].read_text(encoding="utf-8")
    assert "Document" in content
    assert "userTask" in content


async def test_maestro_bpmn_well_formed_xml(assembled_project: Path) -> None:
    import xml.etree.ElementTree as ET

    sibling_candidates = list(
        assembled_project.parent.glob(f"{assembled_project.name}_maestro/*.bpmn")
    )
    assert sibling_candidates
    root = ET.fromstring(sibling_candidates[0].read_text(encoding="utf-8"))
    assert root is not None
    assert root.tag.endswith("definitions")


async def test_maestro_bpmn_NOT_inside_package(assembled_project: Path) -> None:
    """Verify the fakery is gone: the BPMN must NOT be inside the
    project directory (which becomes the .nupkg payload)."""
    inside = list((assembled_project / "Maestro").glob("*.bpmn")) if (
        assembled_project / "Maestro"
    ).exists() else []
    assert not inside, (
        f"Maestro BPMN found INSIDE project (fakery): {inside}. "
        "It must be in a sibling _maestro/ dir, not bundled."
    )


# ---------------------------------------------------------------------------
# Coded automation (C# Odoo workflow)
# ---------------------------------------------------------------------------


async def test_enterprise_project_has_all_cs_files(assembled_project: Path) -> None:
    """The enterprise IPF project ships 16 compiled C# files, not 1."""
    cs_files = set(p.name for p in assembled_project.glob("*.cs"))
    expected = {
        "EmbeddedInvoices.cs",
        "DocumentUnderstandingClient.cs",
        "LocalInvoiceExtractor.cs",
        "ProcessConfig.cs",
        "BatchMetrics.cs",
        "ProcessContext.cs",
        "OdooClient.cs",
        "BusinessRuleEngine.cs",
        "IState.cs",
        "ProcessExceptions.cs",
        "InitState.cs",
        "GetTransactionDataState.cs",
        "ProcessState.cs",
        "SetTransactionStatusState.cs",
        "EndState.cs",
        "ProcessInvoiceMain.cs",
    }
    missing = expected - cs_files
    assert not missing, f"missing C# files: {missing}"


async def test_odoo_client_uses_real_jsonrpc_calls(assembled_project: Path) -> None:
    odoo_client = (assembled_project / "OdooClient.cs").read_text(encoding="utf-8")
    assert "/web/dataset/call_kw" in odoo_client
    assert "account.move" in odoo_client
    assert "/web/session/authenticate" in odoo_client
    assert "HttpClient" in odoo_client
    assert "JsonSerializer" in odoo_client
    assert "invoice_line_ids" in odoo_client
    assert "activity_schedule" in odoo_client


async def test_process_invoice_main_is_state_machine_driver(assembled_project: Path) -> None:
    main = (assembled_project / "ProcessInvoiceMain.cs").read_text(encoding="utf-8")
    assert "[Workflow]" in main
    assert ": CodedWorkflow" in main
    assert "IState? state = new InitState()" in main
    assert "BusinessException" in main
    assert "RpaSystemException" in main


# ---------------------------------------------------------------------------
# Agent scaffold (vendor normalizer)
# ---------------------------------------------------------------------------


async def test_agent_scaffold_written_as_sibling(
    assembled_project: Path,
) -> None:
    """Agent scaffolds are written OUTSIDE the .nupkg (sibling dir).

    UiPath Portable Coded Workflow projects have no Python SDK agent
    entry point concept, so bundling Python scaffolds inside the
    nupkg just bloats the package. The scaffolds are placed next to
    the project so they can be packed/published separately via
    ``uipath pack`` on the agent itself.
    """
    sibling_agents = (
        assembled_project.parent / f"{assembled_project.name}_agents"
    )
    agent_dirs = list(sibling_agents.iterdir())
    assert agent_dirs, f"no Agents/ subdirectory at {sibling_agents}"
    for adir in agent_dirs:
        assert (adir / "main.py").exists(), f"missing main.py in {adir}"
        assert (adir / "uipath.json").exists(), f"missing uipath.json in {adir}"
        assert (adir / "pyproject.toml").exists(), f"missing pyproject.toml in {adir}"


async def test_agent_main_py_imports_uipath(assembled_project: Path) -> None:
    sibling_agents = (
        assembled_project.parent / f"{assembled_project.name}_agents"
    )
    agent_dirs = list(sibling_agents.iterdir())
    assert agent_dirs
    main_py = (agent_dirs[0] / "main.py").read_text(encoding="utf-8")
    assert "from uipath import UiPath" in main_py


# ---------------------------------------------------------------------------
# Object Repository (placeholder selectors at minimum)
# ---------------------------------------------------------------------------


async def test_object_repository_populated(assembled_project: Path) -> None:
    obj_dir = assembled_project / ".objects"
    assert obj_dir.exists()
    assert any(obj_dir.rglob("*.json")), "no .objects/*.json files written"


# ---------------------------------------------------------------------------
# XAML lint cleanliness on the generated REFramework files
# ---------------------------------------------------------------------------


async def test_main_xaml_lints_cleanly(assembled_project: Path) -> None:
    """The single Main.xaml must lint cleanly (no critical errors)."""
    from rpa_architect.xaml_lint import LintSeverity, lint_xaml

    main_xaml = assembled_project / "Main.xaml"
    assert main_xaml.exists()
    content = main_xaml.read_text(encoding="utf-8")
    issues = lint_xaml(content)
    critical = [
        f"{i.rule_id} {i.message}"
        for i in issues
        if i.severity == LintSeverity.ERROR and i.rule_id != "XL-H001"
    ]
    assert not critical, f"lint errors: {critical}"
