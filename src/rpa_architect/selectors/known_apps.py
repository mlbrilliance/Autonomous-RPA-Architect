"""Pre-built selector libraries for common applications.

Provides a registry of known UI selectors for frequently automated
applications (e.g., SAP, Outlook, web browsers) so that generated
projects start with high-quality selectors out of the box.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

# Default knowledge base path relative to package root
_DEFAULT_KNOWLEDGE_DIR = (
    Path(__file__).resolve().parent.parent.parent.parent
    / "knowledge"
    / "selectors"
    / "known_apps"
)


class KnownAppSelectors:
    """Registry of pre-built selectors for known applications.

    Loads selector definitions from JSON files in the knowledge base
    directory. Each file is named ``{app_name}.json`` and contains
    a dict mapping element names to UiPath XML selector strings.
    """

    def __init__(self, knowledge_dir: Optional[Path] = None) -> None:
        """Initialize the selector registry.

        Args:
            knowledge_dir: Directory containing app selector JSON files.
                Defaults to ``knowledge/selectors/known_apps/`` relative
                to the project root.
        """
        self._knowledge_dir = knowledge_dir or _DEFAULT_KNOWLEDGE_DIR
        self._cache: dict[str, dict[str, str]] = {}

    @property
    def knowledge_dir(self) -> Path:
        """Path to the knowledge base directory."""
        return self._knowledge_dir

    def load_app_selectors(self, app_name: str) -> dict[str, str]:
        """Load selectors for a specific application.

        Reads from ``knowledge/selectors/known_apps/{app_name}.json``.
        Results are cached after first load.

        Args:
            app_name: Application name (case-insensitive, e.g., 'sap', 'outlook').

        Returns:
            Dictionary mapping element_name -> selector_xml.
            Returns empty dict if the app file is not found.
        """
        app_key = app_name.lower().strip()

        if app_key in self._cache:
            return self._cache[app_key]

        selector_file = self._knowledge_dir / f"{app_key}.json"

        if not selector_file.exists():
            logger.debug(
                "No known selectors for app '%s' (looked in %s).",
                app_name,
                selector_file,
            )
            self._cache[app_key] = {}
            return {}

        try:
            raw = selector_file.read_text(encoding="utf-8")
            data = json.loads(raw)
        except (json.JSONDecodeError, OSError) as exc:
            logger.warning(
                "Failed to load selectors for '%s': %s",
                app_name,
                exc,
            )
            self._cache[app_key] = {}
            return {}

        if not isinstance(data, dict):
            logger.warning(
                "Selector file for '%s' is not a JSON object; ignoring.",
                app_name,
            )
            self._cache[app_key] = {}
            return {}

        selectors: dict[str, str] = {str(k): str(v) for k, v in data.items()}
        self._cache[app_key] = selectors

        logger.info(
            "Loaded %d known selectors for '%s'.",
            len(selectors),
            app_name,
        )
        return selectors

    def get_selector(self, app_name: str, element_name: str) -> Optional[str]:
        """Look up a specific selector for an app element.

        Args:
            app_name: Application name.
            element_name: Element identifier within the app.

        Returns:
            The selector XML string, or None if not found.
        """
        selectors = self.load_app_selectors(app_name)
        return selectors.get(element_name)

    def list_known_apps(self) -> list[str]:
        """List all applications with known selector libraries.

        Scans the knowledge directory for ``*.json`` files and returns
        their base names (without extension).

        Returns:
            Sorted list of known application names.
        """
        if not self._knowledge_dir.exists():
            return []

        apps: list[str] = []
        for path in self._knowledge_dir.glob("*.json"):
            apps.append(path.stem)

        return sorted(apps)
