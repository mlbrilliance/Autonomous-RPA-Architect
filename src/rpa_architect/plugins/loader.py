"""Plugin discovery and loading.

Plugins are plain Python modules (or packages) located in an ``extensions/``
directory.  When loaded, a plugin module is expected to call the registration
functions from :mod:`rpa_architect.plugins.api` at import time so that its
generators, lint rules, hooks, and namespaces become available to the rest of
the system.
"""

from __future__ import annotations

import importlib
import importlib.util
import logging
import sys
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Internal state
# ---------------------------------------------------------------------------

_LOADED_PLUGINS: dict[str, Any] = {}


# ---------------------------------------------------------------------------
# Discovery
# ---------------------------------------------------------------------------

def discover_plugins(extensions_dir: Path | str | None = None) -> list[str]:
    """Discover plugin modules in the extensions directory.

    Looks for Python files or packages in ``extensions/`` relative to the
    current working directory, or in the explicitly provided directory.

    Returns a list of importable module name strings.
    """
    if extensions_dir is None:
        extensions_dir = Path.cwd() / "extensions"
    else:
        extensions_dir = Path(extensions_dir)

    if not extensions_dir.is_dir():
        return []

    discovered: list[str] = []

    # Check whether the directory itself is a package
    init_file = extensions_dir / "__init__.py"
    if init_file.is_file():
        discovered.append("extensions")

    # Individual .py files (skip private / dunder files)
    for py_file in sorted(extensions_dir.glob("*.py")):
        if py_file.name.startswith("_"):
            continue
        module_name = f"extensions.{py_file.stem}"
        discovered.append(module_name)

    # Sub-packages (directories with __init__.py)
    for sub_dir in sorted(extensions_dir.iterdir()):
        if sub_dir.is_dir() and (sub_dir / "__init__.py").is_file():
            module_name = f"extensions.{sub_dir.name}"
            discovered.append(module_name)

    logger.info("Discovered %d plugin(s) in %s", len(discovered), extensions_dir)
    return discovered


# ---------------------------------------------------------------------------
# Loading
# ---------------------------------------------------------------------------

def load_plugin(module_name: str, plugin_path: Path | str | None = None) -> Any:
    """Load a single plugin module by name or file path.

    The plugin module should call ``register_generator()``,
    ``register_lint_rule()``, etc. during import to register its extensions.

    Parameters
    ----------
    module_name:
        Dotted module name (e.g. ``"extensions.my_plugin"``).
    plugin_path:
        Optional filesystem path to load from directly (useful when the
        module is not on ``sys.path``).

    Returns
    -------
    The loaded module object.
    """
    if module_name in _LOADED_PLUGINS:
        logger.debug("Plugin already loaded: %s", module_name)
        return _LOADED_PLUGINS[module_name]

    try:
        if plugin_path:
            spec = importlib.util.spec_from_file_location(
                module_name, str(plugin_path)
            )
            if spec and spec.loader:
                module = importlib.util.module_from_spec(spec)
                sys.modules[module_name] = module
                spec.loader.exec_module(module)
            else:
                raise ImportError(f"Cannot create spec for {plugin_path}")
        else:
            module = importlib.import_module(module_name)

        _LOADED_PLUGINS[module_name] = module
        logger.info("Loaded plugin: %s", module_name)
        return module
    except Exception:
        logger.exception("Failed to load plugin: %s", module_name)
        raise


def load_all_plugins(extensions_dir: Path | str | None = None) -> list[str]:
    """Discover and load all plugins from *extensions_dir*.

    Returns the list of successfully loaded module names.
    """
    names = discover_plugins(extensions_dir)
    loaded: list[str] = []
    for name in names:
        try:
            load_plugin(name)
            loaded.append(name)
        except Exception:
            logger.warning("Skipping failed plugin: %s", name)
    return loaded


# ---------------------------------------------------------------------------
# Introspection / testing helpers
# ---------------------------------------------------------------------------

def get_loaded_plugins() -> dict[str, Any]:
    """Return a copy of the loaded-plugin mapping (name -> module)."""
    return dict(_LOADED_PLUGINS)


def clear_plugins() -> None:
    """Clear loaded plugins state.

    This is primarily useful in test suites to reset state between tests.
    """
    _LOADED_PLUGINS.clear()
