"""Main project assembler for UiPath projects.

Coordinates all sub-generators to write a complete UiPath project
directory structure including workflows, configuration, object
repository, and test files.
"""

from __future__ import annotations

import logging
from pathlib import Path

from pydantic import BaseModel, Field

from rpa_architect.ir.schema import ProcessIR

# Import GeneratedFile directly from the module to avoid pulling in
# langgraph via codegen/__init__.py at import time.
try:
    from rpa_architect.codegen.orchestrator import GeneratedFile
except ImportError:
    # Fallback definition if langgraph is not installed
    class GeneratedFile(BaseModel):  # type: ignore[no-redef]
        """A single generated file in the UiPath project."""
        path: str
        content: str
        file_type: str
        generation_task_id: str

logger = logging.getLogger(__name__)


class ProjectManifest(BaseModel):
    """Manifest of a fully assembled UiPath project."""

    project_dir: Path = Field(description="Root directory of the assembled project.")
    files_written: list[str] = Field(
        default_factory=list,
        description="Relative paths of all files written to disk.",
    )
    warnings: list[str] = Field(
        default_factory=list,
        description="Non-fatal warnings generated during assembly.",
    )


def _ensure_directory_structure(output_dir: Path) -> None:
    """Create the minimal Portable Coded Workflow project tree.

    Post-pivot to Cross-Platform / Portable we only need Data/ (for
    Config.xlsx), .objects/ (for Object Repository), and .local/
    (for project.local.json). We no longer pre-create Framework/
    because we don't ship REFramework stub XAML anymore.
    """
    dirs = [
        output_dir,
        output_dir / "Data",
        output_dir / ".objects",
        output_dir / ".local",
    ]
    for d in dirs:
        d.mkdir(parents=True, exist_ok=True)


def _write_file(
    output_dir: Path,
    relative_path: str,
    content: str | bytes,
    manifest: ProjectManifest,
) -> None:
    """Write a single file and record it in the manifest."""
    file_path = output_dir / relative_path
    file_path.parent.mkdir(parents=True, exist_ok=True)

    if isinstance(content, bytes):
        file_path.write_bytes(content)
    else:
        file_path.write_text(content, encoding="utf-8")

    manifest.files_written.append(relative_path)


def _minimal_portable_main_xaml(process_name: str) -> str:
    """Return a Main.xaml that invokes the ProcessInvoiceMain coded workflow.

    Uses ``ui:InvokeWorkflowFile`` with WorkflowFileName pointing at the
    compiled coded workflow. Because Portable projects disable JIT
    compilation, we cannot pass expression arguments — so the coded
    workflow's ``Execute()`` method takes no parameters and reads all
    config from environment variables that the UiPath runtime injects
    from Orchestrator Assets.
    """
    return (
        '<?xml version="1.0" encoding="utf-8"?>\n'
        '<Activity mc:Ignorable="sap sap2010 sads"'
        ' x:Class="Main"'
        ' xmlns="http://schemas.microsoft.com/netfx/2009/xaml/activities"'
        ' xmlns:mc="http://schemas.openxmlformats.org/markup-compatibility/2006"'
        ' xmlns:sap="http://schemas.microsoft.com/netfx/2009/xaml/activities/presentation"'
        ' xmlns:sap2010="http://schemas.microsoft.com/netfx/2010/xaml/activities/presentation"'
        ' xmlns:sads="http://schemas.microsoft.com/netfx/2010/xaml/activities/debugger"'
        ' xmlns:ui="http://schemas.uipath.com/workflow/activities"'
        ' xmlns:x="http://schemas.microsoft.com/winfx/2006/xaml">\n'
        f'  <Sequence DisplayName="{process_name} Main">\n'
        '    <ui:InvokeWorkflowFile DisplayName="Invoke ProcessInvoiceMain"'
        ' WorkflowFileName="ProcessInvoiceMain.cs" />\n'
        '  </Sequence>\n'
        '</Activity>\n'
    )


async def assemble_project(
    ir: ProcessIR,
    generated_files: dict[str, GeneratedFile],
    output_dir: Path,
    harvest_config: object | None = None,
    llm_client: object | None = None,
) -> ProjectManifest:
    """Assemble a complete UiPath project in the output directory.

    Writes all generated code files, then invokes sub-generators for:
    - project.json (project metadata and dependencies)
    - Config.xlsx (REFramework configuration workbook)
    - REFramework XAML files (state machine and framework workflows)
    - Object repository (.objects/ directory)
    - Test files (Tests/ directory)

    Args:
        ir: The ProcessIR describing the RPA process.
        generated_files: Map of relative_path -> GeneratedFile from the
            code generation pipeline.
        output_dir: Root directory where the project will be written.
        harvest_config: Optional HarvestConfig for live browser selector harvesting.
        llm_client: Optional LLMClient for LLM-assisted element matching.

    Returns:
        ProjectManifest listing all written files and any warnings.
    """
    from rpa_architect.assembler.config_xlsx_gen import generate_config_xlsx
    from rpa_architect.assembler.project_json_gen import generate_project_json
    from rpa_architect.assembler.reframework_gen import generate_reframework_xaml
    from rpa_architect.selectors.object_repository import generate_object_repository
    from rpa_architect.selectors.placeholder_gen import generate_placeholder_selectors

    manifest = ProjectManifest(project_dir=output_dir)

    # Create directory structure
    _ensure_directory_structure(output_dir)
    logger.info("Assembling project '%s' in %s.", ir.process_name, output_dir)

    # 1. Write all generated code files from the pipeline
    for rel_path, gen_file in generated_files.items():
        _write_file(output_dir, rel_path, gen_file.content, manifest)

    # 2. Generate and write project.json
    try:
        project_json_content = generate_project_json(ir)
        _write_file(output_dir, "project.json", project_json_content, manifest)
    except Exception as exc:
        manifest.warnings.append(f"Failed to generate project.json: {exc}")
        logger.warning("project.json generation failed: %s", exc)

    # 3. Generate and write Config.xlsx
    try:
        config_path = output_dir / "Data" / "Config.xlsx"
        generate_config_xlsx(ir, config_path)
        manifest.files_written.append("Data/Config.xlsx")
    except ImportError:
        manifest.warnings.append(
            "openpyxl not installed; Config.xlsx was not generated."
        )
    except Exception as exc:
        manifest.warnings.append(f"Failed to generate Config.xlsx: {exc}")
        logger.warning("Config.xlsx generation failed: %s", exc)

    # 4. Main.xaml — MINIMAL valid workflow that hands off to the Coded
    # Workflow in ProcessInvoiceMain.cs. We intentionally do NOT generate
    # the old REFramework stub XAML anymore: the Framework/*.xaml files
    # referenced undeclared variables (ExtractedFields, in_TransactionItem,
    # etc.) and failed uipcli's compile validation. Portable / Coded
    # Workflow projects only need a minimal Main.xaml as the legacy
    # `main` field target.
    try:
        main_xaml = _minimal_portable_main_xaml(ir.process_name)
        _write_file(output_dir, "Main.xaml", main_xaml, manifest)
    except Exception as exc:
        manifest.warnings.append(f"Failed to generate Main.xaml: {exc}")
        logger.warning("Main.xaml generation failed: %s", exc)

    # 5. Generate object repository (with optional browser harvesting)
    try:
        placeholders = generate_placeholder_selectors(ir)
        selectors = placeholders

        if harvest_config and getattr(harvest_config, "enabled", False):
            try:
                from rpa_architect.selectors.harvest_pipeline import (
                    merge_selectors,
                    run_harvest_pipeline,
                )

                harvested = await run_harvest_pipeline(ir, harvest_config, llm_client)
                if harvested:
                    selectors = merge_selectors(harvested, placeholders)
                    logger.info(
                        "Merged %d harvested selectors with %d placeholders.",
                        len(harvested), len(placeholders),
                    )
            except ImportError:
                manifest.warnings.append(
                    "Playwright not installed; falling back to placeholder selectors. "
                    "Install with: pip install 'autonomous-rpa-architect[harvest]'"
                )
            except Exception as exc:
                manifest.warnings.append(f"Browser harvest failed: {exc}")
                logger.warning("Browser harvest failed, using placeholders: %s", exc)

        if selectors:
            obj_repo_files = generate_object_repository(ir, selectors)
            for rel_path, content in obj_repo_files.items():
                _write_file(output_dir, rel_path, content, manifest)
    except Exception as exc:
        manifest.warnings.append(f"Failed to generate object repository: {exc}")
        logger.warning("Object repository generation failed: %s", exc)

    # 6. Wire workflows into REFramework structure
    try:
        from rpa_architect.wiring import wire_project

        wiring_result = wire_project(output_dir, ir.model_dump() if ir else None)
        if wiring_result.warnings:
            manifest.warnings.extend(
                f"Wiring: {w}" for w in wiring_result.warnings
            )
        if wiring_result.errors:
            manifest.warnings.extend(
                f"Wiring error: {e}" for e in wiring_result.errors
            )
        if wiring_result.actions:
            logger.info(
                "Framework wiring: %d actions performed.",
                len(wiring_result.actions),
            )
    except Exception as exc:
        manifest.warnings.append(f"Framework wiring failed: {exc}")
        logger.warning("Framework wiring failed: %s", exc)

    # 7. Resolve NuGet package versions
    try:
        from rpa_architect.nuget import resolve_package

        project_json_path = output_dir / "project.json"
        if project_json_path.is_file():
            import json as _json

            pj_data = _json.loads(project_json_path.read_text(encoding="utf-8"))
            deps = pj_data.get("dependencies", {})
            updated = False
            for pkg_id in list(deps.keys()):
                try:
                    info = resolve_package(pkg_id)
                    if not info.is_fallback and info.version != deps[pkg_id]:
                        logger.info(
                            "NuGet: %s %s -> %s", pkg_id, deps[pkg_id], info.version
                        )
                        deps[pkg_id] = info.version
                        updated = True
                except Exception:
                    pass  # Keep existing version on resolution failure
            if updated:
                project_json_path.write_text(
                    _json.dumps(pj_data, indent=2, ensure_ascii=False) + "\n",
                    encoding="utf-8",
                )
    except Exception as exc:
        manifest.warnings.append(f"NuGet resolution failed: {exc}")
        logger.warning("NuGet resolution failed: %s", exc)

    # 8. Document Understanding taxonomy.json — DESIGN-TIME asset only.
    # Written as a SIBLING to the project dir (not bundled) because the
    # Portable runtime has no IntelligentOCR package and uipcli fails
    # compilation if DU activities are inside the main project tree.
    if ir.document_understanding is not None and ir.document_understanding.enabled:
        try:
            from rpa_architect.du.taxonomy import build_invoice_taxonomy
            from rpa_architect.du.taxonomy_gen import serialize_taxonomy

            taxonomy = build_invoice_taxonomy()
            taxonomy_json = serialize_taxonomy(taxonomy)
            sibling_du = output_dir.parent / f"{output_dir.name}_document_processing"
            sibling_du.mkdir(parents=True, exist_ok=True)
            (sibling_du / "taxonomy.json").write_text(
                taxonomy_json, encoding="utf-8"
            )
            logger.info(
                "DU taxonomy written as design-time sibling: %s",
                sibling_du / "taxonomy.json",
            )
        except Exception as exc:
            manifest.warnings.append(f"Failed to generate DU taxonomy.json: {exc}")
            logger.warning("DU taxonomy generation failed: %s", exc)

    # 9a. Enterprise Maestro BPMN + DMN (DESIGN-TIME SIBLINGS).
    # Always emit the enterprise Invoice Processing Factory BPMN
    # alongside the project. Studio Web's Maestro designer can import
    # these files directly.
    try:
        from rpa_architect.codegen.enterprise_bpmn_gen import (
            generate_invoice_processing_bpmn,
            generate_invoice_rules_dmn,
        )
        enterprise_sibling = output_dir.parent / f"{output_dir.name}_enterprise_maestro"
        enterprise_sibling.mkdir(parents=True, exist_ok=True)
        (enterprise_sibling / "InvoiceProcessingFlow.bpmn").write_text(
            generate_invoice_processing_bpmn(), encoding="utf-8"
        )
        (enterprise_sibling / "InvoiceRulesDecision.dmn").write_text(
            generate_invoice_rules_dmn(), encoding="utf-8"
        )
        (enterprise_sibling / "README.md").write_text(
            "# Enterprise Maestro design assets\n\n"
            "Import into Studio Web at `cloud.uipath.com/{org}/studio_/` →\n"
            "Maestro → New → Import BPMN. See\n"
            "`docs/maestro_studio_web_import.md` for the step-by-step guide.\n\n"
            "- `InvoiceProcessingFlow.bpmn` — full pipeline: receive → DU →\n"
            "  confidence gate → rules → create bill → notify. Mirrors the\n"
            "  C# state machine in `ProcessInvoiceMain.cs`.\n"
            "- `InvoiceRulesDecision.dmn` — 7-row decision table encoding\n"
            "  the 4 business rules (currency, duplicate, amount, KYC).\n"
            "  Business analysts can edit this without touching C#.\n",
            encoding="utf-8",
        )
        logger.info("Enterprise Maestro assets written: %s", enterprise_sibling)
    except Exception as exc:
        manifest.warnings.append(f"Failed to write enterprise Maestro assets: {exc}")
        logger.warning("Enterprise Maestro gen failed: %s", exc)

    # 9. Legacy Maestro BPMN (DESIGN-TIME ARTIFACT, written next to the project,
    # NOT bundled inside the .nupkg). UiPath Maestro has no public
    # deployment API as of 25.10 — Maestro processes are designed and
    # deployed via Studio Web. Bundling a BPMN file inside the .nupkg
    # was earlier-version fakery; Orchestrator silently ignores extra
    # files. The honest behavior: write the BPMN as a sibling design
    # asset that the user can manually import into Studio Web.
    try:
        from rpa_architect.maestro.bpmn_generator import generate_bpmn
        from rpa_architect.maestro.maestro_planner import detect_mode
        from rpa_architect.config import GenerationMode

        mode = detect_mode(ir)
        has_routing_rules = any(
            r.outcome in ("route", "escalate")
            for txn in ir.transactions
            for r in txn.business_rules
        )
        has_du = (
            ir.document_understanding is not None and ir.document_understanding.enabled
        )
        if mode in (GenerationMode.MAESTRO, GenerationMode.HYBRID) or has_du or has_routing_rules:
            bpmn_xml = generate_bpmn(ir, [])
            sibling_dir = output_dir.parent / f"{output_dir.name}_maestro"
            sibling_dir.mkdir(parents=True, exist_ok=True)
            bpmn_path = sibling_dir / f"{ir.process_name}.bpmn"
            bpmn_path.write_text(bpmn_xml, encoding="utf-8")
            # Also drop a README so the user knows what to do.
            readme = sibling_dir / "README.md"
            readme.write_text(
                f"# Maestro design asset for {ir.process_name}\n\n"
                "This BPMN file is a **design-time artifact**. UiPath Maestro\n"
                "has no public deployment API as of 25.10 — to deploy this\n"
                "process, open Studio Web at <https://cloud.uipath.com/>, go to\n"
                "**Maestro → Processes → New → Import BPMN**, and upload\n"
                f"`{bpmn_path.name}`.\n\n"
                "The .nupkg in the parent directory is the runnable package\n"
                "that talks to Odoo via JSON-RPC. The Maestro BPMN is a\n"
                "complementary higher-level orchestration spec.\n",
                encoding="utf-8",
            )
            logger.info(
                "Maestro BPMN written as design-time sibling: %s", bpmn_path
            )
    except Exception as exc:
        manifest.warnings.append(f"Failed to generate Maestro BPMN: {exc}")
        logger.warning("Maestro BPMN generation failed: %s", exc)

    # 10. Enterprise Invoice Processing Factory — 16 C# files:
    # - EmbeddedInvoices (5 real PDFs as base64)
    # - DocumentUnderstandingClient (real DU v2 HTTP)
    # - LocalInvoiceExtractor (fallback)
    # - Models (ProcessConfig, BatchMetrics, ProcessContext)
    # - OdooClient (auth + partner + bill + manager task)
    # - BusinessRuleEngine (IRule + 4 real rules)
    # - REFramework state machine (IState + 5 states + exceptions)
    # - ProcessInvoiceMain (entry point)
    try:
        import os as _os_for_odoo

        odoo_systems = [
            s for s in ir.systems
            if "odoo" in (s.name or "").lower() or "odoo" in (s.url or "").lower()
        ]
        if odoo_systems:
            from rpa_architect.codegen.du_client_gen import generate_du_client_cs
            from rpa_architect.codegen.embedded_invoices_gen import (
                generate_embedded_invoices_cs,
                load_invoices,
            )
            from rpa_architect.codegen.local_extractor_gen import (
                generate_local_extractor_cs,
            )
            from rpa_architect.codegen.models_gen import (
                generate_batch_metrics_cs,
                generate_process_config_cs,
                generate_process_context_cs,
            )
            from rpa_architect.codegen.odoo_client_gen import generate_odoo_client_cs
            from rpa_architect.codegen.reframework_csharp_gen import (
                generate_end_state_cs,
                generate_exceptions_cs,
                generate_get_transaction_state_cs,
                generate_init_state_cs,
                generate_istate_cs,
                generate_process_invoice_main_cs,
                generate_process_state_cs,
                generate_set_transaction_status_state_cs,
            )
            from rpa_architect.codegen.rules_engine_gen import (
                generate_rules_engine_cs,
            )

            from pathlib import Path as _Path
            pdf_dir = _Path(__file__).resolve().parent.parent.parent.parent / "tests" / "fixtures" / "invoices"
            default_url = _os_for_odoo.environ.get(
                "ODOO_PUBLIC_URL", "http://localhost:8069"
            )
            ns = ir.process_name

            files: dict[str, str] = {
                "EmbeddedInvoices.cs": generate_embedded_invoices_cs(
                    load_invoices(pdf_dir), namespace=ns
                ),
                "DocumentUnderstandingClient.cs": generate_du_client_cs(namespace=ns),
                "LocalInvoiceExtractor.cs": generate_local_extractor_cs(namespace=ns),
                "ProcessConfig.cs": generate_process_config_cs(namespace=ns),
                "BatchMetrics.cs": generate_batch_metrics_cs(namespace=ns),
                "ProcessContext.cs": generate_process_context_cs(namespace=ns),
                "OdooClient.cs": generate_odoo_client_cs(
                    namespace=ns, default_base_url=default_url
                ),
                "BusinessRuleEngine.cs": generate_rules_engine_cs(namespace=ns),
                "IState.cs": generate_istate_cs(namespace=ns),
                "ProcessExceptions.cs": generate_exceptions_cs(namespace=ns),
                "InitState.cs": generate_init_state_cs(namespace=ns),
                "GetTransactionDataState.cs": generate_get_transaction_state_cs(namespace=ns),
                "ProcessState.cs": generate_process_state_cs(namespace=ns),
                "SetTransactionStatusState.cs": generate_set_transaction_status_state_cs(namespace=ns),
                "EndState.cs": generate_end_state_cs(namespace=ns),
                "ProcessInvoiceMain.cs": generate_process_invoice_main_cs(
                    namespace=ns, default_odoo_url=default_url
                ),
            }
            for fname, content in files.items():
                _write_file(output_dir, fname, content, manifest)
    except Exception as exc:
        manifest.warnings.append(f"Failed to generate enterprise C# project: {exc}")
        logger.warning("Enterprise C# generation failed: %s", exc)

    # 11. Agent scaffolds — DESIGN-TIME siblings only. UiPath's robot
    # runtime has no Python SDK entry point concept for Portable C#
    # projects, so bundling them inside the nupkg just bloats the
    # package. They're written as a sibling for manual deployment via
    # `uipath pack` / `uipath publish` on the agent itself.
    try:
        from rpa_architect.assembler.agent_scaffold_gen import generate_agent_scaffold
        from rpa_architect.maestro.maestro_planner import _step_is_agent_candidate

        agent_steps = [
            step
            for txn in ir.transactions
            for step in txn.steps
            if _step_is_agent_candidate(step) is not None
        ]
        if agent_steps:
            sibling_agents = output_dir.parent / f"{output_dir.name}_agents"
            sibling_agents.mkdir(parents=True, exist_ok=True)
        for step in agent_steps:
            agent_name = f"agent_{step.id.lower()}"
            desc = (step.description or "").lower()
            if "vendor" in desc and "normaliz" in desc:
                agent_name = "vendor_normalizer"
            elif "classif" in desc:
                agent_name = "invoice_classifier"
            scaffold = generate_agent_scaffold(
                process_name=agent_name,
                description=step.description or "",
            )
            agent_dir = sibling_agents / agent_name
            agent_dir.mkdir(parents=True, exist_ok=True)
            for fname, content in scaffold.items():
                (agent_dir / fname).write_text(content, encoding="utf-8")
            logger.info("Agent scaffold written: %s", agent_dir)
    except Exception as exc:
        manifest.warnings.append(f"Failed to generate agent scaffolds: {exc}")
        logger.warning("Agent scaffold generation failed: %s", exc)

    # 12. Write .local/project.local.json placeholder
    local_json = '{\n  "schemaVersion": "1.0",\n  "projectSettings": {}\n}\n'
    _write_file(output_dir, ".local/project.local.json", local_json, manifest)

    logger.info(
        "Project assembly complete: %d files written, %d warnings.",
        len(manifest.files_written),
        len(manifest.warnings),
    )

    return manifest
