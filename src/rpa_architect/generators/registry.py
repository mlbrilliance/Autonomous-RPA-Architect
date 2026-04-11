"""Generator registry -- maps activity names to deterministic XAML generators."""

from __future__ import annotations

import importlib
from dataclasses import dataclass, field
from typing import Any, Callable


# ---------------------------------------------------------------------------
# Registry data structures
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class GeneratorInfo:
    """Metadata and callable for a single registered generator."""

    name: str
    fn: Callable[..., str]
    display_name: str
    category: str
    description: str = ""


_REGISTRY: dict[str, GeneratorInfo] = {}


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def register_generator(
    name: str,
    fn: Callable[..., str],
    display_name: str,
    category: str,
    description: str = "",
) -> None:
    """Register a generator function under *name*.

    Raises ``ValueError`` if *name* is already registered.
    """
    if name in _REGISTRY:
        raise ValueError(f"Generator '{name}' is already registered")
    _REGISTRY[name] = GeneratorInfo(
        name=name,
        fn=fn,
        display_name=display_name,
        category=category,
        description=description,
    )


def get_generator(name: str) -> GeneratorInfo | None:
    """Look up a generator by *name*.  Returns ``None`` if not found."""
    return _REGISTRY.get(name)


def generate_activity(name: str, **params: Any) -> str:
    """Call the registered generator for *name* with the given keyword params.

    Raises ``ValueError`` if no generator is registered under *name*.
    """
    info = _REGISTRY.get(name)
    if info is None:
        available = ", ".join(sorted(_REGISTRY.keys()))
        raise ValueError(
            f"No generator registered for '{name}'. "
            f"Available generators: {available}"
        )
    return info.fn(**params)


def list_generators() -> list[GeneratorInfo]:
    """Return all registered generators sorted by name."""
    return sorted(_REGISTRY.values(), key=lambda g: g.name)


# ---------------------------------------------------------------------------
# Auto-import all generator modules to trigger registration
# ---------------------------------------------------------------------------

_GENERATOR_MODULES = [
    "rpa_architect.generators.ui_activities",
    "rpa_architect.generators.control_flow",
    "rpa_architect.generators.data_ops",
    "rpa_architect.generators.error_handling",
    "rpa_architect.generators.integrations",
    "rpa_architect.generators.file_system",
    "rpa_architect.generators.orchestrator_activities",
    "rpa_architect.generators.http_json",
    "rpa_architect.generators.invoke",
    "rpa_architect.generators.logging_misc",
    "rpa_architect.generators.coded_apis",
]

for _mod_name in _GENERATOR_MODULES:
    importlib.import_module(_mod_name)
