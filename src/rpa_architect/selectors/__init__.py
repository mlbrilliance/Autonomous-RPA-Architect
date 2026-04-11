"""Selector generation and management for UiPath UI automation."""

from rpa_architect.selectors.known_apps import KnownAppSelectors
from rpa_architect.selectors.object_repository import (
    ObjectRepositoryAppV2,
    ObjectRepositoryElementV2,
    ObjectRepositoryEntry,
    ObjectRepositoryScreenV2,
    extract_selector_variables,
    generate_object_repository,
    generate_object_repository_v2,
    resolve_selector_variables,
)
from rpa_architect.selectors.ui_library_gen import generate_ui_library
from rpa_architect.selectors.placeholder_gen import generate_placeholder_selectors
from rpa_architect.selectors.vision_inference import SelectorInference, infer_selectors

# Browser harvesting imports (optional — requires playwright)
try:
    from rpa_architect.selectors.browser_harvester import (
        BrowserHarvestReport,
        HarvestConfig,
        HarvestResult,
        harvest_selectors_from_browser,
    )
    from rpa_architect.selectors.element_matcher import MatchResult, match_actions_to_elements
    from rpa_architect.selectors.harvest_pipeline import merge_selectors, run_harvest_pipeline
    from rpa_architect.selectors.uipath_converter import (
        HarvestedElement,
        batch_convert,
        convert_to_uipath_selector,
    )

    _HARVEST_AVAILABLE = True
except ImportError:
    _HARVEST_AVAILABLE = False

__all__ = [
    "KnownAppSelectors",
    "ObjectRepositoryAppV2",
    "ObjectRepositoryElementV2",
    "ObjectRepositoryEntry",
    "ObjectRepositoryScreenV2",
    "SelectorInference",
    "extract_selector_variables",
    "generate_object_repository",
    "generate_object_repository_v2",
    "generate_placeholder_selectors",
    "generate_ui_library",
    "infer_selectors",
    "resolve_selector_variables",
    # Browser harvesting (optional)
    "BrowserHarvestReport",
    "HarvestConfig",
    "HarvestResult",
    "HarvestedElement",
    "MatchResult",
    "batch_convert",
    "convert_to_uipath_selector",
    "harvest_selectors_from_browser",
    "match_actions_to_elements",
    "merge_selectors",
    "run_harvest_pipeline",
]
