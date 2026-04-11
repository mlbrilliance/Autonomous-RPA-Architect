"""Plugin architecture for the RPA Architect.

This package provides extensibility hooks so that users can register custom
generators, lint rules, scaffold hooks, and XML namespaces via a simple Python
API or by dropping modules into an ``extensions/`` directory.

Quick start::

    from rpa_architect.plugins import register_generator, register_lint_rule

    # Register a custom generator
    register_generator("my_activity", my_gen_fn, category="custom")

    # Register a custom lint rule
    register_lint_rule(my_rule_fn)

    # Discover and load all plugins from extensions/
    from rpa_architect.plugins import discover_plugins, load_plugin
    for name in discover_plugins():
        load_plugin(name)
"""

from __future__ import annotations

from rpa_architect.plugins.api import (
    get_registered_namespaces,
    register_generator,
    register_lint_rule,
    register_namespace,
    register_scaffold_hook,
)
from rpa_architect.plugins.hooks import HookPoint, run_hooks
from rpa_architect.plugins.loader import discover_plugins, load_plugin

__all__ = [
    "discover_plugins",
    "get_registered_namespaces",
    "HookPoint",
    "load_plugin",
    "register_generator",
    "register_lint_rule",
    "register_namespace",
    "register_scaffold_hook",
    "run_hooks",
]
