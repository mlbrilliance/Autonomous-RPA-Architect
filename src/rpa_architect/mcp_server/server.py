"""FastMCP server exposing RPA Architect tools."""

from __future__ import annotations

from mcp.server.fastmcp import FastMCP

from rpa_architect.mcp_server.tools import (
    build_knowledge,
    deploy_project,
    diagnose_failures,
    generate_enterprise_reframework,
    generate_from_ir,
    generate_from_pdd,
    generate_selectors,
    get_community_cloud_gotchas,
    get_execution_logs,
    harvest_selectors_live,
    lifecycle_run,
    parse_pdd_to_ir,
    validate_project,
    verify_package_contents,
)

app = FastMCP("rpa-architect")

# ------------------------------------------------------------------
# Register tools
# ------------------------------------------------------------------


@app.tool()
async def tool_generate_from_pdd(
    pdd_path: str,
    output_dir: str,
    mode: str = "auto",
) -> dict:
    """Generate a complete UiPath project from a Process Design Document.

    Args:
        pdd_path: Path to the PDD file (PDF, DOCX, or text).
        output_dir: Directory to write generated project files.
        mode: Generation mode — auto, reframework, maestro, or hybrid.
    """
    return await generate_from_pdd(pdd_path, output_dir, mode)  # type: ignore[return-value]


@app.tool()
async def tool_parse_pdd_to_ir(pdd_path: str) -> dict:
    """Parse a Process Design Document into an Intermediate Representation.

    Args:
        pdd_path: Path to the PDD file.
    """
    return await parse_pdd_to_ir(pdd_path)  # type: ignore[return-value]


@app.tool()
async def tool_generate_from_ir(
    ir_json: str,
    output_dir: str,
    harvest_selectors: bool = False,
    harvest_headless: bool = True,
) -> dict:
    """Generate a UiPath project from a serialised ProcessIR JSON.

    Args:
        ir_json: JSON string of the ProcessIR.
        output_dir: Target output directory.
        harvest_selectors: Enable live browser selector harvesting.
        harvest_headless: Run harvest browser in headless mode.
    """
    return await generate_from_ir(ir_json, output_dir, harvest_selectors, harvest_headless)  # type: ignore[return-value]


@app.tool()
async def tool_validate_project(project_dir: str) -> dict:
    """Validate an existing UiPath project for correctness.

    Args:
        project_dir: Path to the project directory.
    """
    return await validate_project(project_dir)  # type: ignore[return-value]


@app.tool()
async def tool_generate_selectors(screenshots_dir: str, ir_json: str) -> dict:
    """Generate UI selectors from screenshots using IR context.

    Args:
        screenshots_dir: Directory containing application screenshots.
        ir_json: JSON string of the ProcessIR for context.
    """
    return await generate_selectors(screenshots_dir, ir_json)  # type: ignore[return-value]


@app.tool()
async def tool_build_knowledge(knowledge_dir: str) -> dict:
    """Build or rebuild the RAG knowledge index from documents.

    Args:
        knowledge_dir: Directory containing knowledge documents.
    """
    return await build_knowledge(knowledge_dir)  # type: ignore[return-value]


@app.tool()
async def tool_harvest_selectors_live(
    ir_json: str,
    system_name: str | None = None,
    headless: bool = True,
    timeout_ms: int = 30000,
) -> dict:
    """Harvest UI selectors from live browser sessions.

    Navigates to web system URLs found in the IR, discovers interactive
    elements, and returns production-ready UiPath selectors.

    Args:
        ir_json: JSON string of the ProcessIR.
        system_name: Optional specific system to harvest (all web systems if omitted).
        headless: Run browser in headless mode.
        timeout_ms: Navigation timeout in milliseconds.
    """
    return await harvest_selectors_live(ir_json, system_name, headless, timeout_ms)  # type: ignore[return-value]


@app.tool()
async def tool_lifecycle_run(
    source: str,
    source_type: str = "pdd",
    output_dir: str = "output",
    deploy_target: str = "Default",
    auto_monitor: bool = True,
    require_approval: bool = True,
) -> dict:
    """Run the full automation lifecycle: author, validate, deploy, monitor, fix.

    Args:
        source: Path to PDD, IR JSON, or natural language description.
        source_type: Input type — pdd, ir, or natural_language.
        output_dir: Output directory for generated project.
        deploy_target: Orchestrator folder for deployment.
        auto_monitor: Monitor after deployment.
        require_approval: Require human approval for fixes.
    """
    return await lifecycle_run(source, source_type, output_dir, deploy_target, auto_monitor, require_approval)  # type: ignore[return-value]


@app.tool()
async def tool_deploy_project(
    project_dir: str,
    folder: str = "Default",
) -> dict:
    """Deploy a generated UiPath project to Orchestrator.

    Args:
        project_dir: Path to the project directory.
        folder: Target Orchestrator folder.
    """
    return await deploy_project(project_dir, folder)  # type: ignore[return-value]


@app.tool()
async def tool_get_execution_logs(
    process_key: str,
    folder: str = "Default",
    hours: int = 24,
) -> dict:
    """Fetch execution monitoring report for a deployed process.

    Args:
        process_key: Process key to monitor.
        folder: Orchestrator folder.
        hours: Lookback window in hours.
    """
    return await get_execution_logs(process_key, folder, hours)  # type: ignore[return-value]


@app.tool()
async def tool_diagnose_failures(
    process_key: str,
    folder: str = "Default",
    hours: int = 24,
) -> dict:
    """Diagnose execution failures for a deployed process.

    Args:
        process_key: Process key to diagnose.
        folder: Orchestrator folder.
        hours: Lookback window in hours.
    """
    return await diagnose_failures(process_key, folder, hours)  # type: ignore[return-value]


@app.tool()
async def tool_generate_enterprise_reframework(
    namespace: str,
    output_dir: str,
    odoo_base_url: str = "http://localhost:8069",
) -> dict:
    """Generate the 16-file REFramework-as-C#-CodedWorkflow project.

    Produces the complete state machine pattern (Init → GetTransaction →
    Process → SetStatus → End) targetting the UiPath Community Cloud
    Linux serverless (.NET 8 Portable) runtime.

    Args:
        namespace: C# namespace for all generated types.
        output_dir: Directory to write the .cs files into.
        odoo_base_url: Base URL baked into ProcessInvoiceMain.cs at pack time.
    """
    return await generate_enterprise_reframework(namespace, output_dir, odoo_base_url)  # type: ignore[return-value]


@app.tool()
async def tool_verify_package_contents(nupkg_path: str) -> dict:
    """Run structural assertions against a UiPath .nupkg.

    Checks content-types layout, project.json Portable enum values,
    lib/net8.0/*.dll presence, and assembly metadata.

    Args:
        nupkg_path: Path to a .nupkg produced by `uipcli pack`.
    """
    return await verify_package_contents(nupkg_path)  # type: ignore[return-value]


@app.tool()
async def tool_get_community_cloud_gotchas() -> dict:
    """Return the structured list of UiPath Community Cloud brick walls.

    Useful for checking "can I do X on the Linux serverless runtime?"
    without loading a full skill file.
    """
    return await get_community_cloud_gotchas()  # type: ignore[return-value]


if __name__ == "__main__":
    app.run()
