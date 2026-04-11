"""Tests for domain pack framework."""

import pytest

from rpa_architect.domains.base import (
    DomainPack,
    ProcessTemplate,
    get_pack,
    list_packs,
    load_builtin_packs,
    match_pack,
    register_pack,
    _DOMAIN_PACKS,
)


@pytest.fixture(autouse=True)
def clean_registry():
    """Reset domain pack registry between tests."""
    _DOMAIN_PACKS.clear()
    yield
    _DOMAIN_PACKS.clear()


def _make_pack(industry: str = "test") -> DomainPack:
    return DomainPack(
        name="Test Pack",
        industry=industry,
        description="A test domain pack",
        templates=[
            ProcessTemplate(
                name="Test Template",
                description="Test process",
                tags=["invoice", "billing"],
            ),
        ],
    )


class TestDomainRegistry:
    def test_register_and_get(self):
        pack = _make_pack("finance")
        register_pack(pack)
        assert get_pack("finance") is pack

    def test_get_nonexistent(self):
        assert get_pack("nonexistent") is None

    def test_list_packs(self):
        register_pack(_make_pack("finance"))
        register_pack(_make_pack("healthcare"))
        packs = list_packs()
        assert len(packs) == 2

    def test_match_pack_by_tag(self):
        register_pack(_make_pack("finance"))
        result = match_pack("Process vendor invoices and post to ERP")
        assert result is not None
        assert result.industry == "finance"

    def test_match_pack_no_match(self):
        register_pack(_make_pack("finance"))
        result = match_pack("Deploy kubernetes cluster")
        assert result is None


class TestBuiltinPacks:
    def test_load_builtin_packs(self):
        load_builtin_packs()
        packs = list_packs()
        industries = {p.industry for p in packs}
        assert "finance" in industries
        assert "healthcare" in industries
        assert "insurance" in industries

    def test_finance_pack_templates(self):
        load_builtin_packs()
        pack = get_pack("finance")
        assert pack is not None
        template_names = {t.name for t in pack.templates}
        assert "Invoice Processing" in template_names
        assert "Bank Reconciliation" in template_names
        assert "Loan Origination QA" in template_names

    def test_healthcare_pack_compliance(self):
        load_builtin_packs()
        pack = get_pack("healthcare")
        assert pack is not None
        assert any("HIPAA" in req for req in pack.compliance_requirements)

    def test_insurance_pack_templates(self):
        load_builtin_packs()
        pack = get_pack("insurance")
        assert pack is not None
        template_names = {t.name for t in pack.templates}
        assert "Policy Issuance" in template_names
        assert "Claims Adjudication" in template_names
