"""Domain pack framework for vertical industry solutions."""

from __future__ import annotations

import importlib
import logging
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)


class ProcessTemplate(BaseModel):
    """A pre-configured process template for a domain."""

    name: str = Field(description="Template name (e.g., 'Invoice Processing').")
    description: str = Field(description="What this template automates.")
    process_type: str = Field(default="transactional", description="Process type.")
    systems: list[dict[str, Any]] = Field(default_factory=list, description="Typical systems involved.")
    steps_outline: list[str] = Field(default_factory=list, description="High-level step descriptions.")
    config_defaults: dict[str, str] = Field(default_factory=dict, description="Default Config.xlsx values.")
    tags: list[str] = Field(default_factory=list, description="Searchable tags.")


class DomainPack(BaseModel):
    """A vertical domain pack with templates, rules, and knowledge."""

    name: str = Field(description="Pack name.")
    industry: str = Field(description="Industry (finance, healthcare, insurance, etc.).")
    description: str = Field(description="What this domain pack covers.")
    templates: list[ProcessTemplate] = Field(default_factory=list)
    business_rule_patterns: list[dict[str, Any]] = Field(
        default_factory=list,
        description="Common business rule patterns for this domain.",
    )
    compliance_requirements: list[str] = Field(
        default_factory=list,
        description="Regulatory/compliance considerations.",
    )
    knowledge_dir: str = Field(
        default="",
        description="Path to domain-specific knowledge documents (relative to knowledge/).",
    )


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------

_DOMAIN_PACKS: dict[str, DomainPack] = {}


def register_pack(pack: DomainPack) -> None:
    """Register a domain pack in the global registry."""
    _DOMAIN_PACKS[pack.industry] = pack
    logger.info("Registered domain pack: %s (%s)", pack.name, pack.industry)


def get_pack(industry: str) -> DomainPack | None:
    """Retrieve a domain pack by industry."""
    return _DOMAIN_PACKS.get(industry)


def list_packs() -> list[DomainPack]:
    """List all registered domain packs."""
    return list(_DOMAIN_PACKS.values())


def match_pack(description: str) -> DomainPack | None:
    """Match a domain pack based on process description keywords."""
    desc_lower = description.lower()
    for pack in _DOMAIN_PACKS.values():
        for template in pack.templates:
            for tag in template.tags:
                if tag.lower() in desc_lower:
                    logger.info("Matched domain pack '%s' via tag '%s'", pack.name, tag)
                    return pack
    return None


def load_builtin_packs() -> None:
    """Load all built-in domain packs."""
    for module_name in ("finance", "healthcare", "insurance"):
        try:
            mod = importlib.import_module(f"rpa_architect.domains.{module_name}")
            if hasattr(mod, "PACK"):
                register_pack(mod.PACK)
        except ImportError:
            logger.debug("Domain pack %s not available", module_name)
