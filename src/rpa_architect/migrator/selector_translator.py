"""Translate UiPath selector XML fragments to Playwright locator expressions.

UiPath selectors live in a nested XML-like string such as
``<html app='chrome.exe'/><webctrl tag='button' id='submit'/>``.

We pick the **most stable** attribute by priority:

1. ``data-testid`` → ``page.get_by_test_id(...)``
2. ``id``          → ``page.locator('#id')``
3. ``name``        → ``page.locator('tag[name="..."]')``
4. ``aaname``      → ``page.get_by_role('<tag>', name=...)`` (aaname is UiPath's accessible name)
5. ``innertext``   → ``page.get_by_text(...)``
6. ``css-selector``→ ``page.locator(<raw css>)``

This hierarchy matches Playwright's own documented ranking of stable
selectors. Empty or unparseable fragments emit a deliberately-noisy
``TODO`` locator so the generated code still compiles but flags the
migration-time issue.
"""

from __future__ import annotations

import re


_ATTR_RE = re.compile(r"""([\w-]+)\s*=\s*['"]([^'"]*)['"]""")


def translate_selector(selector_xml: str) -> str:
    """Return a Playwright locator expression for the given UiPath selector XML."""
    if not selector_xml:
        return "page.locator('TODO: empty selector')"

    attrs, tag = _parse(selector_xml)

    if "data-testid" in attrs:
        return f"page.get_by_test_id({_py_literal(attrs['data-testid'])})"

    if "id" in attrs and attrs["id"]:
        return f"page.locator({_py_literal('#' + attrs['id'])})"

    if "name" in attrs and attrs["name"]:
        tag_part = tag or "input"
        css = tag_part + '[name="' + attrs["name"] + '"]'
        return f"page.locator({_py_literal(css)})"

    if "aaname" in attrs and attrs["aaname"]:
        role = tag or "button"
        return f"page.get_by_role({_py_literal(role)}, name={_py_literal(attrs['aaname'])})"

    if "innertext" in attrs and attrs["innertext"]:
        return f"page.get_by_text({_py_literal(attrs['innertext'])})"

    if "css-selector" in attrs and attrs["css-selector"]:
        return f"page.locator({_py_literal(attrs['css-selector'])})"

    return "page.locator('TODO: no stable selector attribute found')"


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------


def _parse(selector_xml: str) -> tuple[dict[str, str], str]:
    """Parse all ``key='value'`` pairs across the selector. Prefer the tag
    from the innermost element (usually ``webctrl`` or ``aa-auto``).
    """
    attrs = dict(_ATTR_RE.findall(selector_xml))
    tag = attrs.pop("tag", "")
    # HTML wrapper attributes we don't care about for locator generation
    for noise in ("app", "appid", "title", "cls"):
        attrs.pop(noise, None)
    return attrs, tag


def _py_literal(value: str) -> str:
    """Emit a Python string literal safe for single-quote contexts."""
    escaped = value.replace("\\", "\\\\").replace("'", "\\'")
    return f"'{escaped}'"
