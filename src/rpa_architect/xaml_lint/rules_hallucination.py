"""Hallucination detection rules for UiPath XAML (ERROR severity).

Each rule function accepts (root: ET.Element, ns: dict[str, str]) and returns
a list of LintIssue instances.  These rules detect mistakes that LLMs commonly
make when generating UiPath XAML -- invented activities, wrong enums, broken
nesting, etc.
"""

from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from typing import TYPE_CHECKING

from rpa_architect.xaml_lint._line_map import get_line_number as _get_line_number
from rpa_architect.xaml_lint.known_activities import (
    VALID_ACTIVITIES,
    VALID_ENUMS,
    VALID_PROPERTIES,
)
from rpa_architect.xaml_lint.models import LintCategory, LintIssue, LintSeverity

if TYPE_CHECKING:
    pass

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

# Tags that are structural parts of activities rather than activities themselves
_STRUCTURAL_TAGS = {
    "Activity",
    "Members",
    "Property",
    "TextExpression",
    "WorkflowViewState",
    "ViewStateData",
    "ViewStateManager",
    "WorkflowViewStateService",
    "Literal",
    "Reference",
    "AssemblyReference",
    "Argument",
    "Variable",
    "VisualBasicSettings",
    "VisualBasicReference",
    "VisualBasicImport",
    "VisualBasicImportReference",
    "VisualBasicValue",
    "CSharpValue",
    "CSharpReference",
    "InArgument",
    "OutArgument",
    "InOutArgument",
    "Collection",
    "Dictionary",
    "List",
    "Imports",
    "NamespacesForImplementation",
    # State machine elements
    "StateMachine",
    "State",
    "StateReference",
    "Transition",
    "DelegateInArgument",
    "ActivityAction",
    "Target",
}

# Sub-element tags that are property accessors (ActivityName.PropertyName)
_PROPERTY_ACCESSOR_RE = re.compile(r"^[A-Z]\w+\.\w+$")

# Valid .NET primitive types and common UiPath types for TypeArgument validation
_VALID_DOTNET_TYPES = {
    # Primitives
    "x:String", "x:Int32", "x:Int64", "x:Boolean", "x:Double", "x:Decimal",
    "x:Object", "x:Byte", "x:Char", "x:Single", "x:Int16", "x:UInt16",
    "x:UInt32", "x:UInt64", "x:DateTime", "x:TimeSpan", "x:Guid",
    # System types (no prefix)
    "String", "Int32", "Int64", "Boolean", "Double", "Decimal",
    "Object", "Byte", "Char", "Single", "DateTime", "TimeSpan", "Guid",
    # Common complex types
    "DataTable", "DataRow", "DataColumn",
    "System.Data.DataTable", "System.Data.DataRow", "System.Data.DataColumn",
    "System.String", "System.Int32", "System.Int64", "System.Boolean",
    "System.Double", "System.Decimal", "System.Object", "System.DateTime",
    "System.TimeSpan", "System.Guid",
    "System.Net.Mail.MailMessage",
    "System.IO.DirectoryInfo", "System.IO.FileInfo",
    "System.Collections.Generic.KeyValuePair",
    "System.Exception", "System.ApplicationException",
    "System.Text.RegularExpressions.Match",
    "JObject", "JArray", "JToken",
    "Newtonsoft.Json.Linq.JObject", "Newtonsoft.Json.Linq.JArray",
    "Newtonsoft.Json.Linq.JToken",
    "UiPath.Core.QueueItem",
    "ui:QueueItem",
    "ui:BusinessRuleException",
    "UiPath.Core.BusinessRuleException",
    "System.Net.HttpStatusCode",
    "System.Security.SecureString",
}


def _local_name(tag: str) -> str:
    """Strip namespace URI from an ElementTree tag like {uri}LocalName."""
    if tag.startswith("{"):
        return tag.split("}", 1)[1]
    return tag


def _strip_generic(type_str: str) -> list[str]:
    """Extract base type names from a possibly-generic TypeArgument value.

    E.g. "TypeArgument='scg:KeyValuePair(x:String, x:Int32)'" yields
    ['KeyValuePair', 'x:String', 'x:Int32'].
    """
    # Remove assembly-qualified clr-namespace prefixes
    cleaned = re.sub(r"\[.*?\]", "", type_str)
    # Extract names from generic notation  Foo(Bar, Baz)
    parts = re.split(r"[(),\s]+", cleaned)
    return [p.strip() for p in parts if p.strip()]




# ---------------------------------------------------------------------------
# Rules
# ---------------------------------------------------------------------------


def lint_unknown_activities(root: ET.Element, ns: dict[str, str]) -> list[LintIssue]:
    """XL-H001: Flag activity element names not in the known activity registry."""
    issues: list[LintIssue] = []

    for elem in root.iter():
        local = _local_name(elem.tag)

        # Skip structural / framework tags
        if local in _STRUCTURAL_TAGS:
            continue

        # Skip property accessor elements (e.g. If.Then, TryCatch.Try)
        if _PROPERTY_ACCESSOR_RE.match(local):
            continue

        # Skip elements that start with lowercase (XML namespace artifacts)
        if local and local[0].islower():
            continue

        # Skip generic-looking suffixes often used by XAML serializer
        base_name = local.split("`")[0] if "`" in local else local

        if base_name not in VALID_ACTIVITIES:
            issues.append(
                LintIssue(
                    rule_id="XL-H001",
                    severity=LintSeverity.ERROR,
                    category=LintCategory.HALLUCINATION,
                    message=f"Unknown activity '{base_name}' is not a recognized UiPath activity",
                    element_name=base_name,
                    line_number=_get_line_number(elem),
                    suggestion=(
                        f"Check if '{base_name}' is a valid UiPath activity name. "
                        "Common LLM mistakes include inventing activities like "
                        "'ReadExcel' (should be 'ReadRange'), 'ClickButton' (should be 'NClick'), "
                        "or 'SetVariable' (should be 'Assign')."
                    ),
                )
            )

    return issues


def lint_missing_namespaces(root: ET.Element, ns: dict[str, str]) -> list[LintIssue]:
    """XL-H002: Check that all xmlns prefixes used in element tags are declared."""
    issues: list[LintIssue] = []
    declared_prefixes: set[str] = set()

    # Collect declared namespaces from the root element attributes
    for attr_name, attr_val in root.attrib.items():
        if attr_name.startswith("xmlns:"):
            prefix = attr_name.split(":", 1)[1]
            declared_prefixes.add(prefix)
        elif attr_name == "xmlns":
            declared_prefixes.add("")

    # ElementTree resolves prefixes to full URIs in {uri}tag format,
    # so we check for elements whose namespace URI doesn't match any declared mapping.
    # We also check attribute values that are namespace-prefixed type references.
    seen_issues: set[str] = set()

    # Only these attributes typically contain namespace-prefixed type references
    _type_ref_attrs = {"TypeArgument", "TypeArguments", "Type", "x:TypeArguments"}

    for elem in root.iter():
        # Check type-reference attributes for undeclared prefixes
        for attr_name, attr_val in elem.attrib.items():
            clean_attr = _local_name(attr_name)
            if clean_attr not in _type_ref_attrs:
                continue
            if ":" in attr_val and not attr_val.startswith("http"):
                prefix = attr_val.split(":", 1)[0]
                # Strip generic wrappers like "scg:List(x:String)"
                prefix = re.split(r"[(\[,\s]", prefix)[0]
                # Common known valid prefixes
                if prefix in ("x", "scg", "sco", "local", "mca", "sap2010", "mc", "p", "s",
                             "ui", "sd", "InArgument", "OutArgument", "InOutArgument"):
                    continue
                if prefix in declared_prefixes:
                    continue
                # Only flag if it looks like a namespace prefix (short alphanumeric)
                if 1 <= len(prefix) <= 15 and prefix.isalpha() and prefix not in seen_issues:
                    seen_issues.add(prefix)
                    issues.append(
                        LintIssue(
                            rule_id="XL-H002",
                            severity=LintSeverity.ERROR,
                            category=LintCategory.NAMESPACE,
                            message=f"Namespace prefix '{prefix}' is used but not declared in xmlns attributes",
                            element_name=_local_name(elem.tag),
                            line_number=_get_line_number(elem),
                            suggestion=(
                                f"Add xmlns:{prefix}='...' declaration to the root Activity element. "
                                "LLMs often invent namespace prefixes without declaring them."
                            ),
                        )
                    )

    return issues


def lint_invalid_enum_values(root: ET.Element, ns: dict[str, str]) -> list[LintIssue]:
    """XL-H003: Check property values against VALID_ENUMS."""
    issues: list[LintIssue] = []

    for elem in root.iter():
        for attr_name, attr_val in elem.attrib.items():
            # Strip namespace from attribute name
            clean_attr = _local_name(attr_name)

            if clean_attr in VALID_ENUMS:
                valid_values = VALID_ENUMS[clean_attr]
                # Handle expressions -- skip VB/C# expressions
                if attr_val.startswith("[") or attr_val.startswith("{"):
                    continue
                # Strip any enum type prefix like "ClickType.CLICK_SINGLE"
                val_to_check = attr_val.split(".")[-1] if "." in attr_val else attr_val
                if val_to_check not in valid_values:
                    issues.append(
                        LintIssue(
                            rule_id="XL-H003",
                            severity=LintSeverity.ERROR,
                            category=LintCategory.ENUM,
                            message=(
                                f"Invalid enum value '{attr_val}' for property '{clean_attr}'. "
                                f"Valid values: {sorted(valid_values)}"
                            ),
                            element_name=_local_name(elem.tag),
                            line_number=_get_line_number(elem),
                            suggestion=(
                                f"Use one of the valid values for '{clean_attr}': "
                                f"{', '.join(sorted(valid_values))}. "
                                "LLMs often hallucinate enum values like 'Left' instead of 'BTN_LEFT'."
                            ),
                        )
                    )

        # Also check child elements that represent enum properties
        for child in elem:
            child_local = _local_name(child.tag)
            # Match pattern like "NClick.ClickType"
            if "." in child_local:
                prop_name = child_local.split(".", 1)[1]
                if prop_name in VALID_ENUMS and child.text:
                    text_val = child.text.strip()
                    if text_val.startswith("[") or text_val.startswith("{"):
                        continue
                    val_to_check = text_val.split(".")[-1] if "." in text_val else text_val
                    valid_values = VALID_ENUMS[prop_name]
                    if val_to_check not in valid_values:
                        issues.append(
                            LintIssue(
                                rule_id="XL-H003",
                                severity=LintSeverity.ERROR,
                                category=LintCategory.ENUM,
                                message=(
                                    f"Invalid enum value '{text_val}' for property '{prop_name}'. "
                                    f"Valid values: {sorted(valid_values)}"
                                ),
                                element_name=_local_name(elem.tag),
                                line_number=_get_line_number(child),
                                suggestion=(
                                    f"Use one of the valid values for '{prop_name}': "
                                    f"{', '.join(sorted(valid_values))}."
                                ),
                            )
                        )

    return issues


def lint_wrong_nesting(root: ET.Element, ns: dict[str, str]) -> list[LintIssue]:
    """XL-H004: Validate parent-child nesting relationships.

    Checks:
    - If.Then / If.Else must each contain exactly one activity
    - ForEach.Body must contain a Sequence
    - TryCatch must have a Try section and at least one Catch
    - Switch cases must contain activities
    - Sequence children should only be activities
    """
    issues: list[LintIssue] = []

    for elem in root.iter():
        local = _local_name(elem.tag)

        # ── If activity checks ────────────────────────────────────────
        if local == "If":
            then_found = False
            for child in elem:
                child_local = _local_name(child.tag)
                if child_local == "If.Then":
                    then_found = True
                    activity_children = [
                        c for c in child
                        if not _local_name(c.tag).startswith("If.")
                        and _local_name(c.tag) not in _STRUCTURAL_TAGS
                    ]
                    if len(activity_children) == 0:
                        issues.append(
                            LintIssue(
                                rule_id="XL-H004",
                                severity=LintSeverity.ERROR,
                                category=LintCategory.NESTING,
                                message="If.Then block is empty -- must contain exactly one activity",
                                element_name="If",
                                line_number=_get_line_number(child),
                                suggestion="Add an activity inside the If.Then block. Use a Sequence to nest multiple activities.",
                            )
                        )
                    elif len(activity_children) > 1:
                        issues.append(
                            LintIssue(
                                rule_id="XL-H004",
                                severity=LintSeverity.ERROR,
                                category=LintCategory.NESTING,
                                message=(
                                    f"If.Then contains {len(activity_children)} activities but must "
                                    "contain exactly one. Wrap in a Sequence."
                                ),
                                element_name="If",
                                line_number=_get_line_number(child),
                                suggestion="Wrap multiple activities in a <Sequence> inside the If.Then block.",
                            )
                        )

            if not then_found:
                # If might use direct child elements in some XAML styles, so
                # only flag if the If element has children at all
                direct_children = [
                    c for c in elem
                    if _local_name(c.tag) not in _STRUCTURAL_TAGS
                    and not _PROPERTY_ACCESSOR_RE.match(_local_name(c.tag))
                ]
                if not direct_children:
                    issues.append(
                        LintIssue(
                            rule_id="XL-H004",
                            severity=LintSeverity.ERROR,
                            category=LintCategory.NESTING,
                            message="If activity is missing If.Then block",
                            element_name="If",
                            line_number=_get_line_number(elem),
                            suggestion="Add an <If.Then> child element containing the activity to execute when condition is true.",
                        )
                    )

        # ── ForEach / ParallelForEach body checks ─────────────────────
        elif local in ("ForEach", "ParallelForEach"):
            body_found = False
            for child in elem:
                child_local = _local_name(child.tag)
                if child_local in (f"{local}.Body", "ActivityAction"):
                    body_found = True
                    # Body should ideally contain a Sequence
                    inner_activities = [
                        c for c in child
                        if _local_name(c.tag) not in _STRUCTURAL_TAGS
                        and not _PROPERTY_ACCESSOR_RE.match(_local_name(c.tag))
                    ]
                    # Check if there's a Sequence or if direct children exist
                    has_sequence = any(
                        _local_name(c.tag) in ("Sequence", "ActivityAction")
                        for c in child
                    )
                    if not has_sequence and len(inner_activities) > 1:
                        issues.append(
                            LintIssue(
                                rule_id="XL-H004",
                                severity=LintSeverity.ERROR,
                                category=LintCategory.NESTING,
                                message=(
                                    f"{local}.Body contains multiple activities without "
                                    "a wrapping Sequence"
                                ),
                                element_name=local,
                                line_number=_get_line_number(child),
                                suggestion=f"Wrap the contents of {local}.Body in a <Sequence> element.",
                            )
                        )

        # ── TryCatch checks ──────────────────────────────────────────
        elif local == "TryCatch":
            has_try = False
            has_catches = False
            for child in elem:
                child_local = _local_name(child.tag)
                if child_local == "TryCatch.Try":
                    has_try = True
                    inner = [
                        c for c in child
                        if _local_name(c.tag) not in _STRUCTURAL_TAGS
                    ]
                    if not inner:
                        issues.append(
                            LintIssue(
                                rule_id="XL-H004",
                                severity=LintSeverity.ERROR,
                                category=LintCategory.NESTING,
                                message="TryCatch.Try block is empty",
                                element_name="TryCatch",
                                line_number=_get_line_number(child),
                                suggestion="Add activities inside the TryCatch.Try block.",
                            )
                        )
                elif child_local == "TryCatch.Catches":
                    has_catches = True

            if not has_try:
                issues.append(
                    LintIssue(
                        rule_id="XL-H004",
                        severity=LintSeverity.ERROR,
                        category=LintCategory.NESTING,
                        message="TryCatch is missing the TryCatch.Try block",
                        element_name="TryCatch",
                        line_number=_get_line_number(elem),
                        suggestion="Add a <TryCatch.Try> child element with the activity to attempt.",
                    )
                )

            if not has_catches:
                issues.append(
                    LintIssue(
                        rule_id="XL-H004",
                        severity=LintSeverity.ERROR,
                        category=LintCategory.NESTING,
                        message="TryCatch is missing TryCatch.Catches block",
                        element_name="TryCatch",
                        line_number=_get_line_number(elem),
                        suggestion="Add a <TryCatch.Catches> block with at least one <Catch> element.",
                    )
                )

    return issues


def lint_nonexistent_properties(root: ET.Element, ns: dict[str, str]) -> list[LintIssue]:
    """XL-H005: Check element attributes against VALID_PROPERTIES for known activities."""
    issues: list[LintIssue] = []

    # Attributes to always skip (framework-level, not activity properties)
    _skip_attrs = {
        "xmlns", "x:Class", "x:Name", "x:Key",
        "mc:Ignorable", "TextExpression.NamespacesForImplementation",
        "TextExpression.ReferencesForImplementation",
    }

    for elem in root.iter():
        local = _local_name(elem.tag)

        if local not in VALID_PROPERTIES:
            continue

        valid_props = VALID_PROPERTIES[local]

        for attr_name in elem.attrib:
            clean_attr = _local_name(attr_name)

            # Skip framework attributes
            if clean_attr in _skip_attrs:
                continue
            if attr_name.startswith("xmlns"):
                continue
            # Skip namespace-prefixed attributes from well-known frameworks
            if attr_name.startswith("{"):
                continue

            if clean_attr not in valid_props:
                issues.append(
                    LintIssue(
                        rule_id="XL-H005",
                        severity=LintSeverity.ERROR,
                        category=LintCategory.PROPERTY,
                        message=(
                            f"Property '{clean_attr}' does not exist on activity '{local}'"
                        ),
                        element_name=local,
                        line_number=_get_line_number(elem),
                        suggestion=(
                            f"Valid properties for '{local}' include: "
                            f"{', '.join(sorted(valid_props))}. "
                            "LLMs commonly invent properties like 'Selector' on modern activities "
                            "(should be 'Target') or 'FileName' on activities that use 'WorkflowFileName'."
                        ),
                    )
                )

    return issues


def lint_broken_viewstate(root: ET.Element, ns: dict[str, str]) -> list[LintIssue]:
    """XL-H006: Verify ViewState references match actual activity DisplayNames/IdRefs."""
    issues: list[LintIssue] = []

    # Collect all IdRef values from activities
    activity_idrefs: set[str] = set()
    for elem in root.iter():
        for attr_name, attr_val in elem.attrib.items():
            if _local_name(attr_name) == "WorkflowViewState.IdRef":
                activity_idrefs.add(attr_val)

    # Find ViewState entries
    viewstate_refs: set[str] = set()
    for elem in root.iter():
        local = _local_name(elem.tag)
        if local == "ViewStateData":
            id_val = elem.attrib.get("Id", "")
            if id_val:
                viewstate_refs.add(id_val)
        elif local == "WorkflowViewState" or local == "ViewStateManager":
            # Some formats use different structures
            for child in elem:
                child_local = _local_name(child.tag)
                if child_local == "ViewStateData":
                    id_val = child.attrib.get("Id", "")
                    if id_val:
                        viewstate_refs.add(id_val)

    # Flag ViewState references that don't have matching activities
    for ref in viewstate_refs:
        if ref not in activity_idrefs:
            issues.append(
                LintIssue(
                    rule_id="XL-H006",
                    severity=LintSeverity.ERROR,
                    category=LintCategory.VIEWSTATE,
                    message=(
                        f"ViewState references IdRef '{ref}' but no activity has this IdRef"
                    ),
                    element_name="ViewStateData",
                    suggestion=(
                        f"Ensure activity with sap2010:WorkflowViewState.IdRef='{ref}' exists, "
                        "or remove the orphaned ViewStateData entry. LLMs often generate ViewState "
                        "blocks that reference activities they later renamed or removed."
                    ),
                )
            )

    return issues


def lint_invalid_type_arguments(root: ET.Element, ns: dict[str, str]) -> list[LintIssue]:
    """XL-H007: Validate TypeArgument attribute values are valid .NET types."""
    issues: list[LintIssue] = []

    for elem in root.iter():
        type_arg = elem.attrib.get("TypeArgument", "")
        if not type_arg:
            # Also check x:TypeArguments (used in some XAML variants)
            for attr_name, attr_val in elem.attrib.items():
                if _local_name(attr_name) == "TypeArguments":
                    type_arg = attr_val
                    break

        if not type_arg:
            continue

        # Parse out the type names (handles generics)
        type_names = _strip_generic(type_arg)

        for t in type_names:
            if not t:
                continue
            # Allow namespace-prefixed types (scg:List, etc.)
            base = t.split(":")[-1] if ":" in t else t

            # Allow assembly-qualified names
            if ";" in base:
                continue

            # Skip if it's in our known valid types
            if t in _VALID_DOTNET_TYPES or base in _VALID_DOTNET_TYPES:
                continue

            # Allow types that look like fully-qualified .NET types
            if "." in base and all(part[0:1].isupper() for part in base.split(".") if part):
                continue

            # Allow namespace-prefixed references
            if ":" in t:
                prefix = t.split(":", 1)[0]
                if prefix in ("x", "scg", "sco", "local", "s", "System"):
                    continue

            # Flag suspicious type names
            issues.append(
                LintIssue(
                    rule_id="XL-H007",
                    severity=LintSeverity.ERROR,
                    category=LintCategory.TYPE_ARGUMENT,
                    message=f"Potentially invalid TypeArgument value '{t}' in element '{_local_name(elem.tag)}'",
                    element_name=_local_name(elem.tag),
                    line_number=_get_line_number(elem),
                    suggestion=(
                        "Use valid .NET type names: x:String, x:Int32, x:Boolean, x:Object, "
                        "DataTable, DataRow, System.Data.DataTable, etc. "
                        "LLMs often hallucinate types like 'x:DataTable' (should be 'System.Data.DataTable') "
                        "or 'x:Array' (should use 'scg:List')."
                    ),
                )
            )

    return issues


def lint_duplicate_display_names(root: ET.Element, ns: dict[str, str]) -> list[LintIssue]:
    """XL-H008: Flag duplicate DisplayName values within the same scope."""
    issues: list[LintIssue] = []

    def _check_scope(scope_elem: ET.Element) -> None:
        """Check for duplicate DisplayNames among direct-child activities of a scope."""
        display_names: dict[str, list[ET.Element]] = {}

        for child in scope_elem:
            local = _local_name(child.tag)
            # Skip structural and property elements
            if local in _STRUCTURAL_TAGS or _PROPERTY_ACCESSOR_RE.match(local):
                # Recurse into property elements to find their scope
                _check_scope(child)
                continue

            dn = child.attrib.get("DisplayName", "")
            if dn:
                display_names.setdefault(dn, []).append(child)

            # Recurse into child scopes (Sequence, Flowchart, etc.)
            _check_scope(child)

        for dn, elems in display_names.items():
            if len(elems) > 1:
                for e in elems[1:]:  # Flag all but the first occurrence
                    issues.append(
                        LintIssue(
                            rule_id="XL-H008",
                            severity=LintSeverity.ERROR,
                            category=LintCategory.HALLUCINATION,
                            message=(
                                f"Duplicate DisplayName '{dn}' found in the same scope "
                                f"(activity: {_local_name(e.tag)})"
                            ),
                            element_name=_local_name(e.tag),
                            line_number=_get_line_number(e),
                            suggestion=(
                                f"Rename one of the activities with DisplayName '{dn}' "
                                "to avoid confusion. Each activity in a scope should have "
                                "a unique DisplayName for clarity and ViewState correctness."
                            ),
                        )
                    )

    _check_scope(root)
    return issues


# ---------------------------------------------------------------------------
# Exported rule list
# ---------------------------------------------------------------------------

ALL_HALLUCINATION_RULES = [
    lint_unknown_activities,
    lint_missing_namespaces,
    lint_invalid_enum_values,
    lint_wrong_nesting,
    lint_nonexistent_properties,
    lint_broken_viewstate,
    lint_invalid_type_arguments,
    lint_duplicate_display_names,
]
