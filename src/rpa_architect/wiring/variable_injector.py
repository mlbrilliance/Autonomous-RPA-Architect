"""Variable dependency scanning and injection for UiPath XAML workflows."""
from __future__ import annotations

import logging
import re
import xml.etree.ElementTree as ET
from pathlib import Path

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Namespace map used when parsing UiPath XAML
# ---------------------------------------------------------------------------
_NS = {
    "": "http://schemas.microsoft.com/netfx/2009/xaml/activities",
    "x": "http://schemas.microsoft.com/winfx/2006/xaml",
    "ui": "http://schemas.uipath.com/workflow/activities",
    "scg": "clr-namespace:System.Collections.Generic;assembly=mscorlib",
    "sap2010": "http://schemas.microsoft.com/netfx/2010/xaml/activities/presentation",
}

# Register namespaces so ET.write preserves prefixes
for _prefix, _uri in _NS.items():
    if _prefix:
        ET.register_namespace(_prefix, _uri)
ET.register_namespace("", _NS[""])

# Common shared variables in REFramework
REFRAMEWORK_VARIABLES: dict[str, dict[str, str]] = {
    "Config": {
        "type": 'scg:Dictionary(x:String, x:Object)',
        "annotation": "Configuration dictionary from Config.xlsx",
    },
    "TransactionItem": {
        "type": "ui:QueueItem",
        "annotation": "Current transaction queue item",
    },
    "TransactionData": {
        "type": "System.Data.DataRow",
        "annotation": "Current transaction data row",
    },
    "TransactionNumber": {
        "type": "x:Int32",
        "annotation": "Current transaction number",
    },
    "ConsecutiveSystemExceptions": {
        "type": "x:Int32",
        "annotation": "Count of consecutive system exceptions",
    },
}

# Patterns that indicate a variable reference in XAML expressions
_EXPR_BRACKET_RE = re.compile(r"\[([A-Za-z_]\w*(?:\.\w+)*)\]")
_DOTTED_REF_RE = re.compile(r"(?<![\"'\w])([A-Za-z_]\w*)\.(?:ToString|Item|Count|Rows|Value|Length|ContainsKey)")

# Pattern for argument bindings that reference variables
_ARG_VALUE_RE = re.compile(
    r'(?:InArgument|OutArgument|InOutArgument)[^>]*>\s*\[([A-Za-z_]\w*)'
)


def inject_variables(
    xaml_path: Path,
    variables: list[dict[str, str]],
) -> list[str]:
    """Inject variable declarations into a XAML workflow if not already present.

    Args:
        xaml_path: Path to the XAML file.
        variables: List of {"name": str, "type": str, "default": str, "annotation": str}.

    Returns:
        List of variable names that were injected (already-present ones are skipped).
    """
    if not xaml_path.exists():
        logger.warning("XAML file not found: %s", xaml_path)
        return []

    if not variables:
        return []

    content = xaml_path.read_text(encoding="utf-8")
    existing_names = _extract_declared_variable_names(content)

    injected: list[str] = []
    new_var_elements: list[str] = []

    for var in variables:
        name = var.get("name", "")
        if not name:
            continue
        if name in existing_names:
            logger.debug("Variable '%s' already declared in %s; skipping.", name, xaml_path.name)
            continue

        var_type = var.get("type", "x:String")
        default = var.get("default", "")
        annotation = var.get("annotation", "")
        new_var_elements.append(generate_variable_xaml(name, var_type, default, annotation))
        injected.append(name)

    if not new_var_elements:
        return []

    # Insert the new variables into the XAML content
    content = _insert_variable_declarations(content, new_var_elements)
    xaml_path.write_text(content, encoding="utf-8")
    logger.info("Injected %d variables into %s: %s", len(injected), xaml_path.name, injected)
    return injected


def scan_variable_references(xaml_content: str) -> set[str]:
    """Scan XAML content for variable references.

    Looks for variable names used in:
    - Expression values: [VariableName], VariableName.Property
    - Argument bindings
    - Activity property values

    Args:
        xaml_content: Raw XAML text content.

    Returns:
        Set of variable names that appear to be referenced.
    """
    refs: set[str] = set()

    # Match bracket expressions like [Config] or [TransactionItem.SpecificContent]
    for match in _EXPR_BRACKET_RE.finditer(xaml_content):
        # Take the root variable name (before any dot)
        full_ref = match.group(1)
        root_name = full_ref.split(".")[0]
        refs.add(root_name)

    # Match dotted references like Config.ContainsKey, TransactionItem.ToString
    for match in _DOTTED_REF_RE.finditer(xaml_content):
        refs.add(match.group(1))

    # Match argument binding values
    for match in _ARG_VALUE_RE.finditer(xaml_content):
        refs.add(match.group(1))

    # Filter out common XAML keywords / built-in names that are not variables
    noise = {
        "x", "ui", "scg", "sap", "sap2010", "sads", "mc", "mva", "sco", "sd",
        "True", "False", "Nothing", "String", "Int32", "Boolean", "Object",
        "System", "Microsoft", "UiPath", "Sequence", "Variable", "Argument",
        "Activity", "State", "Transition", "Flowchart",
    }
    refs -= noise

    return refs


def detect_missing_variables(xaml_path: Path) -> list[dict[str, str]]:
    """Detect variables referenced but not declared in a XAML file.

    Checks against REFRAMEWORK_VARIABLES for known framework variables.

    Args:
        xaml_path: Path to the XAML file.

    Returns:
        List of variable dicts (name, type, annotation) that are referenced
        but not declared and match known REFramework variables.
    """
    if not xaml_path.exists():
        logger.warning("XAML file not found for missing-variable detection: %s", xaml_path)
        return []

    content = xaml_path.read_text(encoding="utf-8")
    declared = _extract_declared_variable_names(content)
    referenced = scan_variable_references(content)

    missing: list[dict[str, str]] = []
    for ref_name in sorted(referenced - declared):
        if ref_name in REFRAMEWORK_VARIABLES:
            info = REFRAMEWORK_VARIABLES[ref_name]
            missing.append({
                "name": ref_name,
                "type": info["type"],
                "default": "",
                "annotation": info["annotation"],
            })
        else:
            logger.debug(
                "Variable '%s' referenced in %s is not declared and is not a known "
                "REFramework variable; it may be a local or external reference.",
                ref_name, xaml_path.name,
            )

    return missing


def generate_variable_xaml(
    name: str,
    var_type: str,
    default: str = "",
    annotation: str = "",
) -> str:
    """Generate a single <Variable> XAML element.

    Args:
        name: Variable name.
        var_type: XAML type string (e.g., "x:String", "x:Int32", "ui:QueueItem").
        default: Default value expression (optional).
        annotation: Annotation / description text (optional).

    Returns:
        A complete <Variable> XML element string.
    """
    parts = [f'<Variable x:TypeArguments="{_xml_escape_attr(var_type)}" Name="{_xml_escape_attr(name)}"']

    if default:
        parts.append(f' Default="{_xml_escape_attr(default)}"')

    if annotation:
        parts.append(
            f' sap2010:Annotation.AnnotationText="{_xml_escape_attr(annotation)}"'
        )

    parts.append(" />")
    return "".join(parts)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _xml_escape_attr(value: str) -> str:
    """Escape a string for use inside an XML attribute."""
    return (
        value
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
        .replace("'", "&apos;")
    )


def _extract_declared_variable_names(xaml_content: str) -> set[str]:
    """Extract the set of variable names already declared in XAML content.

    Uses regex to avoid full XML parse issues with complex UiPath namespaces.
    """
    # Match <Variable ... Name="SomeName" ... />
    pattern = re.compile(r'<Variable\b[^>]*\bName="([^"]+)"', re.IGNORECASE)
    return {m.group(1) for m in pattern.finditer(xaml_content)}


def _find_variables_block(content: str) -> tuple[int, int] | None:
    """Find the position of an existing <Sequence.Variables> block.

    Returns (start, end) byte offsets of the block, or None if not found.
    """
    # Look for various Variable container patterns
    for tag_name in ("Sequence.Variables", "Flowchart.Variables", "Activity.Variables"):
        open_tag = f"<{tag_name}>"
        close_tag = f"</{tag_name}>"
        start = content.find(open_tag)
        if start != -1:
            end = content.find(close_tag, start)
            if end != -1:
                return (start, end + len(close_tag))

    # Also try self-contained pattern with child <Variable> elements
    # Some XAML puts Variables directly inside Sequence
    return None


def _insert_variable_declarations(content: str, var_elements: list[str]) -> str:
    """Insert variable declaration elements into XAML content.

    Strategy:
    1. If a <Sequence.Variables> (or similar) block exists, insert before its close tag.
    2. If a <Sequence> element exists, insert a new <Sequence.Variables> block after its opening tag.
    3. If an <Activity> root exists, wrap in Sequence with Variables.
    """
    vars_xml = "\n".join(f"      {v}" for v in var_elements)

    # Strategy 1: Insert into existing Variables block
    for tag_name in ("Sequence.Variables", "Flowchart.Variables", "Activity.Variables"):
        close_tag = f"</{tag_name}>"
        idx = content.find(close_tag)
        if idx != -1:
            insertion = f"\n{vars_xml}\n    "
            return content[:idx] + insertion + content[idx:]

    # Strategy 2: Insert a new Variables block after <Sequence ...> opening tag
    seq_pattern = re.compile(r'(<Sequence\b[^>]*>)', re.DOTALL)
    match = seq_pattern.search(content)
    if match:
        insert_pos = match.end()
        vars_block = (
            f"\n    <Sequence.Variables>\n"
            f"{vars_xml}\n"
            f"    </Sequence.Variables>"
        )
        return content[:insert_pos] + vars_block + content[insert_pos:]

    # Strategy 3: Look for a Flowchart tag
    fc_pattern = re.compile(r'(<Flowchart\b[^>]*>)', re.DOTALL)
    match = fc_pattern.search(content)
    if match:
        insert_pos = match.end()
        vars_block = (
            f"\n    <Flowchart.Variables>\n"
            f"{vars_xml}\n"
            f"    </Flowchart.Variables>"
        )
        return content[:insert_pos] + vars_block + content[insert_pos:]

    # Fallback: insert before the closing </Activity> tag
    activity_close = content.rfind("</Activity>")
    if activity_close != -1:
        wrapper = (
            f"  <Sequence DisplayName=\"Main\">\n"
            f"    <Sequence.Variables>\n"
            f"{vars_xml}\n"
            f"    </Sequence.Variables>\n"
            f"  </Sequence>\n"
        )
        return content[:activity_close] + wrapper + content[activity_close:]

    # Last resort: append at end
    logger.warning("Could not find suitable insertion point for variables; appending at end.")
    return content + "\n" + "\n".join(var_elements) + "\n"
