"""Framework wiring engine -- connects generated workflows into REFramework structure."""
from __future__ import annotations

import logging
import re
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from rpa_architect.wiring.invoke_linker import generate_invoke_chain, generate_invoke_workflow
from rpa_architect.wiring.variable_injector import (
    REFRAMEWORK_VARIABLES,
    detect_missing_variables,
    inject_variables,
    scan_variable_references,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Namespace map for UiPath XAML parsing
# ---------------------------------------------------------------------------
_NS = {
    "default": "http://schemas.microsoft.com/netfx/2009/xaml/activities",
    "x": "http://schemas.microsoft.com/winfx/2006/xaml",
    "ui": "http://schemas.uipath.com/workflow/activities",
    "scg": "clr-namespace:System.Collections.Generic;assembly=mscorlib",
    "sap2010": "http://schemas.microsoft.com/netfx/2010/xaml/activities/presentation",
}

# Framework directories/files that should NOT be treated as custom workflows
_FRAMEWORK_DIRS = {"Framework", "Tests", ".objects", ".local", "Data", "Exceptions_Screenshots"}
_FRAMEWORK_FILES = {
    "Main.xaml",
}

# Scaffold marker patterns
_MARKER_PATTERN = re.compile(r"<!--\s*(INVOKE_WORKFLOWS_HERE|INSERT_WORKFLOWS|WORKFLOW_INVOCATIONS)\s*-->")

# Pattern to detect if an InvokeWorkflowFile for a given path already exists
_INVOKE_EXISTING_RE_TEMPLATE = r'<ui:InvokeWorkflowFile[^>]*WorkflowFileName="[^"]*{path_escaped}"'


# ---------------------------------------------------------------------------
# Result models
# ---------------------------------------------------------------------------

class WiringAction(BaseModel):
    """A single wiring action performed."""
    action_type: str  # "invoke_inserted", "variable_injected", "marker_replaced", "argument_chained"
    target_file: str
    detail: str


class WiringResult(BaseModel):
    """Result of the wiring operation."""
    success: bool = True
    actions: list[WiringAction] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

def wire_project(
    project_dir: Path | str,
    ir: dict[str, Any] | None = None,
) -> WiringResult:
    """Wire all generated workflows into the REFramework structure.

    This is the main entry point. It:
    1. Scans for custom workflows in Workflows/ directory
    2. Inserts InvokeWorkflowFile calls in Process.xaml
    3. Injects shared variables into framework files
    4. Replaces scaffold markers
    5. Chains argument flows

    Args:
        project_dir: Path to the UiPath project root.
        ir: Optional IR dict for additional context (transaction fields, config keys, etc.).

    Returns:
        WiringResult with all actions taken.
    """
    project_dir = Path(project_dir)
    result = WiringResult()
    ir = ir or {}

    if not project_dir.exists():
        result.success = False
        result.errors.append(f"Project directory not found: {project_dir}")
        return result

    # --- Step 1: Find custom workflows ---
    custom_workflows = _find_custom_workflows(project_dir)
    if not custom_workflows:
        result.warnings.append("No custom workflows found in Workflows/ directory.")
        logger.info("No custom workflows found; nothing to wire.")
        return result

    logger.info("Found %d custom workflow(s) to wire: %s",
                len(custom_workflows),
                [w.name for w in custom_workflows])

    # --- Step 2: Detect arguments for each workflow ---
    workflow_specs: list[dict[str, Any]] = []
    for wf_path in custom_workflows:
        rel_path = str(wf_path.relative_to(project_dir))
        args = _detect_needed_arguments(wf_path)
        arg_dict: dict[str, tuple[str, str]] = {}

        for arg_info in args:
            arg_name = arg_info["name"]
            direction = arg_info["direction"]
            # Auto-bind known framework variables
            value = _resolve_argument_value(arg_name, direction, ir)
            arg_dict[arg_name] = (direction, value)

        workflow_specs.append({
            "path": rel_path,
            "arguments": arg_dict,
            "display_name": wf_path.stem,
            "abs_path": wf_path,
        })

        if args:
            result.actions.append(WiringAction(
                action_type="argument_chained",
                target_file=rel_path,
                detail=f"Detected {len(args)} argument(s): {[a['name'] for a in args]}",
            ))

    # --- Step 3: Build invocation XML for each workflow ---
    invocations: list[str] = []
    for spec in workflow_specs:
        invoke_xml = generate_invoke_workflow(
            workflow_path=spec["path"],
            arguments=spec["arguments"] if spec["arguments"] else None,
            display_name=spec["display_name"],
        )
        invocations.append(invoke_xml)

    # --- Step 4: Insert invocations into Process.xaml ---
    process_path = project_dir / "Framework" / "Process.xaml"
    if not process_path.exists():
        result.warnings.append("Framework/Process.xaml not found; skipping invocation insertion.")
    else:
        process_content = process_path.read_text(encoding="utf-8")

        # Filter out workflows already invoked (idempotency)
        new_invocations: list[str] = []
        for spec, invoke_xml in zip(workflow_specs, invocations):
            if _is_already_invoked(process_content, spec["path"]):
                logger.debug("Workflow '%s' already invoked in Process.xaml; skipping.", spec["path"])
                result.warnings.append(
                    f"Workflow '{spec['path']}' already invoked in Process.xaml; skipped."
                )
            else:
                new_invocations.append(invoke_xml)
                result.actions.append(WiringAction(
                    action_type="invoke_inserted",
                    target_file="Framework/Process.xaml",
                    detail=f"Inserted InvokeWorkflowFile for {spec['path']}",
                ))

        if new_invocations:
            process_content = _insert_invocations_into_process(
                process_content, new_invocations, result
            )
            process_path.write_text(process_content, encoding="utf-8")
            logger.info("Updated Process.xaml with %d invocation(s).", len(new_invocations))

    # --- Step 5: Replace scaffold markers in all framework files ---
    _replace_markers_in_project(project_dir, workflow_specs, result)

    # --- Step 6: Inject shared variables into framework files that need them ---
    _inject_framework_variables(project_dir, result)

    # --- Step 7: Inject variables into custom workflows that reference framework vars ---
    for spec in workflow_specs:
        wf_path: Path = spec["abs_path"]
        missing = detect_missing_variables(wf_path)
        if missing:
            injected = inject_variables(wf_path, missing)
            for var_name in injected:
                result.actions.append(WiringAction(
                    action_type="variable_injected",
                    target_file=spec["path"],
                    detail=f"Injected variable '{var_name}'",
                ))

    if result.errors:
        result.success = False

    logger.info(
        "Wiring complete: %d action(s), %d warning(s), %d error(s).",
        len(result.actions), len(result.warnings), len(result.errors),
    )
    return result


# ---------------------------------------------------------------------------
# Discovery helpers
# ---------------------------------------------------------------------------

def _find_custom_workflows(project_dir: Path) -> list[Path]:
    """Find all custom .xaml workflows (excluding framework files).

    Scans the Workflows/ subdirectory for .xaml files. If no Workflows/
    directory exists, scans the project root for .xaml files that are not
    in framework directories.

    Args:
        project_dir: Root of the UiPath project.

    Returns:
        Sorted list of Path objects for each custom workflow.
    """
    workflows_dir = project_dir / "Workflows"
    if workflows_dir.is_dir():
        return sorted(workflows_dir.rglob("*.xaml"))

    # Fallback: scan root for non-framework .xaml files
    results: list[Path] = []
    for xaml_file in project_dir.rglob("*.xaml"):
        rel = xaml_file.relative_to(project_dir)
        parts = rel.parts
        # Skip files in framework directories
        if parts and parts[0] in _FRAMEWORK_DIRS:
            continue
        # Skip known framework root files
        if rel.name in _FRAMEWORK_FILES:
            continue
        results.append(xaml_file)

    return sorted(results)


# ---------------------------------------------------------------------------
# XAML reading/writing
# ---------------------------------------------------------------------------

def _read_xaml(path: Path) -> tuple[ET.Element, str]:
    """Read and parse a XAML file, returning (root_element, raw_content).

    Returns the parsed ElementTree root and the raw text content.
    Raises FileNotFoundError if the file does not exist.
    """
    raw = path.read_text(encoding="utf-8")
    root = ET.fromstring(raw)
    return root, raw


def _write_xaml(path: Path, root: ET.Element) -> None:
    """Write an ElementTree back to a XAML file with proper formatting.

    Adds the XML declaration and ensures UTF-8 encoding.
    """
    tree = ET.ElementTree(root)
    ET.indent(tree, space="  ")
    with open(path, "wb") as f:
        tree.write(f, encoding="utf-8", xml_declaration=True)


# ---------------------------------------------------------------------------
# Scaffold marker replacement
# ---------------------------------------------------------------------------

def _replace_scaffold_markers(content: str, replacements: dict[str, str]) -> str:
    """Replace scaffold markers like <!-- INVOKE_WORKFLOWS_HERE --> with actual content.

    Args:
        content: Raw XAML text.
        replacements: Mapping of marker name -> replacement XAML text.

    Returns:
        Modified content with markers replaced.
    """
    def _replacer(match: re.Match) -> str:
        marker_name = match.group(1).strip()
        replacement = replacements.get(marker_name)
        if replacement is not None:
            return replacement
        # Return original marker if no replacement defined
        return match.group(0)

    return _MARKER_PATTERN.sub(_replacer, content)


def _replace_markers_in_project(
    project_dir: Path,
    workflow_specs: list[dict[str, Any]],
    result: WiringResult,
) -> None:
    """Scan all framework .xaml files for scaffold markers and replace them.

    Generates a chain of InvokeWorkflowFile calls and uses it to replace markers.
    """
    # Build the replacement invocation chain
    chain_specs = [
        {"path": s["path"], "arguments": s["arguments"], "display_name": s["display_name"]}
        for s in workflow_specs
    ]
    chain_xml = generate_invoke_chain(chain_specs) if chain_specs else ""

    replacements = {
        "INVOKE_WORKFLOWS_HERE": chain_xml,
        "INSERT_WORKFLOWS": chain_xml,
        "WORKFLOW_INVOCATIONS": chain_xml,
    }

    # Scan all .xaml files in the project
    for xaml_file in project_dir.rglob("*.xaml"):
        try:
            content = xaml_file.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError) as exc:
            logger.warning("Could not read %s: %s", xaml_file, exc)
            continue

        if not _MARKER_PATTERN.search(content):
            continue

        rel_path = str(xaml_file.relative_to(project_dir))
        new_content = _replace_scaffold_markers(content, replacements)

        if new_content != content:
            xaml_file.write_text(new_content, encoding="utf-8")
            result.actions.append(WiringAction(
                action_type="marker_replaced",
                target_file=rel_path,
                detail="Replaced scaffold marker(s) with workflow invocations",
            ))
            logger.info("Replaced scaffold markers in %s.", rel_path)


# ---------------------------------------------------------------------------
# Argument detection
# ---------------------------------------------------------------------------

def _detect_needed_arguments(workflow_path: Path) -> list[dict[str, str]]:
    """Parse a workflow XAML to detect its declared arguments (name, type, direction).

    UiPath arguments are declared as <x:Property> elements inside the Activity's
    x:Members, or as top-level InArgument/OutArgument attributes.

    Args:
        workflow_path: Path to a .xaml workflow file.

    Returns:
        List of {"name": str, "type": str, "direction": str} dicts.
    """
    if not workflow_path.exists():
        return []

    try:
        content = workflow_path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        logger.warning("Could not read workflow %s: %s", workflow_path, exc)
        return []

    arguments: list[dict[str, str]] = []
    seen_names: set[str] = set()

    # Pattern 1: x:Property declarations (UiPath argument declarations)
    # <x:Property Name="in_Config" Type="InArgument(scg:Dictionary(x:String, x:Object))" />
    # The type can contain nested parentheses, so we match up to the closing "
    prop_pattern = re.compile(
        r'<x:Property\s+Name="([^"]+)"\s+Type="((?:In|Out|InOut)Argument)\((.+?)\)\s*"',
        re.IGNORECASE,
    )
    for match in prop_pattern.finditer(content):
        name = match.group(1)
        direction_tag = match.group(2)
        arg_type = match.group(3)

        # Strip direction prefix from name for cleaner mapping
        clean_name = _strip_direction_prefix(name)
        direction = _tag_to_direction(direction_tag)

        if clean_name not in seen_names:
            seen_names.add(clean_name)
            arguments.append({
                "name": clean_name,
                "type": arg_type,
                "direction": direction,
                "raw_name": name,
            })

    # Pattern 2: Standalone argument attributes in the Activity element
    # <Activity ... in_TransactionItem="[TransactionItem]" ...>
    attr_pattern = re.compile(
        r'\b(in|out|io)_([A-Za-z_]\w*)="([^"]*)"'
    )
    for match in attr_pattern.finditer(content):
        prefix = match.group(1)
        arg_name = match.group(2)
        direction = {"in": "In", "out": "Out", "io": "InOut"}.get(prefix, "In")

        if arg_name not in seen_names:
            seen_names.add(arg_name)
            arguments.append({
                "name": arg_name,
                "type": "x:Object",
                "direction": direction,
                "raw_name": f"{prefix}_{arg_name}",
            })

    # Pattern 3: <x:Property Name="argName" Type="InArgument(x:String)" /> (alternate format
    # with optional whitespace around the parentheses)
    alt_prop_pattern = re.compile(
        r'<x:Property\s+Name="([^"]+)"\s+Type="((?:In|Out|InOut)Argument)\s*\(\s*(.+?)\s*\)\s*"',
        re.IGNORECASE,
    )
    for match in alt_prop_pattern.finditer(content):
        name = match.group(1)
        direction_tag = match.group(2)
        arg_type = match.group(3)
        clean_name = _strip_direction_prefix(name)
        direction = _tag_to_direction(direction_tag)

        if clean_name not in seen_names:
            seen_names.add(clean_name)
            arguments.append({
                "name": clean_name,
                "type": arg_type,
                "direction": direction,
                "raw_name": name,
            })

    return arguments


# ---------------------------------------------------------------------------
# Invocation insertion
# ---------------------------------------------------------------------------

def _insert_invocations_into_process(
    process_content: str,
    invocations: list[str],
    result: WiringResult,
) -> str:
    """Insert InvokeWorkflowFile XAML blocks into Process.xaml content.

    Strategies (tried in order):
    1. Replace scaffold markers (<!-- INVOKE_WORKFLOWS_HERE -->, etc.)
    2. Append before the closing </Sequence> tag
    3. Append before the closing </Activity> tag

    Args:
        process_content: Raw text content of Process.xaml.
        invocations: List of InvokeWorkflowFile XAML strings.
        result: WiringResult to record actions/warnings.

    Returns:
        Modified Process.xaml content.
    """
    # Build the combined invocation block
    indented_invocations = []
    for inv in invocations:
        # Indent each invocation to sit inside a Sequence (4 spaces)
        indented = "\n".join(f"    {line}" for line in inv.splitlines())
        indented_invocations.append(indented)
    invocation_block = "\n".join(indented_invocations)

    # Strategy 1: Replace scaffold marker
    marker_match = _MARKER_PATTERN.search(process_content)
    if marker_match:
        marker_name = marker_match.group(1).strip()
        new_content = process_content[:marker_match.start()] + invocation_block + process_content[marker_match.end():]
        result.actions.append(WiringAction(
            action_type="marker_replaced",
            target_file="Framework/Process.xaml",
            detail=f"Replaced marker '<!-- {marker_name} -->' with invocations",
        ))
        return new_content

    # Strategy 2: Insert before closing </Sequence> tag
    # Find the last </Sequence> — it's typically the main Process Sequence
    last_seq_close = process_content.rfind("</Sequence>")
    if last_seq_close != -1:
        return (
            process_content[:last_seq_close]
            + invocation_block + "\n"
            + process_content[last_seq_close:]
        )

    # Strategy 3: Insert before closing </Activity>
    activity_close = process_content.rfind("</Activity>")
    if activity_close != -1:
        # Wrap in a Sequence since there's no existing one
        wrapped = (
            f'  <Sequence DisplayName="Process Transaction">\n'
            f'{invocation_block}\n'
            f'  </Sequence>\n'
        )
        return (
            process_content[:activity_close]
            + wrapped
            + process_content[activity_close:]
        )

    # Fallback: append at end
    result.warnings.append(
        "Could not find insertion point in Process.xaml; appended invocations at end."
    )
    return process_content + "\n" + invocation_block


# ---------------------------------------------------------------------------
# Variable injection for framework files
# ---------------------------------------------------------------------------

def _inject_framework_variables(project_dir: Path, result: WiringResult) -> None:
    """Inject shared REFramework variables into framework files that need them.

    Scans framework files for variable references and injects any missing
    REFramework variables.
    """
    framework_files = [
        project_dir / "Framework" / "Process.xaml",
        project_dir / "Framework" / "InitAllApplications.xaml",
        project_dir / "Framework" / "GetTransactionData.xaml",
        project_dir / "Framework" / "SetTransactionStatus.xaml",
        project_dir / "Framework" / "CloseAllApplications.xaml",
        project_dir / "Main.xaml",
    ]

    for fw_path in framework_files:
        if not fw_path.exists():
            continue

        missing = detect_missing_variables(fw_path)
        if missing:
            injected = inject_variables(fw_path, missing)
            rel_path = str(fw_path.relative_to(project_dir))
            for var_name in injected:
                result.actions.append(WiringAction(
                    action_type="variable_injected",
                    target_file=rel_path,
                    detail=f"Injected variable '{var_name}'",
                ))


# ---------------------------------------------------------------------------
# Idempotency helpers
# ---------------------------------------------------------------------------

def _is_already_invoked(process_content: str, workflow_path: str) -> bool:
    """Check whether an InvokeWorkflowFile for the given path already exists in content.

    Handles both forward-slash and backslash path separators.
    """
    # Normalise to backslash for matching
    normalised = workflow_path.replace("/", "\\")
    # Escape for regex
    escaped = re.escape(normalised)
    # Also check forward-slash variant
    escaped_fwd = re.escape(workflow_path)

    pattern = re.compile(
        rf'<ui:InvokeWorkflowFile[^>]*WorkflowFileName="[^"]*(?:{escaped}|{escaped_fwd})"',
        re.IGNORECASE,
    )
    return bool(pattern.search(process_content))


# ---------------------------------------------------------------------------
# Argument resolution helpers
# ---------------------------------------------------------------------------

def _resolve_argument_value(arg_name: str, direction: str, ir: dict[str, Any]) -> str:
    """Resolve the variable/expression to bind to a workflow argument.

    For known REFramework arguments, returns the standard variable name.
    For IR-defined fields, attempts to map to transaction data properties.

    Args:
        arg_name: The argument name (without direction prefix).
        direction: "In", "Out", or "InOut".
        ir: The IR dictionary for context.

    Returns:
        A VB expression string to bind to the argument.
    """
    # Known REFramework variable mappings
    known_mappings: dict[str, str] = {
        "Config": "Config",
        "config": "Config",
        "TransactionItem": "TransactionItem",
        "transactionItem": "TransactionItem",
        "TransactionData": "TransactionData",
        "transactionData": "TransactionData",
        "TransactionNumber": "TransactionNumber",
    }

    if arg_name in known_mappings:
        return known_mappings[arg_name]

    # Check if the argument name matches a config key
    config = ir.get("config", {})
    if isinstance(config, dict) and arg_name in config:
        return f'Config("{arg_name}")'

    # Check if it matches a transaction field
    transactions = ir.get("transactions", [])
    for txn in transactions:
        if isinstance(txn, dict):
            input_contract = txn.get("input_contract", {})
            if isinstance(input_contract, dict):
                fields = input_contract.get("fields", [])
                for field in fields:
                    if isinstance(field, dict) and field.get("name") == arg_name:
                        return f'TransactionItem.SpecificContent("{arg_name}").ToString'

    # Default: use the argument name as-is (assume a variable with the same name exists)
    return arg_name


def _strip_direction_prefix(name: str) -> str:
    """Strip UiPath direction prefix (in_, out_, io_) from an argument name."""
    for prefix in ("in_", "out_", "io_"):
        if name.startswith(prefix):
            return name[len(prefix):]
    return name


def _tag_to_direction(tag: str) -> str:
    """Convert a XAML argument type tag to a direction string."""
    tag_lower = tag.lower()
    if "inout" in tag_lower:
        return "InOut"
    if "out" in tag_lower:
        return "Out"
    return "In"
