"""Map a :class:`UIAction` to a Playwright-Python call expression.

Every supported action has an entry; unknown actions raise
:class:`UnsupportedActionError`. This is the translation boundary — once
every UIAction can produce a valid Python snippet, the py_playwright_emitter
is trivial (Jinja concatenation).
"""

from __future__ import annotations

import re

from rpa_architect.ir.schema import UIAction
from rpa_architect.migrator.selector_translator import translate_selector


class UnsupportedActionError(ValueError):
    """Raised when the migrator cannot emit Python for a UIAction kind."""


def emit_call(action: UIAction) -> str:
    """Return a one-statement Playwright expression for ``action``."""
    locator = translate_selector(action.selector_hint or "")

    if action.action == "click":
        return f"await {locator}.click()"
    if action.action == "type_into":
        value = action.value or ""
        return f"await {locator}.fill({_literal(value)})"
    if action.action == "get_text":
        var = _slugify(action.target)
        return f"{var} = await {locator}.text_content()"
    if action.action == "select_item":
        value = action.value or ""
        return f"await {locator}.select_option({_literal(value)})"
    if action.action == "check":
        return f"await {locator}.check()"
    if action.action == "uncheck":
        return f"await {locator}.uncheck()"
    if action.action == "hover":
        return f"await {locator}.hover()"
    if action.action == "wait_element":
        return f"await {locator}.wait_for()"
    if action.action == "keyboard_shortcut":
        value = action.value or ""
        return f"await page.keyboard.press({_literal(value)})"
    if action.action == "extract_data":
        var = _slugify(action.target)
        return f"{var} = await {locator}.text_content()"

    raise UnsupportedActionError(
        f"Migrator cannot emit Python for UIAction.action={action.action!r}. "
        f"Supported actions: click, type_into, get_text, select_item, check, "
        "uncheck, hover, wait_element, keyboard_shortcut, extract_data."
    )


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------


def _literal(value: str) -> str:
    """Emit a Python string literal safe for single-quote contexts."""
    escaped = value.replace("\\", "\\\\").replace("'", "\\'")
    return f"'{escaped}'"


_NON_ID = re.compile(r"[^a-z0-9]+")


def _slugify(target: str) -> str:
    """Turn a display name into a Python identifier."""
    base = _NON_ID.sub("_", target.lower()).strip("_")
    if not base or base[0].isdigit():
        base = "var_" + base
    return base
