"""Typer CLI for the Autonomous RPA Architect."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Optional

import typer
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from rpa_architect import __version__

app = typer.Typer(
    name="rpa-architect",
    help="Autonomous RPA Architect — Generate UiPath projects from Process Design Documents.",
    add_completion=True,
    no_args_is_help=True,
)
console = Console()


def _run_async(coro):  # type: ignore[no-untyped-def]
    """Run an async coroutine from sync CLI context."""
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = None
    if loop and loop.is_running():
        import concurrent.futures

        with concurrent.futures.ThreadPoolExecutor() as pool:
            return pool.submit(asyncio.run, coro).result()
    return asyncio.run(coro)


def _version_callback(value: bool) -> None:
    if value:
        console.print(f"rpa-architect {__version__}")
        raise typer.Exit()


@app.callback()
def main(
    version: Optional[bool] = typer.Option(
        None,
        "--version",
        "-V",
        help="Show version and exit.",
        callback=_version_callback,
        is_eager=True,
    ),
) -> None:
    """Autonomous RPA Architect CLI."""


@app.command()
def generate(
    pdd_path: Path = typer.Argument(..., help="Path to the Process Design Document."),
    output_dir: Path = typer.Option(
        Path("output"),
        "--output",
        "-o",
        help="Output directory for the generated project.",
    ),
    mode: str = typer.Option(
        "auto",
        "--mode",
        "-m",
        help="Generation mode: auto, reframework, maestro, hybrid.",
    ),
    validate: bool = typer.Option(
        True,
        "--validate/--no-validate",
        help="Run validation after generation.",
    ),
    package: bool = typer.Option(
        False,
        "--package",
        help="Package the project as .nupkg after generation.",
    ),
    provision: bool = typer.Option(
        False,
        "--provision",
        help="Provision Orchestrator resources (queues, assets).",
    ),
    harvest_selectors: bool = typer.Option(
        False,
        "--harvest-selectors",
        help="Enable live browser-based selector harvesting from system URLs.",
    ),
    harvest_headed: bool = typer.Option(
        False,
        "--harvest-headed",
        help="Run the harvest browser visibly (non-headless).",
    ),
) -> None:
    """Generate a UiPath project from a Process Design Document."""
    from rpa_architect.utils.logging import setup_logging

    setup_logging()

    if not pdd_path.exists():
        console.print(f"[red]Error:[/red] File not found: {pdd_path}")
        raise typer.Exit(code=1)

    console.print(
        Panel(
            f"Generating from [bold]{pdd_path.name}[/bold]\nMode: {mode} | Output: {output_dir}",
            title="RPA Architect",
        )
    )

    from rpa_architect.mcp_server.tools import generate_from_pdd as gen

    with console.status("Generating project..."):
        result = _run_async(gen(str(pdd_path), str(output_dir), mode))

    if result.get("success"):
        table = Table(title="Generated Files")
        table.add_column("File", style="green")
        for f in result.get("files", []):
            table.add_row(f)
        console.print(table)
        console.print("[green]Generation complete.[/green]")

        if validate:
            _do_validate(output_dir)
        if package:
            _do_package(output_dir)
    else:
        console.print("[red]Generation failed:[/red]")
        for err in result.get("errors", []):
            console.print(f"  - {err}")
        raise typer.Exit(code=1)


@app.command("parse-pdd")
def parse_pdd(
    pdd_path: Path = typer.Argument(..., help="Path to the PDD file."),
    output: Optional[Path] = typer.Option(
        None,
        "--output",
        "-o",
        help="Output file for the IR JSON. Prints to stdout if omitted.",
    ),
) -> None:
    """Parse a PDD into an Intermediate Representation (IR)."""
    from rpa_architect.utils.logging import setup_logging

    setup_logging()

    if not pdd_path.exists():
        console.print(f"[red]Error:[/red] File not found: {pdd_path}")
        raise typer.Exit(code=1)

    from rpa_architect.mcp_server.tools import parse_pdd_to_ir

    with console.status("Parsing PDD..."):
        result = _run_async(parse_pdd_to_ir(str(pdd_path)))

    if not result.get("success"):
        console.print("[red]Parse failed:[/red]")
        for err in result.get("errors", []):
            console.print(f"  - {err}")
        raise typer.Exit(code=1)

    ir_json = json.dumps(result["ir"], indent=2)

    if output:
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(ir_json, encoding="utf-8")
        console.print(f"[green]IR written to {output}[/green]")
    else:
        console.print(ir_json)


@app.command("generate-from-ir")
def generate_from_ir_cmd(
    ir_path: Path = typer.Argument(..., help="Path to the IR JSON file."),
    output_dir: Path = typer.Option(
        Path("output"),
        "--output",
        "-o",
        help="Output directory for the generated project.",
    ),
    harvest_selectors: bool = typer.Option(
        False,
        "--harvest-selectors",
        help="Enable live browser-based selector harvesting from system URLs.",
    ),
    harvest_headed: bool = typer.Option(
        False,
        "--harvest-headed",
        help="Run the harvest browser visibly (non-headless).",
    ),
) -> None:
    """Generate a UiPath project from an existing IR JSON file."""
    from rpa_architect.utils.logging import setup_logging

    setup_logging()

    if not ir_path.exists():
        console.print(f"[red]Error:[/red] File not found: {ir_path}")
        raise typer.Exit(code=1)

    ir_json = ir_path.read_text(encoding="utf-8")

    from rpa_architect.mcp_server.tools import generate_from_ir

    with console.status("Generating project from IR..."):
        result = _run_async(
            generate_from_ir(
                ir_json,
                str(output_dir),
                harvest_enabled=harvest_selectors,
                harvest_headless=not harvest_headed,
            )
        )

    if result.get("success"):
        console.print(f"[green]Project generated in {output_dir}[/green]")
        for f in result.get("files", []):
            console.print(f"  {f}")
    else:
        console.print("[red]Generation failed:[/red]")
        for err in result.get("errors", []):
            console.print(f"  - {err}")
        raise typer.Exit(code=1)


@app.command("validate")
def validate_cmd(
    project_dir: Path = typer.Argument(..., help="Path to the UiPath project directory."),
) -> None:
    """Validate an existing UiPath project."""
    _do_validate(project_dir)


@app.command("build-knowledge")
def build_knowledge_cmd(
    knowledge_dir: Path = typer.Argument(..., help="Directory containing knowledge documents."),
) -> None:
    """Build or rebuild the RAG knowledge index."""
    from rpa_architect.utils.logging import setup_logging

    setup_logging()

    if not knowledge_dir.is_dir():
        console.print(f"[red]Error:[/red] Not a directory: {knowledge_dir}")
        raise typer.Exit(code=1)

    from rpa_architect.mcp_server.tools import build_knowledge

    with console.status("Building knowledge index..."):
        result = _run_async(build_knowledge(str(knowledge_dir)))

    if result.get("success"):
        console.print(f"[green]Indexed {result.get('documents_indexed', 0)} documents.[/green]")
    else:
        console.print("[red]Knowledge build failed:[/red]")
        for err in result.get("errors", []):
            console.print(f"  - {err}")
        raise typer.Exit(code=1)


@app.command("serve-mcp")
def serve_mcp() -> None:
    """Start the MCP server for tool integration."""
    from rpa_architect.utils.logging import setup_logging

    setup_logging()

    console.print("[bold]Starting RPA Architect MCP server...[/bold]")
    try:
        from rpa_architect.mcp_server.server import app as mcp_app

        mcp_app.run()
    except KeyboardInterrupt:
        console.print("\n[yellow]MCP server stopped.[/yellow]")
    except Exception as exc:
        console.print(f"[red]MCP server error:[/red] {exc}")
        raise typer.Exit(code=1)


@app.command("upgrade")
def upgrade_cmd(
    project_dir: Path = typer.Argument(..., help="Path to the UiPath project directory."),
    target: str = typer.Option(
        "2025.10",
        "--target",
        "-t",
        help="Target UiPath Studio version.",
    ),
) -> None:
    """Upgrade an existing UiPath project to target package versions."""
    if not project_dir.is_dir():
        console.print(f"[red]Error:[/red] Not a directory: {project_dir}")
        raise typer.Exit(code=1)

    project_json_path = project_dir / "project.json"
    if not project_json_path.exists():
        console.print(f"[red]Error:[/red] No project.json found in {project_dir}")
        raise typer.Exit(code=1)

    from rpa_architect.nuget.known_packages import DEFAULT_VERSIONS, resolve_package_alias

    with console.status(f"Upgrading to {target}..."):
        data = json.loads(project_json_path.read_text(encoding="utf-8"))

        # Update tool/studio versions
        data["toolVersion"] = "25.10.0"
        data["studioVersion"] = "25.10.0.0"
        data.setdefault("targetFramework", "net6.0-windows")
        data.setdefault("runtimeOptions", {})["netVersion"] = "net6.0"

        # Update dependency versions
        updated_deps: dict[str, str] = {}
        for pkg_id, version_range in data.get("dependencies", {}).items():
            canonical = resolve_package_alias(pkg_id)
            if canonical in DEFAULT_VERSIONS:
                updated_deps[canonical] = f"[{DEFAULT_VERSIONS[canonical]}]"
            else:
                updated_deps[canonical] = version_range
        data["dependencies"] = updated_deps

        project_json_path.write_text(
            json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8"
        )

    console.print(f"[green]Upgraded {project_dir.name} to UiPath Studio {target}[/green]")
    table = Table(title="Updated Dependencies")
    table.add_column("Package", style="cyan")
    table.add_column("Version", style="green")
    for pkg, ver in sorted(data["dependencies"].items()):
        table.add_row(pkg, ver)
    console.print(table)


@app.command("lint-coded")
def lint_coded_cmd(
    project_dir: Path = typer.Argument(..., help="Path to the UiPath project directory."),
) -> None:
    """Lint C# coded workflow files for common issues."""
    if not project_dir.is_dir():
        console.print(f"[red]Error:[/red] Not a directory: {project_dir}")
        raise typer.Exit(code=1)

    from rpa_architect.xaml_lint.rules_coded import lint_coded_file

    cs_files = list(project_dir.rglob("*.cs"))
    if not cs_files:
        console.print("[yellow]No .cs files found.[/yellow]")
        return

    total_issues = 0
    for cs_file in cs_files:
        content = cs_file.read_text(encoding="utf-8")
        issues = lint_coded_file(content, str(cs_file.relative_to(project_dir)))
        if issues:
            for issue in issues:
                sev_color = {"error": "red", "warning": "yellow", "info": "blue"}.get(
                    issue.severity.value
                    if hasattr(issue.severity, "value")
                    else str(issue.severity),
                    "white",
                )
                console.print(
                    f"  [{sev_color}]{issue.rule_id}[/{sev_color}] "
                    f"{cs_file.relative_to(project_dir)}: {issue.message}"
                )
                total_issues += 1

    if total_issues == 0:
        console.print("[green]No coded workflow issues found.[/green]")
    else:
        console.print(f"\n[yellow]{total_issues} issue(s) found.[/yellow]")


@app.command("score-selectors")
def score_selectors_cmd(
    project_dir: Path = typer.Argument(..., help="Path to the UiPath project directory."),
) -> None:
    """Score UI selectors for robustness (0-100)."""
    if not project_dir.is_dir():
        console.print(f"[red]Error:[/red] Not a directory: {project_dir}")
        raise typer.Exit(code=1)

    from rpa_architect.validation.selector_scorer import (
        aggregate_score,
        score_selector,
    )

    # Collect selectors from .objects/ and XAML files
    selectors: dict[str, str] = {}

    objects_dir = project_dir / ".objects"
    if objects_dir.is_dir():
        for json_file in objects_dir.rglob("*.json"):
            if json_file.name == "descriptor.json":
                continue
            try:
                data = json.loads(json_file.read_text(encoding="utf-8"))
                if "selector" in data:
                    selectors[json_file.stem] = data["selector"]
                elif "selectorXml" in data:
                    selectors[json_file.stem] = data["selectorXml"]
                for elem in data.get("elements", []):
                    selectors[elem.get("name", json_file.stem)] = elem.get("selector", "")
            except (json.JSONDecodeError, KeyError):
                pass

    if not selectors:
        console.print("[yellow]No selectors found in project.[/yellow]")
        return

    scores = {name: score_selector(sel, name) for name, sel in selectors.items() if sel}
    avg = aggregate_score(scores)

    table = Table(title=f"Selector Quality Scores (Average: {avg}/100)")
    table.add_column("Element", style="cyan")
    table.add_column("Score", justify="right")
    table.add_column("Issues", style="yellow")

    for name, s in sorted(scores.items(), key=lambda x: x[1].score):
        score_color = "green" if s.score >= 70 else "yellow" if s.score >= 40 else "red"
        issues = ", ".join(s.penalties[:2]) if s.penalties else "none"
        table.add_row(name, f"[{score_color}]{s.score}[/{score_color}]", issues)

    console.print(table)


@app.command("lifecycle")
def lifecycle_cmd(
    pdd_path: Path = typer.Argument(..., help="Path to the PDD, IR JSON, or text file."),
    output_dir: Path = typer.Option(
        Path("output"),
        "--output",
        "-o",
        help="Output directory for the generated project.",
    ),
    deploy: bool = typer.Option(
        False,
        "--deploy",
        help="Deploy to Orchestrator after generation.",
    ),
    monitor: bool = typer.Option(
        False,
        "--monitor",
        help="Monitor the deployed process for failures.",
    ),
    folder: str = typer.Option(
        "Default",
        "--folder",
        "-f",
        help="Orchestrator folder for deployment.",
    ),
    auto_fix: bool = typer.Option(
        False,
        "--auto-fix",
        help="Automatically diagnose and fix failures (requires --monitor).",
    ),
    require_approval: bool = typer.Option(
        True,
        "--approval/--no-approval",
        help="Require human approval before applying fixes.",
    ),
    dry_run: bool = typer.Option(
        False,
        "--dry-run",
        help="Run the lifecycle without actually deploying.",
    ),
) -> None:
    """Run the full automation lifecycle: author, validate, deploy, monitor, fix."""
    from rpa_architect.utils.logging import setup_logging

    setup_logging()

    if not pdd_path.exists():
        console.print(f"[red]Error:[/red] File not found: {pdd_path}")
        raise typer.Exit(code=1)

    source_type = "pdd"
    if pdd_path.suffix == ".json":
        source_type = "ir"

    from rpa_architect.lifecycle.state import (
        AuthoringOutputs,
        LifecycleRequest,
        LifecycleState,
    )

    request = LifecycleRequest(
        source=str(pdd_path),
        source_type=source_type,
        deploy_target=folder,
        auto_monitor=monitor,
        require_approval_for_fixes=require_approval,
    )

    initial_state = LifecycleState(
        request=request,
        authoring=AuthoringOutputs(project_dir=str(output_dir)),
        max_iterations=3,
    )

    console.print(
        Panel(
            f"[bold]Lifecycle Agent[/bold]\n"
            f"Source: {pdd_path.name} ({source_type})\n"
            f"Deploy: {'yes' if deploy else 'no'} | Monitor: {'yes' if monitor else 'no'}\n"
            f"Auto-fix: {'yes' if auto_fix else 'no'} | Approval: {'required' if require_approval else 'auto'}",
            title="RPA Architect Lifecycle",
        )
    )

    if dry_run:
        console.print(
            "[yellow]Dry run — lifecycle graph would execute with the above configuration.[/yellow]"
        )
        return

    from rpa_architect.lifecycle.agent import create_lifecycle_graph

    graph = create_lifecycle_graph()

    with console.status("Running lifecycle agent..."):
        result = _run_async(graph.ainvoke(initial_state))

    # Display results
    if isinstance(result, dict):
        result_state = result
    else:
        result_state = result.model_dump() if hasattr(result, "model_dump") else {}

    phase = result_state.get("phase", "unknown")
    errors = result_state.get("errors", [])
    deployment = result_state.get("deployment")
    history = result_state.get("history", [])

    if errors:
        console.print(f"[yellow]Lifecycle completed with errors (phase: {phase}):[/yellow]")
        for err in errors:
            console.print(f"  - {err}")
    else:
        console.print(f"[green]Lifecycle completed successfully (phase: {phase})[/green]")

    if deployment:
        console.print(
            f"\n[bold]Deployment:[/bold] {deployment.get('process_key', 'N/A')} "
            f"v{deployment.get('version', '?')} → {deployment.get('folder', '?')}"
        )

    if history:
        table = Table(title="Lifecycle Events")
        table.add_column("Phase", style="cyan")
        table.add_column("Event", style="green")
        table.add_column("Detail")
        for event in history[-10:]:
            if isinstance(event, dict):
                table.add_row(
                    event.get("phase", ""),
                    event.get("event_type", ""),
                    event.get("detail", "")[:80],
                )
        console.print(table)


@app.command("lifecycle-status")
def lifecycle_status_cmd(
    process_key: str = typer.Argument(..., help="Process key to check."),
    folder: str = typer.Option("Default", "--folder", "-f", help="Orchestrator folder."),
    hours: int = typer.Option(24, "--hours", "-h", help="Lookback window in hours."),
) -> None:
    """Check monitoring status of a deployed process."""
    from rpa_architect.utils.logging import setup_logging

    setup_logging()

    from rpa_architect.lifecycle.monitor import collect_monitoring_report

    with console.status(f"Monitoring {process_key}..."):
        report = _run_async(collect_monitoring_report(process_key, folder, lookback_hours=hours))

    table = Table(title=f"Monitoring: {process_key}")
    table.add_column("Metric", style="cyan")
    table.add_column("Value", justify="right")
    table.add_row("Total Jobs", str(report.total_jobs))
    table.add_row("Successful", f"[green]{report.successful}[/green]")
    table.add_row("Faulted", f"[red]{report.faulted}[/red]" if report.faulted else "0")
    table.add_row("Success Rate", f"{report.success_rate:.1%}")
    table.add_row("Avg Duration", f"{report.avg_duration_seconds:.1f}s")
    console.print(table)

    if report.errors_by_type:
        err_table = Table(title="Error Distribution")
        err_table.add_column("Error Type", style="yellow")
        err_table.add_column("Count", justify="right")
        for err_type, count in sorted(report.errors_by_type.items(), key=lambda x: -x[1]):
            err_table.add_row(err_type, str(count))
        console.print(err_table)


@app.command("scaffold-agent")
def scaffold_agent_cmd(
    project_dir: Path = typer.Argument(..., help="Output directory for agent scaffold."),
    name: str = typer.Option("my_agent", "--name", "-n", help="Agent process name."),
    description: str = typer.Option("", "--description", "-d", help="Agent description."),
) -> None:
    """Generate a UiPath Python SDK agent scaffold."""
    from rpa_architect.assembler.agent_scaffold_gen import generate_agent_scaffold

    files = generate_agent_scaffold(
        process_name=name,
        description=description or f"UiPath agent: {name}",
    )

    project_dir.mkdir(parents=True, exist_ok=True)
    for file_path, content in files.items():
        full_path = project_dir / file_path
        full_path.parent.mkdir(parents=True, exist_ok=True)
        full_path.write_text(content, encoding="utf-8")
        console.print(f"  [green]+[/green] {file_path}")

    console.print(f"\n[green]Agent scaffold created in {project_dir}[/green]")
    console.print("Next steps:")
    console.print("  1. cd " + str(project_dir))
    console.print("  2. pip install uipath")
    console.print("  3. uipath init")
    console.print("  4. uipath run main '{}'")


# ------------------------------------------------------------------
# Internal helpers
# ------------------------------------------------------------------


def _do_validate(project_dir: Path) -> None:
    """Run project validation and print results."""
    from rpa_architect.mcp_server.tools import validate_project

    with console.status("Validating project..."):
        result = _run_async(validate_project(str(project_dir)))

    if result.get("valid"):
        console.print("[green]Validation passed.[/green]")
    else:
        console.print("[yellow]Validation issues:[/yellow]")
        for issue in result.get("issues", []):
            console.print(f"  - {issue}")


def _do_package(project_dir: Path) -> None:
    """Package the project using the UiPath CLI."""
    from rpa_architect.platform.agent_deployer import deploy_as_agent

    with console.status("Packaging project..."):
        result = _run_async(deploy_as_agent(project_dir))

    if result.success:
        console.print(f"[green]Package created:[/green] {result.package_id}")
    else:
        console.print("[red]Packaging failed:[/red]")
        for err in result.errors:
            console.print(f"  - {err}")
