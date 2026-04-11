"""Plugin registration API for extending the RPA Architect.

This module provides the central registration functions that delegate to the
correct subsystem (generators, lint rules, scaffold hooks, XML namespaces).
Plugin authors should import from ``rpa_architect.plugins`` rather than from
this module directly.
"""

from __future__ import annotations

import logging
from typing import Any, Callable

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Namespace registry (custom xmlns prefixes)
# ---------------------------------------------------------------------------

_CUSTOM_NAMESPACES: dict[str, str] = {}


# ---------------------------------------------------------------------------
# Public registration functions
# ---------------------------------------------------------------------------

def register_generator(
    name: str,
    fn: Callable[..., str],
    display_name: str = "",
    category: str = "custom",
    description: str = "",
) -> None:
    """Register a custom XAML activity generator.

    Parameters
    ----------
    name:
        Unique identifier for the generator (e.g. ``"my_custom_activity"``).
    fn:
        Callable that accepts keyword arguments and returns a XAML string.
    display_name:
        Human-readable name shown in listings.  Defaults to *name*.
    category:
        Grouping category (e.g. ``"custom"``, ``"integration"``).
    description:
        Optional short description of what the generator produces.
    """
    from rpa_architect.generators.registry import register_generator as _reg

    _reg(name, fn, display_name or name, category, description)
    logger.info("Plugin registered generator: %s", name)


def register_lint_rule(fn: Callable, rule_module: str = "custom") -> None:
    """Register a custom lint rule function.

    The function should accept ``(root: ET.Element, ns: dict)`` and return
    ``list[LintIssue]``.

    Parameters
    ----------
    fn:
        The lint rule callable.
    rule_module:
        Informational label for logging (e.g. the plugin name).
    """
    from rpa_architect.xaml_lint.engine import get_default_engine

    engine = get_default_engine()
    engine.register_rule(fn)
    logger.info("Plugin registered lint rule: %s.%s", rule_module, fn.__name__)


def register_scaffold_hook(
    fn: Callable, hook_point: str = "post_scaffold"
) -> None:
    """Register a scaffold lifecycle hook.

    Parameters
    ----------
    fn:
        Callable that receives a context ``dict`` and optionally returns an
        updated context ``dict``.
    hook_point:
        One of the ``HookPoint`` values (e.g. ``"pre_scaffold"``,
        ``"post_scaffold"``, ``"pre_assemble"``, ``"post_assemble"``,
        ``"pre_validate"``, ``"post_validate"``).
    """
    from rpa_architect.plugins.hooks import HookPoint, _register_hook

    point = HookPoint(hook_point)
    _register_hook(point, fn)
    logger.info("Plugin registered scaffold hook at %s: %s", hook_point, fn.__name__)


def register_namespace(prefix: str, uri: str) -> None:
    """Register a custom XML namespace prefix -> URI mapping.

    Parameters
    ----------
    prefix:
        The namespace prefix (e.g. ``"myext"``).
    uri:
        The full namespace URI (e.g. ``"http://example.com/myext"``).
    """
    _CUSTOM_NAMESPACES[prefix] = uri
    logger.info("Plugin registered namespace: xmlns:%s='%s'", prefix, uri)


def get_registered_namespaces() -> dict[str, str]:
    """Return a copy of all custom-registered XML namespaces."""
    return dict(_CUSTOM_NAMESPACES)
