"""Pydantic v2 models for the XAML hallucination linter."""

from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, model_validator


class LintSeverity(str, Enum):
    """Severity level for a lint issue."""

    ERROR = "ERROR"
    WARNING = "WARNING"
    INFO = "INFO"


class LintCategory(str, Enum):
    """Category of lint issue detected."""

    HALLUCINATION = "HALLUCINATION"
    SECURITY = "SECURITY"
    BEST_PRACTICE = "BEST_PRACTICE"
    NAMESPACE = "NAMESPACE"
    ENUM = "ENUM"
    NESTING = "NESTING"
    PROPERTY = "PROPERTY"
    VIEWSTATE = "VIEWSTATE"
    TYPE_ARGUMENT = "TYPE_ARGUMENT"
    CREDENTIAL = "CREDENTIAL"
    CONFIG = "CONFIG"


class LintIssue(BaseModel):
    """A single lint issue found in a XAML file."""

    model_config = {"frozen": True}

    rule_id: str
    severity: LintSeverity
    category: LintCategory
    message: str
    element_name: str = ""
    line_number: int = 0
    suggestion: str = ""


class LintResult(BaseModel):
    """Aggregated lint results for a single XAML file."""

    model_config = {"frozen": False}

    file_path: str
    issues: list[LintIssue] = []
    error_count: int = 0
    warning_count: int = 0
    info_count: int = 0

    @model_validator(mode="after")
    def _compute_counts(self) -> LintResult:
        self.error_count = sum(
            1 for i in self.issues if i.severity == LintSeverity.ERROR
        )
        self.warning_count = sum(
            1 for i in self.issues if i.severity == LintSeverity.WARNING
        )
        self.info_count = sum(
            1 for i in self.issues if i.severity == LintSeverity.INFO
        )
        return self
