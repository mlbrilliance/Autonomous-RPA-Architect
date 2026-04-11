"""Deterministic XAML activity generators for UiPath workflows.

Provides pure-function generators that produce structurally correct UiPath XAML
fragments, eliminating LLM hallucination for common activities.
"""

from __future__ import annotations

from rpa_architect.generators.registry import generate_activity, get_generator, list_generators

__all__ = ["generate_activity", "get_generator", "list_generators"]
