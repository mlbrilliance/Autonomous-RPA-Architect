"""Best-practice rules for UiPath XAML (INFO severity).

Detects patterns that are technically valid but indicate poor practices:
hardcoded URLs, missing logging, missing error handling, C# in VB.NET
contexts, placeholder selectors, etc.
"""

from __future__ import annotations

import re
import xml.etree.ElementTree as ET

from rpa_architect.xaml_lint.lint_document import LintDocument
from rpa_architect.xaml_lint.models import LintCategory, LintIssue, LintSeverity
from rpa_architect.xaml_lint.rule import ContentKind, rule

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_URL_RE = re.compile(r"https?://[^\s\"'<>]+", re.IGNORECASE)

_CSHARP_PATTERNS = [
    # != operator (VB uses <>)
    re.compile(r"(?<!\<)\!\="),
    # && and || (VB uses AndAlso / OrElse)
    re.compile(r"\&\&"),
    re.compile(r"\|\|"),
    # var keyword
    re.compile(r"\bvar\s+\w+\s*="),
    # null (VB uses Nothing)
    re.compile(r"\bnull\b"),
    # C# string interpolation $"..."
    re.compile(r'\$"'),
    # => lambda (VB uses Function/Sub)
    re.compile(r"\=\>"),
    # // comments (VB uses ')
    re.compile(r"//\s"),
    # C# using statement
    re.compile(r"\busing\s*\("),
    # typeof (VB uses GetType)
    re.compile(r"\btypeof\s*\("),
    # new keyword with type (VB uses New)
    re.compile(r"\bnew\s+[A-Z]"),
    # C# ternary operator ? :
    re.compile(r"\w+\s*\?\s*\w+\s*:\s*\w+"),
]

_PLACEHOLDER_PATTERNS = re.compile(
    r"(TODO|PLACEHOLDER|FIXME|XXX|CHANGEME|\{\{[^}]*\}\}|<REPLACE>|\[REPLACE\]"
    r"|ENTER_VALUE_HERE|YOUR_.*_HERE|FILL_IN)",
    re.IGNORECASE,
)

_MAGIC_DELAY_RE = re.compile(
    r"TimeSpan\.From(?:Seconds|Milliseconds|Minutes)\s*\(\s*(\d+)\s*\)",
    re.IGNORECASE,
)

# Well-known UiPath documentation / schema URLs that are not hardcoded config values
_ALLOWED_URL_PREFIXES = (
    "http://schemas.",
    "https://schemas.",
    "http://www.w3.org/",
    "http://schemas.microsoft.com/",
    "http://schemas.uipath.com/",
    "http://schemas.openxmlformats.org/",
    "clr-namespace:",
)

# Activities that perform HTTP/API calls
_API_ACTIVITIES = {"HttpClient", "DeserializeJson", "SerializeJson", "InvokeMethod"}


def _local_name(tag: str) -> str:
    if tag.startswith("{"):
        return tag.split("}", 1)[1]
    return tag


def _is_expression(value: str) -> bool:
    stripped = value.strip()
    return stripped.startswith("[") or stripped.startswith("{")


def _has_activity(root: ET.Element, activity_name: str) -> bool:
    """Check if an activity type exists anywhere in the tree."""
    for elem in root.iter():
        if _local_name(elem.tag) == activity_name:
            return True
    return False


def _is_inside_activity(
    elem: ET.Element, parent_map: dict[ET.Element, ET.Element], activity_name: str
) -> bool:
    """Check if elem is nested inside an activity of the given type."""
    current = elem
    while current in parent_map:
        current = parent_map[current]
        if _local_name(current.tag) == activity_name:
            return True
    return False


def _build_parent_map(root: ET.Element) -> dict[ET.Element, ET.Element]:
    """Build a child -> parent mapping for the element tree."""
    parent_map: dict[ET.Element, ET.Element] = {}
    for parent in root.iter():
        for child in parent:
            parent_map[child] = parent
    return parent_map


# ---------------------------------------------------------------------------
# Rules
# ---------------------------------------------------------------------------


@rule(
    id="XL-B001",
    severity=LintSeverity.INFO,
    category=LintCategory.CONFIG,
    applies_to=ContentKind.XAML,
)
def lint_hardcoded_urls(doc: LintDocument) -> list[LintIssue]:
    """XL-B001: Flag http:// or https:// URLs that should reference Config.xlsx."""
    root = doc.tree
    if root is None:
        return []
    issues: list[LintIssue] = []
    seen_urls: set[str] = set()

    for elem in root.iter():
        local = _local_name(elem.tag)

        # Collect all text values from attributes and text content
        values: list[str] = []
        for attr_val in elem.attrib.values():
            values.append(attr_val)
        if elem.text and elem.text.strip():
            values.append(elem.text.strip())

        for value in values:
            # Skip expressions
            if _is_expression(value):
                continue

            for match in _URL_RE.finditer(value):
                url = match.group()
                # Skip schema/namespace URLs
                if any(url.startswith(p) for p in _ALLOWED_URL_PREFIXES):
                    continue
                if url in seen_urls:
                    continue
                seen_urls.add(url)

                issues.append(
                    LintIssue(
                        rule_id="XL-B001",
                        severity=LintSeverity.INFO,
                        category=LintCategory.CONFIG,
                        message=f"Hardcoded URL '{url[:80]}' should be stored in Config.xlsx or Orchestrator Assets",
                        element_name=local,
                        line_number=doc.line_of(elem),
                        suggestion=(
                            "Move URLs to the Config.xlsx Settings sheet and reference them via "
                            'in_Config("SettingName"). Hardcoded URLs break when environments change.'
                        ),
                    )
                )

    return issues


@rule(
    id="XL-B002",
    severity=LintSeverity.INFO,
    category=LintCategory.BEST_PRACTICE,
    applies_to=ContentKind.XAML,
)
def lint_missing_log_messages(doc: LintDocument) -> list[LintIssue]:
    """XL-B002: Warn if workflow has no LogMessage activities."""
    root = doc.tree
    if root is None:
        return []
    issues: list[LintIssue] = []

    if not _has_activity(root, "LogMessage"):
        issues.append(
            LintIssue(
                rule_id="XL-B002",
                severity=LintSeverity.INFO,
                category=LintCategory.BEST_PRACTICE,
                message="Workflow contains no LogMessage activities",
                element_name="Workflow",
                suggestion=(
                    "Add LogMessage activities at key points (start, end, before/after "
                    "critical operations) for observability and debugging. At minimum, log "
                    "workflow start and completion."
                ),
            )
        )

    return issues


@rule(
    id="XL-B003",
    severity=LintSeverity.INFO,
    category=LintCategory.BEST_PRACTICE,
    applies_to=ContentKind.XAML,
)
def lint_missing_retry_scope(doc: LintDocument) -> list[LintIssue]:
    """XL-B003: Flag HttpClient/API calls not wrapped in RetryScope."""
    root = doc.tree
    if root is None:
        return []
    issues: list[LintIssue] = []
    parent_map = _build_parent_map(root)

    for elem in root.iter():
        local = _local_name(elem.tag)

        if local in _API_ACTIVITIES:
            if not _is_inside_activity(elem, parent_map, "RetryScope"):
                display_name = elem.attrib.get("DisplayName", local)
                issues.append(
                    LintIssue(
                        rule_id="XL-B003",
                        severity=LintSeverity.INFO,
                        category=LintCategory.BEST_PRACTICE,
                        message=(
                            f"API activity '{display_name}' ({local}) is not wrapped "
                            "in a RetryScope"
                        ),
                        element_name=local,
                        line_number=doc.line_of(elem),
                        suggestion=(
                            "Wrap HTTP/API calls in a RetryScope to handle transient failures "
                            "(network timeouts, 503 errors, rate limits). Set NumberOfRetries=3 "
                            "and RetryInterval=00:00:05."
                        ),
                    )
                )

    return issues


@rule(
    id="XL-B004",
    severity=LintSeverity.INFO,
    category=LintCategory.BEST_PRACTICE,
    applies_to=ContentKind.XAML,
)
def lint_missing_try_catch(doc: LintDocument) -> list[LintIssue]:
    """XL-B004: Flag top-level workflow without TryCatch."""
    root = doc.tree
    if root is None:
        return []
    issues: list[LintIssue] = []

    # Find the main workflow body (first Sequence or Flowchart under Activity)
    main_body: ET.Element | None = None
    for elem in root.iter():
        local = _local_name(elem.tag)
        if local in ("Sequence", "Flowchart", "StateMachine"):
            main_body = elem
            break

    if main_body is None:
        return issues

    # Check if the main body has a TryCatch as a direct child or is itself one
    has_try_catch = False
    if _local_name(main_body.tag) == "TryCatch":
        has_try_catch = True
    else:
        for child in main_body:
            if _local_name(child.tag) == "TryCatch":
                has_try_catch = True
                break

    if not has_try_catch:
        issues.append(
            LintIssue(
                rule_id="XL-B004",
                severity=LintSeverity.INFO,
                category=LintCategory.BEST_PRACTICE,
                message="Top-level workflow body does not contain a TryCatch",
                element_name=_local_name(main_body.tag),
                line_number=doc.line_of(main_body),
                suggestion=(
                    "Wrap the main workflow logic in a TryCatch to handle unexpected errors. "
                    "The Catch block should log the error and optionally take a screenshot "
                    "for debugging."
                ),
            )
        )

    return issues


@rule(
    id="XL-B005",
    severity=LintSeverity.INFO,
    category=LintCategory.BEST_PRACTICE,
    applies_to=ContentKind.XAML,
)
def lint_csharp_in_vbnet(doc: LintDocument) -> list[LintIssue]:
    """XL-B005: Detect C# syntax in VB.NET expression fields.

    UiPath projects can be either VB.NET or C#.  We check the root element
    for language indicators and then scan expressions accordingly.
    """
    root = doc.tree
    if root is None:
        return []
    issues: list[LintIssue] = []

    # Determine the project language
    # C# projects typically have CSharpValue / CSharpReference; VB.NET uses VisualBasicValue
    has_vb = False
    has_csharp_project = False

    for elem in root.iter():
        local = _local_name(elem.tag)
        if local in (
            "VisualBasicSettings",
            "VisualBasicValue",
            "VisualBasicReference",
            "VisualBasicImport",
        ):
            has_vb = True
        elif local in ("CSharpValue", "CSharpReference"):
            has_csharp_project = True

    # If it's a C# project, skip this rule
    if has_csharp_project and not has_vb:
        return issues

    # If we can't determine, assume VB.NET (more common in UiPath)
    # Scan expression attributes and text content for C# patterns
    for elem in root.iter():
        local = _local_name(elem.tag)

        # Collect expression values
        expressions: list[tuple[str, str]] = []

        # Check common expression attributes
        for attr_name in ("Condition", "Value", "To", "Expression", "Text"):
            val = elem.attrib.get(attr_name, "")
            if val:
                expressions.append((attr_name, val))

        # Check text content of expression elements
        if elem.text and elem.text.strip():
            parent_local = _local_name(elem.tag)
            if parent_local in ("VisualBasicValue", "Condition", "Expression"):
                expressions.append(("text", elem.text.strip()))

        for source, expr in expressions:
            # Skip very short expressions
            if len(expr) < 3:
                continue
            # Skip VB.NET expressions enclosed in brackets
            if expr.startswith("[") and expr.endswith("]"):
                continue

            for pattern in _CSHARP_PATTERNS:
                match = pattern.search(expr)
                if match:
                    issues.append(
                        LintIssue(
                            rule_id="XL-B005",
                            severity=LintSeverity.INFO,
                            category=LintCategory.BEST_PRACTICE,
                            message=(
                                f"Possible C# syntax '{match.group()}' detected in VB.NET "
                                f"expression on '{local}.{source}': \"{expr[:60]}\""
                            ),
                            element_name=local,
                            line_number=doc.line_of(elem),
                            suggestion=(
                                "This project uses VB.NET expressions. Replace C# syntax: "
                                "!= -> <>, && -> AndAlso, || -> OrElse, null -> Nothing, "
                                'var -> Dim, // -> \', $"" -> String.Format().'
                            ),
                        )
                    )
                    break  # One issue per expression is enough

    return issues


@rule(
    id="XL-B006",
    severity=LintSeverity.INFO,
    category=LintCategory.BEST_PRACTICE,
    applies_to=ContentKind.XAML,
)
def lint_placeholder_selectors(doc: LintDocument) -> list[LintIssue]:
    """XL-B006: Flag selectors containing TODO, PLACEHOLDER, or {{}} markers."""
    root = doc.tree
    if root is None:
        return []
    issues: list[LintIssue] = []

    for elem in root.iter():
        local = _local_name(elem.tag)

        # Check all attributes and child elements for selector content
        values_to_check: list[tuple[str, str]] = []

        for attr_name, attr_val in elem.attrib.items():
            clean = _local_name(attr_name)
            if clean in ("Selector", "Target", "SearchProperties"):
                values_to_check.append((clean, attr_val))

        # Check child elements with selector-like tag names
        for child in elem:
            child_local = _local_name(child.tag)
            if "Selector" in child_local or "Target" in child_local:
                if child.text and child.text.strip():
                    values_to_check.append((child_local, child.text.strip()))
                # Check nested children too (selectors can be deeply nested)
                for sub in child.iter():
                    if sub.text and sub.text.strip():
                        values_to_check.append((_local_name(sub.tag), sub.text.strip()))

        for source, value in values_to_check:
            match = _PLACEHOLDER_PATTERNS.search(value)
            if match:
                issues.append(
                    LintIssue(
                        rule_id="XL-B006",
                        severity=LintSeverity.INFO,
                        category=LintCategory.BEST_PRACTICE,
                        message=(
                            f"Placeholder marker '{match.group()}' found in {source} "
                            f"on element '{local}'"
                        ),
                        element_name=local,
                        line_number=doc.line_of(elem),
                        suggestion=(
                            "Replace placeholder selectors with actual UI selectors. "
                            "Use UiPath's Indicate on Screen or the Selector Builder to capture "
                            "valid selectors from the target application."
                        ),
                    )
                )

    return issues


@rule(
    id="XL-B007",
    severity=LintSeverity.INFO,
    category=LintCategory.BEST_PRACTICE,
    applies_to=ContentKind.XAML,
)
def lint_empty_catch_blocks(doc: LintDocument) -> list[LintIssue]:
    """XL-B007: Flag TryCatch with empty Catch blocks (swallowed exceptions)."""
    root = doc.tree
    if root is None:
        return []
    issues: list[LintIssue] = []

    structural = {
        "Variable",
        "Property",
        "Argument",
        "TextExpression",
        "VisualBasicSettings",
        "VisualBasicValue",
        "VisualBasicReference",
    }

    for elem in root.iter():
        local = _local_name(elem.tag)

        if local == "Catch":
            # Check if the Catch has any actual activity children
            has_activity = False

            for child in elem:
                child_local = _local_name(child.tag)
                # Look inside Catch.Body (ActivityAction)
                if child_local in ("ActivityAction", "Catch.Body"):
                    for inner in child:
                        inner_local = _local_name(inner.tag)
                        if inner_local not in structural and not inner_local.startswith(
                            "DelegateInArgument"
                        ):
                            # Check if the inner element has children (actual activities)
                            inner_children = [
                                c for c in inner if _local_name(c.tag) not in structural
                            ]
                            if inner_children or inner_local not in ("Sequence",):
                                has_activity = True
                                break
                            # An empty Sequence still counts as empty
                elif child_local not in structural and not child_local.startswith(
                    "DelegateInArgument"
                ):
                    has_activity = True
                    break

            if not has_activity:
                exception_type = elem.attrib.get("TypeArgument", "Exception")
                # Also check x:TypeArguments
                if not exception_type or exception_type == "Exception":
                    for attr_name, attr_val in elem.attrib.items():
                        if _local_name(attr_name) == "TypeArguments":
                            exception_type = attr_val
                            break

                issues.append(
                    LintIssue(
                        rule_id="XL-B007",
                        severity=LintSeverity.INFO,
                        category=LintCategory.BEST_PRACTICE,
                        message=f"Empty Catch block for {exception_type} -- exception is swallowed silently",
                        element_name="Catch",
                        line_number=doc.line_of(elem),
                        suggestion=(
                            "Add at least a LogMessage activity in the Catch block to record "
                            "the exception. Silently swallowing exceptions makes debugging "
                            "extremely difficult. Use exception.Message and exception.StackTrace."
                        ),
                    )
                )

    return issues


@rule(
    id="XL-B008",
    severity=LintSeverity.INFO,
    category=LintCategory.CONFIG,
    applies_to=ContentKind.XAML,
)
def lint_magic_numbers(doc: LintDocument) -> list[LintIssue]:
    """XL-B008: Flag numeric Delay/timeout values that should be Config-driven."""
    root = doc.tree
    if root is None:
        return []
    issues: list[LintIssue] = []

    for elem in root.iter():
        local = _local_name(elem.tag)

        # Check Delay activities
        if local == "Delay":
            duration = elem.attrib.get("Duration", "")
            if duration and not _is_expression(duration):
                # Check if it's a literal TimeSpan
                if re.match(r"^\d{2}:\d{2}:\d{2}", duration):
                    issues.append(
                        LintIssue(
                            rule_id="XL-B008",
                            severity=LintSeverity.INFO,
                            category=LintCategory.CONFIG,
                            message=f"Hardcoded Delay duration '{duration}' should be Config-driven",
                            element_name=local,
                            line_number=doc.line_of(elem),
                            suggestion=(
                                "Store delay/timeout values in Config.xlsx and reference them as "
                                'TimeSpan.FromSeconds(CDbl(in_Config("DelaySeconds"))). '
                                "Hardcoded delays make tuning difficult across environments."
                            ),
                        )
                    )

        # Check TimeoutMS attributes on any activity
        timeout = elem.attrib.get("TimeoutMS", "")
        if timeout and not _is_expression(timeout):
            try:
                timeout_val = int(timeout)
                if timeout_val > 0:
                    issues.append(
                        LintIssue(
                            rule_id="XL-B008",
                            severity=LintSeverity.INFO,
                            category=LintCategory.CONFIG,
                            message=(
                                f"Hardcoded TimeoutMS={timeout_val} on '{local}' "
                                "should be Config-driven"
                            ),
                            element_name=local,
                            line_number=doc.line_of(elem),
                            suggestion=(
                                "Store timeout values in Config.xlsx. Use "
                                'CInt(in_Config("TimeoutMS")) to reference them. '
                                "Different environments may need different timeout values."
                            ),
                        )
                    )
            except ValueError:
                pass

        # Check for magic numbers in expressions
        for attr_name in ("Value", "Text", "Expression"):
            val = elem.attrib.get(attr_name, "")
            if val:
                match = _MAGIC_DELAY_RE.search(val)
                if match:
                    number = match.group(1)
                    issues.append(
                        LintIssue(
                            rule_id="XL-B008",
                            severity=LintSeverity.INFO,
                            category=LintCategory.CONFIG,
                            message=(
                                f"Magic number {number} in time expression on '{local}' "
                                "should be Config-driven"
                            ),
                            element_name=local,
                            line_number=doc.line_of(elem),
                            suggestion=(
                                f"Replace the literal {number} with a Config.xlsx reference. "
                                'Example: TimeSpan.FromSeconds(CDbl(in_Config("WaitSeconds"))).'
                            ),
                        )
                    )

    return issues


# Classic → Modern activity mapping (deprecated in Modern Design Experience)
_CLASSIC_TO_MODERN: dict[str, str] = {
    "Click": "NClick",
    "TypeInto": "NTypeInto",
    "GetText": "NGetText",
    "SetText": "NTypeInto",
    "SelectItem": "NSelectItem",
    "Check": "NCheck",
    "Hover": "NHover",
    "DoubleClick": "NClick (ClickType=CLICK_DOUBLE)",
    "SendHotkey": "NKeyboardShortcuts",
    "GetAttribute": "NGetText",
    "ElementExists": "NCheckState",
    "FindElement": "NGetText",
    "ClickImage": "NClick",
    "TypeIntoImage": "NTypeInto",
    "FindImage": "NGetText",
    "ScreenScraping": "NGetText / NExtractData",
    "DataScraping": "NExtractData",
}


@rule(
    id="XL-BP009",
    severity=LintSeverity.WARNING,
    category=LintCategory.BEST_PRACTICE,
    applies_to=ContentKind.XAML,
)
def lint_deprecated_classic_activities(doc: LintDocument) -> list[LintIssue]:
    """XL-BP009: Flag classic activities that have modern replacements.

    UiPath Studio 2025.10 strongly encourages Modern Design Experience
    activities (N-prefixed) over legacy classic activities.
    """
    root = doc.tree
    if root is None:
        return []
    issues: list[LintIssue] = []
    seen: set[str] = set()

    for elem in root.iter():
        local = _local_name(elem.tag)

        if local in _CLASSIC_TO_MODERN and local not in seen:
            seen.add(local)
            modern = _CLASSIC_TO_MODERN[local]
            display_name = elem.attrib.get("DisplayName", local)
            issues.append(
                LintIssue(
                    rule_id="XL-BP009",
                    severity=LintSeverity.WARNING,
                    category=LintCategory.BEST_PRACTICE,
                    message=(
                        f"Classic activity '{display_name}' ({local}) is deprecated "
                        f"in Modern Design Experience"
                    ),
                    element_name=local,
                    line_number=doc.line_of(elem),
                    suggestion=(
                        f"Use Modern activity '{modern}' instead of '{local}'. "
                        "Modern activities provide better reliability, unified targeting, "
                        "and are required for Object Repository integration."
                    ),
                )
            )

    return issues


# ---------------------------------------------------------------------------
# Exported rule list
# ---------------------------------------------------------------------------

# Rules are auto-registered by the @rule decorator. The legacy
# ALL_BEST_PRACTICE_RULES list has been removed.
