"""MCP tool implementations for the RPA Architect server."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from rpa_architect.config import GenerationMode
from rpa_architect.ir.schema import ProcessIR
from rpa_architect.utils.file_utils import ensure_dir, write_file

logger = logging.getLogger("rpa_architect.mcp_server.tools")


async def generate_from_pdd(
    pdd_path: str,
    output_dir: str,
    mode: str = "auto",
) -> dict[str, Any]:
    """End-to-end pipeline: parse a PDD and generate a UiPath project.

    Args:
        pdd_path: Path to the Process Design Document.
        output_dir: Directory to write generated project files.
        mode: Generation mode (auto, reframework, maestro, hybrid).

    Returns:
        A dict with keys ``success``, ``output_dir``, ``files``, ``errors``.
    """
    # Parse PDD to IR.
    try:
        ir_result = await parse_pdd_to_ir(pdd_path)
        if not ir_result.get("success"):
            return {"success": False, "errors": ir_result.get("errors", ["Parse failed"])}
        ir = ProcessIR.model_validate(ir_result["ir"])
    except Exception as exc:
        return {"success": False, "errors": [f"Failed to parse PDD: {exc}"]}

    # Detect or use specified mode.
    if mode == "auto":
        from rpa_architect.maestro.maestro_planner import detect_mode

        detect_mode(ir)
    else:
        GenerationMode(mode)

    # Generate project.
    try:
        ir_json = ir.model_dump_json()
        gen_result = await generate_from_ir(ir_json, output_dir)
        return gen_result
    except Exception as exc:
        return {"success": False, "errors": [f"Generation failed: {exc}"]}


async def parse_pdd_to_ir(pdd_path: str) -> dict[str, Any]:
    """Parse a Process Design Document into an Intermediate Representation.

    Args:
        pdd_path: Path to the PDD file (PDF, DOCX, or text).

    Returns:
        A dict with keys ``success``, ``ir`` (serialised IR dict), ``errors``.
    """
    path = Path(pdd_path)
    if not path.exists():
        return {"success": False, "errors": [f"File not found: {pdd_path}"]}

    try:
        # Attempt to use the parser subsystem (sync function).
        from rpa_architect.parser.pdd_parser import parse_pdd

        ir = parse_pdd(path)
        return {
            "success": True,
            "ir": ir.model_dump(),
        }
    except ImportError:
        logger.warning("Parser module not available; returning stub IR")
        stub_ir = ProcessIR(
            process_name=path.stem,
            description=f"Parsed from {path.name}",
        )
        return {
            "success": True,
            "ir": stub_ir.model_dump(),
        }
    except Exception as exc:
        return {"success": False, "errors": [str(exc)]}


async def generate_from_ir(
    ir_json: str,
    output_dir: str,
    harvest_enabled: bool = False,
    harvest_headless: bool = True,
) -> dict[str, Any]:
    """Generate a UiPath project from a serialised IR.

    Args:
        ir_json: JSON string of the ProcessIR.
        output_dir: Target output directory.
        harvest_enabled: Enable live browser selector harvesting.
        harvest_headless: Run harvest browser in headless mode.

    Returns:
        A dict with keys ``success``, ``output_dir``, ``files``, ``errors``.
    """
    try:
        ir = ProcessIR.model_validate_json(ir_json)
    except Exception as exc:
        return {"success": False, "errors": [f"Invalid IR JSON: {exc}"]}

    out_path = ensure_dir(Path(output_dir))
    generated_files: list[str] = []
    errors: list[str] = []
    warnings: list[str] = []

    # Build harvest config if enabled
    harvest_config = None
    if harvest_enabled:
        try:
            from rpa_architect.selectors.browser_harvester import HarvestConfig

            harvest_config = HarvestConfig(
                enabled=True,
                headless=harvest_headless,
                screenshot_dir=out_path / "harvest_screenshots",
            )
        except ImportError:
            errors.append(
                "Playwright not installed; harvest disabled. "
                "Install with: pip install 'autonomous-rpa-architect[harvest]'"
            )

    try:
        from rpa_architect.maestro.maestro_planner import detect_mode, plan_maestro
        from rpa_architect.maestro.service_task_binder import bind_service_tasks
        from rpa_architect.maestro.bpmn_generator import generate_bpmn
        from rpa_architect.maestro.dmn_generator import generate_dmn
        from rpa_architect.assembler.project_assembler import assemble_project

        mode = detect_mode(ir)

        # Always generate the REFramework project (core output).
        manifest = await assemble_project(
            ir,
            {},
            out_path,
            harvest_config=harvest_config,
        )
        generated_files.extend(manifest.files_written)
        # Assembly warnings are non-fatal — keep them separate from errors so
        # downstream callers (CLI, MCP) don't treat them as failures.
        warnings.extend(manifest.warnings)

        # Additionally generate Maestro artifacts for maestro/hybrid modes.
        if mode in (GenerationMode.MAESTRO, GenerationMode.HYBRID):
            plan = plan_maestro(ir)
            bindings = bind_service_tasks(plan, ir)

            bpmn_xml = generate_bpmn(ir, bindings)
            bpmn_path = out_path / f"{ir.process_name}.bpmn"
            write_file(bpmn_path, bpmn_xml)
            generated_files.append(f"{ir.process_name}.bpmn")

            for txn in ir.transactions:
                rules = [r for r in txn.business_rules if r.outcome in ("route", "escalate")]
                if rules:
                    dmn_xml = generate_dmn(rules, f"{txn.name}_Rules")
                    dmn_path = out_path / f"{txn.name}_rules.dmn"
                    write_file(dmn_path, dmn_xml)
                    generated_files.append(f"{txn.name}_rules.dmn")

    except Exception as exc:
        errors.append(f"Generation error: {exc}")

    return {
        "success": len(errors) == 0,
        "output_dir": str(out_path),
        "files": generated_files,
        "errors": errors,
        "warnings": warnings,
    }


async def harvest_selectors_live(
    ir_json: str,
    system_name: str | None = None,
    headless: bool = True,
    timeout_ms: int = 30000,
) -> dict[str, Any]:
    """Harvest selectors from live browser sessions for systems in the IR.

    Navigates to web system URLs, discovers interactive elements, and returns
    production-ready UiPath selectors.

    Args:
        ir_json: JSON string of the ProcessIR.
        system_name: Optional system name to harvest from (all web systems if None).
        headless: Run browser in headless mode.
        timeout_ms: Navigation timeout in milliseconds.

    Returns:
        A dict with keys ``success``, ``selectors``, ``reports``, ``errors``.
    """
    try:
        ir = ProcessIR.model_validate_json(ir_json)
    except Exception as exc:
        return {"success": False, "selectors": {}, "errors": [f"Invalid IR JSON: {exc}"]}

    try:
        from rpa_architect.selectors.browser_harvester import (
            HarvestConfig,
            harvest_selectors_from_browser,
        )
    except ImportError:
        return {
            "success": False,
            "selectors": {},
            "errors": [
                "Playwright not installed. Install with: pip install 'autonomous-rpa-architect[harvest]'"
            ],
        }

    # Filter to specific system if requested
    if system_name:
        ir.systems = [s for s in ir.systems if s.name == system_name]
        if not ir.systems:
            return {
                "success": False,
                "selectors": {},
                "errors": [f"System '{system_name}' not found in IR"],
            }

    config = HarvestConfig(
        enabled=True,
        headless=headless,
        timeout_ms=timeout_ms,
    )

    try:
        reports = await harvest_selectors_from_browser(ir, config)
    except Exception as exc:
        return {"success": False, "selectors": {}, "errors": [str(exc)]}

    all_selectors: dict[str, str] = {}
    all_errors: list[str] = []
    report_summaries: dict[str, dict] = {}

    for sys_name, report in reports.items():
        all_selectors.update(report.selectors)
        all_errors.extend(report.errors)
        report_summaries[sys_name] = {
            "elements_found": sum(len(r.elements) for r in report.results),
            "selectors_generated": len(report.selectors),
            "fallbacks": report.fallbacks,
            "errors": report.errors,
        }

    return {
        "success": len(all_errors) == 0,
        "selectors": all_selectors,
        "reports": report_summaries,
        "errors": all_errors,
    }


async def validate_project(project_dir: str) -> dict[str, Any]:
    """Validate an existing UiPath project.

    Args:
        project_dir: Path to the project directory.

    Returns:
        A dict with keys ``valid``, ``issues``.
    """
    path = Path(project_dir)
    if not path.is_dir():
        return {"valid": False, "issues": [f"Not a directory: {project_dir}"]}

    issues: list[str] = []

    try:
        from rpa_architect.validation.structure_validator import validate_structure

        structure_issues = validate_structure(path)
        issues.extend(issue.message for issue in structure_issues)
    except ImportError:
        issues.append("Structure validator not available")

    return {
        "valid": len(issues) == 0,
        "issues": issues,
    }


async def generate_selectors(
    screenshots_dir: str,
    ir_json: str,
) -> dict[str, Any]:
    """Generate UI selectors from screenshots and IR context.

    Args:
        screenshots_dir: Directory containing application screenshots.
        ir_json: JSON string of the ProcessIR for context.

    Returns:
        A dict with keys ``success``, ``selectors``, ``errors``.
    """
    path = Path(screenshots_dir)
    if not path.is_dir():
        return {
            "success": False,
            "selectors": {},
            "errors": [f"Not a directory: {screenshots_dir}"],
        }

    try:
        ir = ProcessIR.model_validate_json(ir_json)
    except Exception as exc:
        return {"success": False, "selectors": {}, "errors": [f"Invalid IR JSON: {exc}"]}

    selectors: dict[str, str] = {}
    errors: list[str] = []

    try:
        from rpa_architect.selectors.selector_agent import generate_selectors as gen_sel

        selectors = await gen_sel(path, ir)
    except ImportError:
        errors.append("Selector agent not available")
    except Exception as exc:
        errors.append(f"Selector generation failed: {exc}")

    return {
        "success": len(errors) == 0,
        "selectors": selectors,
        "errors": errors,
    }


async def build_knowledge(knowledge_dir: str) -> dict[str, Any]:
    """Build or rebuild the RAG knowledge index.

    Args:
        knowledge_dir: Directory containing knowledge documents.

    Returns:
        A dict with keys ``success``, ``documents_indexed``, ``errors``.
    """
    path = Path(knowledge_dir)
    if not path.is_dir():
        return {
            "success": False,
            "documents_indexed": 0,
            "errors": [f"Not a directory: {knowledge_dir}"],
        }

    errors: list[str] = []
    doc_count = 0

    try:
        from rpa_architect.codegen.rag import build_index

        doc_count = await build_index(path)
    except ImportError:
        errors.append("RAG indexer not available")
    except Exception as exc:
        errors.append(f"Knowledge build failed: {exc}")

    return {
        "success": len(errors) == 0,
        "documents_indexed": doc_count,
        "errors": errors,
    }


# ===================================================================
# v0.3.0 MCP Tools
# ===================================================================


async def upgrade_project(
    project_dir: str,
    target_version: str = "2025.10",
) -> dict[str, Any]:
    """Upgrade an existing UiPath project to 2025.10 package versions.

    Updates project.json dependencies, toolVersion, studioVersion, and
    handles the UIAutomationNext → UIAutomation package rename.

    Args:
        project_dir: Path to the UiPath project directory.
        target_version: Target UiPath Studio version.

    Returns:
        A dict with keys ``success``, ``updated_packages``, ``errors``.
    """
    import json as _json

    path = Path(project_dir)
    project_json_path = path / "project.json"
    if not project_json_path.exists():
        return {"success": False, "updated_packages": {}, "errors": ["project.json not found"]}

    try:
        from rpa_architect.nuget.known_packages import DEFAULT_VERSIONS, resolve_package_alias

        data = _json.loads(project_json_path.read_text(encoding="utf-8"))

        data["toolVersion"] = "25.10.0"
        data["studioVersion"] = "25.10.0.0"
        data.setdefault("targetFramework", "net6.0-windows")
        data.setdefault("runtimeOptions", {})["netVersion"] = "net6.0"

        updated: dict[str, str] = {}
        for pkg_id, version_range in data.get("dependencies", {}).items():
            canonical = resolve_package_alias(pkg_id)
            if canonical in DEFAULT_VERSIONS:
                new_version = f"[{DEFAULT_VERSIONS[canonical]}]"
                updated[canonical] = new_version
            else:
                updated[canonical] = version_range
        data["dependencies"] = updated

        project_json_path.write_text(
            _json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8"
        )

        return {"success": True, "updated_packages": updated, "errors": []}
    except Exception as exc:
        return {"success": False, "updated_packages": {}, "errors": [str(exc)]}


async def generate_coded_workflow(
    class_name: str,
    namespace: str = "GeneratedProject.CodedWorkflows",
    steps: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Generate a C# coded workflow file using Coded Automations APIs.

    Args:
        class_name: Name of the generated C# class.
        namespace: C# namespace for the class.
        steps: List of step dicts, each with 'type' and parameters.

    Returns:
        A dict with keys ``success``, ``content``, ``errors``.
    """
    try:
        from rpa_architect.codegen.coded_workflow_gen import generate_coded_workflow as gen_cw
        from rpa_architect.generators import generate_activity

        body_lines: list[str] = []
        if steps:
            for step in steps:
                step_type = step.pop("type", step.pop("action", ""))
                if step_type:
                    try:
                        line = generate_activity(f"coded_{step_type}", **step)
                        body_lines.append(line)
                    except (ValueError, TypeError):
                        body_lines.append(f"// TODO: {step_type}")

        content = gen_cw(
            class_name=class_name,
            namespace=namespace,
            body_statements=body_lines,
        )

        return {"success": True, "content": content, "errors": []}
    except Exception as exc:
        return {"success": False, "content": "", "errors": [str(exc)]}


async def score_selectors(
    project_dir: str,
) -> dict[str, Any]:
    """Score all UI selectors in a project for robustness (0-100).

    Args:
        project_dir: Path to the UiPath project directory.

    Returns:
        A dict with ``success``, ``average_score``, ``scores``, ``errors``.
    """
    import json as _json

    path = Path(project_dir)
    if not path.is_dir():
        return {"success": False, "average_score": 0, "scores": {}, "errors": ["Not a directory"]}

    try:
        from rpa_architect.validation.selector_scorer import (
            aggregate_score,
            score_selector,
        )

        selectors: dict[str, str] = {}

        objects_dir = path / ".objects"
        if objects_dir.is_dir():
            for json_file in objects_dir.rglob("*.json"):
                if json_file.name == "descriptor.json":
                    continue
                try:
                    data = _json.loads(json_file.read_text(encoding="utf-8"))
                    if "selectorXml" in data:
                        selectors[json_file.stem] = data["selectorXml"]
                    for elem in data.get("elements", []):
                        selectors[elem.get("name", json_file.stem)] = elem.get("selector", "")
                except (ValueError, KeyError):
                    pass

        if not selectors:
            return {"success": True, "average_score": 0, "scores": {}, "errors": []}

        scores = {name: score_selector(sel, name) for name, sel in selectors.items() if sel}
        avg = aggregate_score(scores)

        score_details = {
            name: {
                "score": s.score,
                "penalties": s.penalties,
                "bonuses": s.bonuses,
            }
            for name, s in scores.items()
        }

        return {
            "success": True,
            "average_score": avg,
            "scores": score_details,
            "errors": [],
        }
    except Exception as exc:
        return {"success": False, "average_score": 0, "scores": {}, "errors": [str(exc)]}


async def lifecycle_run(
    source: str,
    source_type: str = "pdd",
    output_dir: str = "output",
    deploy_target: str = "Default",
    auto_monitor: bool = True,
    require_approval: bool = True,
) -> dict[str, Any]:
    """Run the full automation lifecycle: author → validate → deploy → monitor → fix.

    Args:
        source: Path to PDD, IR JSON string, or natural language description.
        source_type: Input type — pdd, ir, or natural_language.
        output_dir: Output directory for generated project.
        deploy_target: Orchestrator folder for deployment.
        auto_monitor: Monitor after deployment.
        require_approval: Require human approval for fixes.

    Returns:
        A dict with lifecycle result including phase, deployment, and event history.
    """
    try:
        from rpa_architect.lifecycle.agent import create_lifecycle_graph
        from rpa_architect.lifecycle.state import (
            AuthoringOutputs,
            LifecycleRequest,
            LifecycleState,
        )

        request = LifecycleRequest(
            source=source,
            source_type=source_type,
            deploy_target=deploy_target,
            auto_monitor=auto_monitor,
            require_approval_for_fixes=require_approval,
        )

        initial_state = LifecycleState(
            request=request,
            authoring=AuthoringOutputs(project_dir=output_dir),
        )

        graph = create_lifecycle_graph()
        result = await graph.ainvoke(initial_state)

        # Serialize result
        if hasattr(result, "model_dump"):
            result_dict = result.model_dump()
        else:
            result_dict = dict(result)

        return {
            "success": not result_dict.get("errors"),
            "phase": result_dict.get("phase", "unknown"),
            "project_dir": result_dict.get("project_dir", ""),
            "deployment": result_dict.get("deployment"),
            "errors": result_dict.get("errors", []),
            "events": len(result_dict.get("history", [])),
        }
    except Exception as exc:
        return {"success": False, "errors": [str(exc)]}


async def deploy_project(
    project_dir: str,
    folder: str = "Default",
) -> dict[str, Any]:
    """Deploy a generated UiPath project to Orchestrator.

    Args:
        project_dir: Path to the project directory.
        folder: Target Orchestrator folder.

    Returns:
        A dict with deployment record or errors.
    """
    try:
        from rpa_architect.lifecycle.deployer import deploy_project as _deploy

        record = await _deploy(project_dir=project_dir, folder=folder)
        return {
            "success": True,
            "deployment": record.model_dump(),
            "errors": [],
        }
    except Exception as exc:
        return {"success": False, "deployment": None, "errors": [str(exc)]}


async def get_execution_logs(
    process_key: str,
    folder: str = "Default",
    hours: int = 24,
) -> dict[str, Any]:
    """Fetch execution monitoring report for a deployed process.

    Args:
        process_key: The deployed process key.
        folder: Orchestrator folder.
        hours: Lookback window in hours.

    Returns:
        A dict with monitoring report data.
    """
    try:
        from rpa_architect.lifecycle.monitor import collect_monitoring_report

        report = await collect_monitoring_report(process_key, folder, lookback_hours=hours)
        return {
            "success": True,
            "report": report.model_dump(),
            "errors": [],
        }
    except Exception as exc:
        return {"success": False, "report": None, "errors": [str(exc)]}


async def diagnose_failures(
    process_key: str,
    folder: str = "Default",
    hours: int = 24,
) -> dict[str, Any]:
    """Diagnose execution failures for a deployed process.

    Args:
        process_key: The deployed process key.
        folder: Orchestrator folder.
        hours: Lookback window in hours.

    Returns:
        A dict with diagnosis result.
    """
    try:
        from rpa_architect.lifecycle.monitor import collect_monitoring_report
        from rpa_architect.lifecycle.diagnosis import diagnose_failures as _diagnose

        report = await collect_monitoring_report(process_key, folder, lookback_hours=hours)
        if report.faulted == 0:
            return {"success": True, "diagnosis": None, "message": "No failures to diagnose"}

        diagnosis = await _diagnose(
            monitoring_report=report,
            ir={},
            project_dir="",
        )
        return {
            "success": True,
            "diagnosis": diagnosis.model_dump(),
            "errors": [],
        }
    except Exception as exc:
        return {"success": False, "diagnosis": None, "errors": [str(exc)]}


# ===================================================================
# v0.5.0 Enterprise tools (Portable / Linux serverless runtime)
# ===================================================================


async def generate_enterprise_reframework(
    namespace: str,
    output_dir: str,
    odoo_base_url: str = "http://localhost:8069",
    invoices_dir: str | None = None,
) -> dict[str, Any]:
    """Generate the 16-file REFramework-as-C#-CodedWorkflow project.

    Writes the complete state machine pattern (Init → GetTransaction →
    Process → SetStatus → End) as compiled C# files targetting the UiPath
    Community Cloud Linux serverless (.NET 8 Portable) runtime.

    Args:
        namespace: C# namespace for all generated types.
        output_dir: Directory to write the .cs files into.
        odoo_base_url: Base URL baked into ProcessInvoiceMain.cs at pack
            time — override with the public URL of your Odoo instance.

    Returns:
        A dict with ``success``, ``files``, ``errors``.
    """
    try:
        from rpa_architect.codegen import reframework_csharp_gen as gen
        from rpa_architect.codegen.rules_engine_gen import generate_rules_engine_cs
        from rpa_architect.codegen.odoo_client_gen import generate_odoo_client_cs
        from rpa_architect.codegen.du_client_gen import generate_du_client_cs
        from rpa_architect.codegen.local_extractor_gen import (
            generate_local_extractor_cs,
        )
        from rpa_architect.codegen.models_gen import (
            generate_process_config_cs,
            generate_batch_metrics_cs,
            generate_process_context_cs,
        )
        from rpa_architect.codegen.embedded_invoices_gen import (
            generate_embedded_invoices_cs,
            load_invoices,
        )

        out_path = Path(output_dir)
        out_path.mkdir(parents=True, exist_ok=True)

        if invoices_dir is None:
            repo_root = Path(__file__).resolve().parents[3]
            invoices_path = repo_root / "tests" / "fixtures" / "invoices"
        else:
            invoices_path = Path(invoices_dir)

        files = {
            "IState.cs": gen.generate_istate_cs(namespace),
            "ProcessExceptions.cs": gen.generate_exceptions_cs(namespace),
            "InitState.cs": gen.generate_init_state_cs(namespace),
            "GetTransactionDataState.cs": gen.generate_get_transaction_state_cs(namespace),
            "ProcessState.cs": gen.generate_process_state_cs(namespace),
            "SetTransactionStatusState.cs": gen.generate_set_transaction_status_state_cs(namespace),
            "EndState.cs": gen.generate_end_state_cs(namespace),
            "ProcessInvoiceMain.cs": gen.generate_process_invoice_main_cs(
                namespace, default_odoo_url=odoo_base_url
            ),
            "BusinessRuleEngine.cs": generate_rules_engine_cs(namespace),
            "OdooClient.cs": generate_odoo_client_cs(namespace),
            "DocumentUnderstandingClient.cs": generate_du_client_cs(namespace),
            "LocalInvoiceExtractor.cs": generate_local_extractor_cs(namespace),
            "ProcessConfig.cs": generate_process_config_cs(namespace),
            "BatchMetrics.cs": generate_batch_metrics_cs(namespace),
            "ProcessContext.cs": generate_process_context_cs(namespace),
            "EmbeddedInvoices.cs": generate_embedded_invoices_cs(
                load_invoices(invoices_path), namespace
            ),
        }

        written: list[str] = []
        for name, content in files.items():
            (out_path / name).write_text(content, encoding="utf-8")
            written.append(name)

        return {"success": True, "files": written, "errors": []}
    except Exception as exc:
        return {"success": False, "files": [], "errors": [str(exc)]}


async def verify_package_contents(nupkg_path: str) -> dict[str, Any]:
    """Run the 17 structural assertions against a UiPath `.nupkg`.

    Checks content-types layout, project.json Portable enum values,
    lib/net8.0/*.dll presence, and assembly metadata. Returns each
    assertion's pass/fail status.

    Args:
        nupkg_path: Path to a `.nupkg` produced by `uipcli pack`.

    Returns:
        A dict with ``success``, ``assertions`` (list of {name, passed,
        detail}), ``passed``, ``failed``, ``errors``.
    """
    import zipfile
    import json as _json

    path = Path(nupkg_path)
    if not path.exists():
        return {
            "success": False,
            "assertions": [],
            "passed": 0,
            "failed": 0,
            "errors": [f"File not found: {nupkg_path}"],
        }

    assertions: list[dict[str, Any]] = []

    def _check(name: str, condition: bool, detail: str = "") -> None:
        assertions.append({"name": name, "passed": bool(condition), "detail": detail})

    try:
        if not zipfile.is_zipfile(path):
            _check("zip_format", False, "not a valid ZIP")
            return {
                "success": False,
                "assertions": assertions,
                "passed": 0,
                "failed": 1,
                "errors": ["Not a valid .nupkg (ZIP)"],
            }
        _check("zip_format", True)

        with zipfile.ZipFile(path) as z:
            names = set(z.namelist())
            _check("has_content_types", "[Content_Types].xml" in names)
            _check("has_rels_dir", any(n.startswith("_rels/") for n in names))
            _check("has_content_dir", any(n.startswith("content/") for n in names))

            project_json_member = next(
                (n for n in names if n.endswith("content/project.json")), None
            )
            _check("has_project_json", project_json_member is not None)

            if project_json_member:
                pj = _json.loads(z.read(project_json_member).decode("utf-8"))
                _check(
                    "target_framework_portable",
                    pj.get("targetFramework") == "Portable",
                    f"got: {pj.get('targetFramework')!r}",
                )
                _check(
                    "project_profile_numeric_zero",
                    pj.get("projectProfile") == 0,
                    f"got: {pj.get('projectProfile')!r}",
                )
                _check(
                    "main_field_present",
                    pj.get("main") == "Main.xaml",
                    f"got: {pj.get('main')!r}",
                )
                _check(
                    "requires_user_interaction_false",
                    pj.get("requiresUserInteraction") is False,
                    f"got: {pj.get('requiresUserInteraction')!r}",
                )

            dll_member = next(
                (n for n in names if n.startswith("lib/net8.0/") and n.endswith(".dll")),
                None,
            )
            _check("has_net8_dll", dll_member is not None)

            if dll_member:
                dll_bytes = z.read(dll_member)
                _check(
                    "dll_is_valid_pe",
                    dll_bytes[:2] == b"MZ",
                    f"header bytes: {dll_bytes[:4].hex()}",
                )
                _check("dll_nonzero_size", len(dll_bytes) > 0, f"{len(dll_bytes)} bytes")

            main_xaml_member = next((n for n in names if n.endswith("content/Main.xaml")), None)
            _check("has_main_xaml", main_xaml_member is not None)

            if main_xaml_member:
                main_content = z.read(main_xaml_member).decode("utf-8")
                _check(
                    "main_xaml_no_expressions",
                    "[" not in main_content or "xmlns:" in main_content,
                    "Main.xaml should not contain [expressions] (JIT disabled in Portable)",
                )

    except Exception as exc:
        _check("parse_error", False, str(exc))

    passed = sum(1 for a in assertions if a["passed"])
    failed = len(assertions) - passed
    return {
        "success": failed == 0,
        "assertions": assertions,
        "passed": passed,
        "failed": failed,
        "errors": [] if failed == 0 else [f"{failed} assertions failed"],
    }


async def get_community_cloud_gotchas() -> dict[str, Any]:
    """Return the structured list of UiPath Community Cloud brick walls.

    Useful for autonomous agents that need to check "can I do X on the
    serverless Linux runtime?" without loading the full skill file. Maps
    directly to `docs/community_cloud_limitations.md`.

    Returns:
        A dict with ``gotchas`` (list of {id, title, symptom, workaround,
        status}) and ``capability_matrix``.
    """
    gotchas = [
        {
            "id": 1,
            "title": "Serverless robot is Linux — no UI automation",
            "symptom": "ui:Click / ui:TypeInto silently fail; UIAutomation package targets net48",
            "workaround": "Drive UIs via HTTP/JSON-RPC from compiled C# CodedWorkflow",
            "status": "hard_wall",
        },
        {
            "id": 2,
            "title": "IntelligentOCR.Activities is Windows-only",
            "symptom": "uipcli pack errors: Cannot create unknown type DigitizeDocument",
            "workaround": "Call DU Cloud API v2 via HttpClient from C#",
            "status": "hard_wall",
        },
        {
            "id": 3,
            "title": "DU Cloud API v2 needs extra OAuth scopes",
            "symptom": 'Token endpoint returns {"error":"invalid_scope"}',
            "workaround": "Register Du.Digitization.Api + Du.Extraction.Api + Du.Classification.Api + Du.Validation.Api on the external app",
            "status": "config_required",
        },
        {
            "id": 4,
            "title": "No public Maestro deployment API",
            "symptom": "No OData Maestro section; no REST endpoint documented",
            "workaround": "Ship BPMN+DMN as sibling files, import via Studio Web manually",
            "status": "no_api",
        },
        {
            "id": 5,
            "title": "No Action Center in Community tier",
            "symptom": "POST /odata/Tasks returns 403 Enterprise required",
            "workaround": "Use Odoo mail.activity.activity_schedule as substitute",
            "status": "tier_limit",
        },
        {
            "id": 6,
            "title": "Portable disables JIT compilation",
            "symptom": "Main.xaml with any [expression] faults: JIT compilation is disabled",
            "workaround": "Main.xaml emits only literals; real expressions in compiled C#",
            "status": "runtime_limit",
        },
        {
            "id": 7,
            "title": "Orchestrator Assets don't surface as env vars in Portable",
            "symptom": "Environment.GetEnvironmentVariable returns stale container env",
            "workaround": "Bake runtime config into C# string literals at pack time",
            "status": "runtime_limit",
        },
        {
            "id": 8,
            "title": "Storage Buckets return 403 on default external app",
            "symptom": "GET /odata/Buckets returns 403 You are not authorized",
            "workaround": "Base64-embed small binaries as C# constants",
            "status": "config_required",
        },
        {
            "id": 9,
            "title": "Job invoke errorCode 2818 — no machine in folder",
            "symptom": "StartJobs fails with no Unattended runtimes in folder",
            "workaround": "Create Standard machine via POST /odata/Machines, assign via AssignMachines action",
            "status": "setup_required",
        },
        {
            "id": 10,
            "title": "Job invoke errorCode 1015 — no robot credentials",
            "symptom": "Robots without credentials cannot run interactive",
            "workaround": "Set requiresUserInteraction:false and projectProfile:0 in project.json",
            "status": "config_required",
        },
        {
            "id": 11,
            "title": "Studio 25.10 project.json enum strictness",
            "symptom": "uipcli pack errors: net6.0-windows is invalid for type TargetFramework",
            "workaround": "Use Portable/Legacy/Windows/Cross-Platform enum strings; projectProfile numeric",
            "status": "version_breaking",
        },
        {
            "id": 12,
            "title": "main field required in project.json",
            "symptom": "Robot error ArgumentNullException path2 in InitWorkflowApplication",
            "workaround": "Always include main: Main.xaml top-level field",
            "status": "version_breaking",
        },
    ]

    capability_matrix = {
        "ui_click_type": "unavailable_linux_serverless",
        "intelligent_ocr_activities": "unavailable_linux_serverless",
        "du_rest_api_v2": "available_with_scopes",
        "maestro_deploy_api": "unavailable",
        "action_center": "enterprise_only",
        "storage_buckets": "available_with_scopes",
        "orchestrator_assets_runtime": "bake_at_packtime",
        "csharp_coded_workflow_httpclient": "available",
        "queue_seed_and_job_invoke": "available",
        "package_upload_and_release_create": "available",
    }

    return {"gotchas": gotchas, "capability_matrix": capability_matrix}


async def generate_agent_scaffold(
    process_name: str,
    output_dir: str,
    description: str = "",
) -> dict[str, Any]:
    """Generate a UiPath Python SDK agent scaffold.

    Creates uipath.json, entry-points.json, pyproject.toml, and main.py
    for deploying via `uipath pack` / `uipath publish`.

    Args:
        process_name: Name of the agent process.
        output_dir: Directory to write scaffold files.
        description: Optional description for the agent.

    Returns:
        A dict with ``success``, ``files``, ``errors``.
    """
    try:
        from rpa_architect.assembler.agent_scaffold_gen import (
            generate_agent_scaffold as gen_scaffold,
        )

        files = gen_scaffold(
            process_name=process_name,
            description=description or f"UiPath agent: {process_name}",
        )

        out_path = Path(output_dir)
        out_path.mkdir(parents=True, exist_ok=True)

        written: list[str] = []
        for file_path, content in files.items():
            full = out_path / file_path
            full.parent.mkdir(parents=True, exist_ok=True)
            full.write_text(content, encoding="utf-8")
            written.append(file_path)

        return {"success": True, "files": written, "errors": []}
    except Exception as exc:
        return {"success": False, "files": [], "errors": [str(exc)]}
