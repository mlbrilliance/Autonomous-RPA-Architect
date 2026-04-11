"""Scaffold and assembly lifecycle hooks.

Hooks allow plugins to inject behaviour at well-defined points in the
scaffold and assembly pipeline.  Each hook receives a mutable *context*
dictionary and may return an updated copy.
"""

from __future__ import annotations

import logging
from enum import Enum
from pathlib import Path
from typing import Any, Callable

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Hook points
# ---------------------------------------------------------------------------

class HookPoint(str, Enum):
    """Well-known points in the scaffold / assembly lifecycle."""

    PRE_SCAFFOLD = "pre_scaffold"
    POST_SCAFFOLD = "post_scaffold"
    PRE_ASSEMBLE = "pre_assemble"
    POST_ASSEMBLE = "post_assemble"
    PRE_VALIDATE = "pre_validate"
    POST_VALIDATE = "post_validate"
    PRE_DEPLOY = "pre_deploy"
    POST_DEPLOY = "post_deploy"
    PRE_MONITOR = "pre_monitor"
    POST_MONITOR = "post_monitor"
    PRE_DIAGNOSE = "pre_diagnose"
    POST_DIAGNOSE = "post_diagnose"
    PRE_FIX = "pre_fix"
    POST_FIX = "post_fix"


# ---------------------------------------------------------------------------
# Hook registry
# ---------------------------------------------------------------------------

_HOOKS: dict[HookPoint, list[Callable]] = {point: [] for point in HookPoint}


def _register_hook(point: HookPoint, fn: Callable) -> None:
    """Internal helper -- append *fn* to the hook list for *point*."""
    _HOOKS[point].append(fn)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def run_hooks(point: HookPoint, context: dict[str, Any]) -> dict[str, Any]:
    """Run all hooks registered at *point*, threading *context* through them.

    Each hook callable receives the current *context* dict.  If a hook
    returns a ``dict``, it replaces the context for subsequent hooks.  If a
    hook raises an exception it is logged and skipped -- remaining hooks
    still execute.

    Returns the (possibly updated) context dictionary.
    """
    for fn in _HOOKS[point]:
        try:
            result = fn(context)
            if isinstance(result, dict):
                context = result
        except Exception:
            logger.exception("Hook %s failed at %s", fn.__name__, point.value)
    return context


def clear_hooks() -> None:
    """Clear all registered hooks.

    This is primarily useful in test suites to reset state between tests.
    """
    for point in HookPoint:
        _HOOKS[point].clear()
