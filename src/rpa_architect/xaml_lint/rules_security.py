"""Security rules for UiPath XAML (WARNING severity).

Detects security issues: plaintext passwords, hardcoded secrets, credential
misuse, and connection string exposure.
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

_PASSWORD_PATTERNS = re.compile(
    r"(password|passwd|pwd|secret|apikey|api_key|api[-_]?secret|token|auth[-_]?token"
    r"|client[-_]?secret|access[-_]?key|private[-_]?key)",
    re.IGNORECASE,
)

_HARDCODED_SECRET_PATTERNS = [
    # API keys (long alphanumeric strings)
    re.compile(r"[A-Za-z0-9]{32,}", re.IGNORECASE),
    # AWS-style keys
    re.compile(r"AKIA[0-9A-Z]{16}", re.IGNORECASE),
    # Bearer tokens
    re.compile(r"Bearer\s+[A-Za-z0-9\-._~+/]+=*", re.IGNORECASE),
    # Basic auth
    re.compile(r"Basic\s+[A-Za-z0-9+/]+=+", re.IGNORECASE),
    # JWT tokens
    re.compile(r"eyJ[A-Za-z0-9\-_]+\.eyJ[A-Za-z0-9\-_]+\.[A-Za-z0-9\-_]+"),
    # Hex-encoded secrets (32+ hex chars)
    re.compile(r"[0-9a-f]{32,}", re.IGNORECASE),
]

_CONNECTION_STRING_PASSWORD_RE = re.compile(
    r"(Password|Pwd)\s*=\s*[^;\"'\s]+",
    re.IGNORECASE,
)

_SECURE_STRING_TYPE = "System.Security.SecureString"


def _local_name(tag: str) -> str:
    """Strip namespace URI from an ElementTree tag."""
    if tag.startswith("{"):
        return tag.split("}", 1)[1]
    return tag


def _is_expression(value: str) -> bool:
    """Return True if value looks like a VB.NET / C# expression rather than a literal."""
    stripped = value.strip()
    return (
        stripped.startswith("[")
        or stripped.startswith("{")
        or "." in stripped
        and not stripped.startswith("http")
        or stripped.startswith("New ")
        or "(" in stripped
    )


# ---------------------------------------------------------------------------
# Rules
# ---------------------------------------------------------------------------


@rule(
    id="XL-S001",
    severity=LintSeverity.WARNING,
    category=LintCategory.SECURITY,
    applies_to=ContentKind.XAML,
)
def lint_string_passwords(doc: LintDocument) -> list[LintIssue]:
    """XL-S001: Flag variables/arguments with password-like names typed as String instead of SecureString."""
    root = doc.tree
    if root is None:
        return []
    issues: list[LintIssue] = []

    for elem in root.iter():
        local = _local_name(elem.tag)

        # Check Variable elements
        if local == "Variable":
            var_name = elem.attrib.get("Name", "")
            var_type = elem.attrib.get("TypeArgument", "")
            # Also check x:TypeArguments
            if not var_type:
                for attr_name, attr_val in elem.attrib.items():
                    if _local_name(attr_name) == "TypeArguments":
                        var_type = attr_val
                        break

            if _PASSWORD_PATTERNS.search(var_name):
                if (
                    var_type
                    and _SECURE_STRING_TYPE not in var_type
                    and "SecureString" not in var_type
                ):
                    issues.append(
                        LintIssue(
                            rule_id="XL-S001",
                            severity=LintSeverity.WARNING,
                            category=LintCategory.SECURITY,
                            message=(
                                f"Variable '{var_name}' appears to hold sensitive data "
                                f"but is typed as '{var_type}' instead of SecureString"
                            ),
                            element_name=var_name,
                            line_number=doc.line_of(elem),
                            suggestion=(
                                f"Change the type of '{var_name}' to System.Security.SecureString. "
                                "Storing passwords as plain String keeps them in memory and makes them "
                                "visible in logs."
                            ),
                        )
                    )

        # Check InArgument / OutArgument with password-like names
        elif local in ("Property", "Member"):
            arg_name = elem.attrib.get("Name", "")
            arg_type = elem.attrib.get("Type", "")
            if _PASSWORD_PATTERNS.search(arg_name):
                if arg_type and "SecureString" not in arg_type and "String" in arg_type:
                    issues.append(
                        LintIssue(
                            rule_id="XL-S001",
                            severity=LintSeverity.WARNING,
                            category=LintCategory.SECURITY,
                            message=(
                                f"Argument '{arg_name}' appears to hold sensitive data "
                                f"but is typed as '{arg_type}' instead of SecureString"
                            ),
                            element_name=arg_name,
                            line_number=doc.line_of(elem),
                            suggestion=(
                                f"Change the type of argument '{arg_name}' to "
                                "InArgument<System.Security.SecureString> to protect sensitive data."
                            ),
                        )
                    )

    return issues


@rule(
    id="XL-S002",
    severity=LintSeverity.WARNING,
    category=LintCategory.CREDENTIAL,
    applies_to=ContentKind.XAML,
)
def lint_credential_arguments(doc: LintDocument) -> list[LintIssue]:
    """XL-S002: Flag credentials passed as workflow In arguments instead of using GetRobotCredential."""
    root = doc.tree
    if root is None:
        return []
    issues: list[LintIssue] = []

    # Collect argument names that look like credentials
    credential_args: list[tuple[str, ET.Element]] = []
    has_get_robot_credential = False

    for elem in root.iter():
        local = _local_name(elem.tag)

        if local == "GetRobotCredential":
            has_get_robot_credential = True

        # Check for InArgument properties with credential-like names
        if local in ("Property", "Member"):
            arg_name = elem.attrib.get("Name", "")
            arg_type = elem.attrib.get("Type", "")
            direction = elem.attrib.get("Direction", "In")

            if _PASSWORD_PATTERNS.search(arg_name) and "In" in (direction or arg_type):
                credential_args.append((arg_name, elem))

    # Only flag if there's no GetRobotCredential usage
    if credential_args and not has_get_robot_credential:
        for arg_name, elem in credential_args:
            issues.append(
                LintIssue(
                    rule_id="XL-S002",
                    severity=LintSeverity.WARNING,
                    category=LintCategory.CREDENTIAL,
                    message=(
                        f"Credential '{arg_name}' is passed as an In argument. "
                        "Use GetRobotCredential to retrieve credentials from Orchestrator instead."
                    ),
                    element_name=arg_name,
                    line_number=doc.line_of(elem),
                    suggestion=(
                        "Remove the credential In argument and use a GetRobotCredential activity "
                        "to retrieve the credential from Orchestrator assets. This is more secure "
                        "and allows credential rotation without modifying the workflow."
                    ),
                )
            )

    return issues


@rule(
    id="XL-S003",
    severity=LintSeverity.WARNING,
    category=LintCategory.SECURITY,
    applies_to=ContentKind.XAML,
)
def lint_hardcoded_secrets(doc: LintDocument) -> list[LintIssue]:
    """XL-S003: Flag likely hardcoded passwords, API keys, connection strings in XAML values."""
    root = doc.tree
    if root is None:
        return []
    issues: list[LintIssue] = []
    seen_values: set[str] = set()

    for elem in root.iter():
        local = _local_name(elem.tag)

        # Check attributes
        for attr_name, attr_val in elem.attrib.items():
            clean_attr = _local_name(attr_name)

            # Skip non-value attributes
            if clean_attr in ("Name", "DisplayName", "x:Class", "xmlns"):
                continue
            if attr_name.startswith("xmlns"):
                continue

            # Check if attribute name suggests a secret
            if _PASSWORD_PATTERNS.search(clean_attr):
                if attr_val and not _is_expression(attr_val) and attr_val not in seen_values:
                    seen_values.add(attr_val)
                    # Skip if it's clearly a variable reference
                    if not attr_val.startswith("$") and len(attr_val) > 2:
                        issues.append(
                            LintIssue(
                                rule_id="XL-S003",
                                severity=LintSeverity.WARNING,
                                category=LintCategory.SECURITY,
                                message=(
                                    f"Possible hardcoded secret in attribute '{clean_attr}' "
                                    f"on element '{local}'"
                                ),
                                element_name=local,
                                line_number=doc.line_of(elem),
                                suggestion=(
                                    "Never hardcode secrets in XAML. Use GetRobotCredential, "
                                    "GetRobotAsset, or Windows Credential Manager instead."
                                ),
                            )
                        )

        # Check text content for secret-like patterns
        if elem.text and elem.text.strip():
            text = elem.text.strip()
            # Skip expressions
            if _is_expression(text):
                continue

            for pattern in _HARDCODED_SECRET_PATTERNS:
                match = pattern.search(text)
                if match and match.group() not in seen_values:
                    # Filter out common false positives
                    matched = match.group()
                    if len(matched) < 20:
                        continue
                    # Skip GUIDs
                    if re.match(
                        r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}",
                        matched,
                        re.I,
                    ):
                        continue
                    # Skip things that look like XML namespace URIs
                    if matched.startswith("http"):
                        continue

                    seen_values.add(matched)
                    issues.append(
                        LintIssue(
                            rule_id="XL-S003",
                            severity=LintSeverity.WARNING,
                            category=LintCategory.SECURITY,
                            message=(
                                f"Possible hardcoded secret detected in element '{local}': "
                                f"'{matched[:20]}...'"
                            ),
                            element_name=local,
                            line_number=doc.line_of(elem),
                            suggestion=(
                                "Move secrets to Orchestrator Assets or Windows Credential Manager. "
                                "Hardcoded secrets in XAML are visible in source control and logs."
                            ),
                        )
                    )
                    break  # One issue per element is enough

    return issues


@rule(
    id="XL-S004",
    severity=LintSeverity.WARNING,
    category=LintCategory.SECURITY,
    applies_to=ContentKind.XAML,
)
def lint_plaintext_connection_strings(doc: LintDocument) -> list[LintIssue]:
    """XL-S004: Flag database connection strings with plaintext passwords."""
    root = doc.tree
    if root is None:
        return []
    issues: list[LintIssue] = []

    for elem in root.iter():
        local = _local_name(elem.tag)

        # Check all attribute values and text content
        values_to_check: list[tuple[str, str]] = []

        for attr_name, attr_val in elem.attrib.items():
            values_to_check.append((_local_name(attr_name), attr_val))

        if elem.text and elem.text.strip():
            values_to_check.append(("text_content", elem.text.strip()))

        for source, value in values_to_check:
            if _is_expression(value):
                continue

            # Look for connection string patterns with embedded passwords
            if _CONNECTION_STRING_PASSWORD_RE.search(value):
                # Verify it looks like a connection string
                conn_indicators = [
                    "Server=",
                    "Data Source=",
                    "Initial Catalog=",
                    "Database=",
                    "Provider=",
                    "Driver=",
                    "DSN=",
                ]
                if any(ind.lower() in value.lower() for ind in conn_indicators):
                    issues.append(
                        LintIssue(
                            rule_id="XL-S004",
                            severity=LintSeverity.WARNING,
                            category=LintCategory.SECURITY,
                            message=(
                                f"Connection string in '{source}' on element '{local}' "
                                "contains a plaintext password"
                            ),
                            element_name=local,
                            line_number=doc.line_of(elem),
                            suggestion=(
                                "Store connection strings in Orchestrator Assets or Config.xlsx. "
                                "Use Integrated Security=True where possible, or retrieve "
                                "the password separately via GetRobotCredential."
                            ),
                        )
                    )

    return issues


# Rules are auto-registered by the @rule decorator. The legacy
# ALL_SECURITY_RULES list has been removed.
