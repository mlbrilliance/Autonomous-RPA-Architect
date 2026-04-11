"""Convert IR business-rule conditions to JavaScript expressions."""

from __future__ import annotations

import re


def generate_expression(condition: str, variables: dict[str, str] | None = None) -> str:
    """Translate a human-readable condition into a JavaScript expression.

    Supports common patterns:

    * Comparisons (``>  <  >=  <=  ==  !=``)
    * String operations (``contains``, ``starts with``, ``ends with``)
    * Date operations (``before``, ``after``)
    * Null / empty checks (``is null``, ``is not null``, ``is empty``)
    * Boolean keywords (``and``, ``or``, ``not``)

    Unknown tokens are passed through as-is so that the expression remains
    valid JavaScript (with variable names substituted from *variables* if
    provided).

    Args:
        condition: Natural-language condition string from the IR.
        variables: Optional mapping of descriptive names to JS variable names.

    Returns:
        A JavaScript expression string.
    """
    expr = condition.strip()
    if variables is None:
        variables = {}

    # Substitute known variable names.
    for human_name, js_name in variables.items():
        expr = re.sub(re.escape(human_name), js_name, expr, flags=re.IGNORECASE)

    # Null / empty checks
    expr = re.sub(r"\bis\s+not\s+null\b", "!== null", expr, flags=re.IGNORECASE)
    expr = re.sub(r"\bis\s+null\b", "=== null", expr, flags=re.IGNORECASE)
    expr = re.sub(r"\bis\s+not\s+empty\b", '!== ""', expr, flags=re.IGNORECASE)
    expr = re.sub(r"\bis\s+empty\b", '=== ""', expr, flags=re.IGNORECASE)

    # String operations
    expr = _replace_string_op(expr, r"contains", "{lhs}.includes({rhs})")
    expr = _replace_string_op(expr, r"starts\s+with", "{lhs}.startsWith({rhs})")
    expr = _replace_string_op(expr, r"ends\s+with", "{lhs}.endsWith({rhs})")

    # Date operations
    expr = re.sub(
        r"(\S+)\s+is\s+before\s+(\S+)",
        r"new Date(\1) < new Date(\2)",
        expr,
        flags=re.IGNORECASE,
    )
    expr = re.sub(
        r"(\S+)\s+is\s+after\s+(\S+)",
        r"new Date(\1) > new Date(\2)",
        expr,
        flags=re.IGNORECASE,
    )

    # Boolean keywords
    expr = re.sub(r"\band\b", "&&", expr, flags=re.IGNORECASE)
    expr = re.sub(r"\bor\b", "||", expr, flags=re.IGNORECASE)
    expr = re.sub(r"\bnot\b", "!", expr, flags=re.IGNORECASE)

    # Comparison operators — normalise words to symbols
    expr = re.sub(r"\bgreater\s+than\s+or\s+equal\s+to\b", ">=", expr, flags=re.IGNORECASE)
    expr = re.sub(r"\bless\s+than\s+or\s+equal\s+to\b", "<=", expr, flags=re.IGNORECASE)
    expr = re.sub(r"\bgreater\s+than\b", ">", expr, flags=re.IGNORECASE)
    expr = re.sub(r"\bless\s+than\b", "<", expr, flags=re.IGNORECASE)
    expr = re.sub(r"\bequals?\b", "===", expr, flags=re.IGNORECASE)
    expr = re.sub(r"\bnot\s+equals?\b", "!==", expr, flags=re.IGNORECASE)
    expr = re.sub(r"\bexceeds?\b", ">", expr, flags=re.IGNORECASE)

    return expr.strip()


def _replace_string_op(expr: str, keyword: str, template: str) -> str:
    """Replace ``<lhs> <keyword> <rhs>`` with a JS method call."""
    pattern = rf"(\S+)\s+{keyword}\s+(\S+)"
    match = re.search(pattern, expr, re.IGNORECASE)
    if match:
        lhs, rhs = match.group(1), match.group(2)
        replacement = template.format(lhs=lhs, rhs=rhs)
        expr = expr[: match.start()] + replacement + expr[match.end() :]
    return expr
