"""Tests for the Odoo Community known-apps selector library."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
ODOO_JSON = REPO_ROOT / "knowledge" / "selectors" / "known_apps" / "odoo_community.json"


@pytest.fixture(scope="module")
def odoo_data() -> dict:
    assert ODOO_JSON.exists(), f"missing {ODOO_JSON}"
    return json.loads(ODOO_JSON.read_text(encoding="utf-8"))


def test_odoo_json_exists() -> None:
    assert ODOO_JSON.exists()


def test_odoo_json_declares_application_metadata(odoo_data: dict) -> None:
    assert odoo_data["application"] == "Odoo Community"
    assert odoo_data["type"] == "web"
    assert odoo_data["browser"] == "chrome.exe"
    assert "default_login_path" in odoo_data
    assert odoo_data["default_login_path"] == "/web/login"


def test_odoo_json_has_login_selectors(odoo_data: dict) -> None:
    sels = odoo_data["selectors"]
    assert "login_email" in sels
    assert "login_password" in sels
    assert "login_submit_button" in sels


def test_odoo_login_selectors_target_correct_url(odoo_data: dict) -> None:
    sels = odoo_data["selectors"]
    for key in ("login_email", "login_password", "login_submit_button"):
        assert "*odoo*login*" in sels[key]["selector"]


def test_odoo_json_has_vendor_bill_form_selectors(odoo_data: dict) -> None:
    sels = odoo_data["selectors"]
    required = {
        "new_button",
        "vendor_field_input",
        "bill_reference_input",
        "invoice_date_input",
        "save_button",
    }
    assert required.issubset(set(sels.keys())), f"missing: {required - set(sels.keys())}"


def test_odoo_form_selectors_use_name_attribute(odoo_data: dict) -> None:
    """Odoo form fields are most stable when targeted by `name` attribute."""
    sels = odoo_data["selectors"]
    assert "name='partner_id'" in sels["vendor_field_input"]["selector"]
    assert "name='ref'" in sels["bill_reference_input"]["selector"]
    assert "name='invoice_date'" in sels["invoice_date_input"]["selector"]


def test_odoo_navigation_selectors_present(odoo_data: dict) -> None:
    sels = odoo_data["selectors"]
    assert "main_menu_brand" in sels
    assert "accounting_menu" in sels
    assert "vendor_bills_menu_item" in sels


def test_odoo_selectors_all_have_stability_and_category(odoo_data: dict) -> None:
    for name, entry in odoo_data["selectors"].items():
        assert "selector" in entry, f"{name}: missing selector"
        assert "description" in entry, f"{name}: missing description"
        assert entry.get("stability") in ("high", "medium", "low"), (
            f"{name}: stability missing or invalid"
        )
        assert "category" in entry, f"{name}: missing category"


def test_odoo_vendor_bills_menu_uses_data_menu_xmlid(odoo_data: dict) -> None:
    sel = odoo_data["selectors"]["vendor_bills_menu_item"]["selector"]
    assert "data-menu-xmlid" in sel
    assert "account.menu_action_move_in_invoice_type" in sel


def test_odoo_notes_mention_owl_js_quirks(odoo_data: dict) -> None:
    notes_text = " ".join(odoo_data.get("notes", [])).lower()
    assert "owl" in notes_text or "dynamic" in notes_text


def test_proof_harvest_script_exists() -> None:
    """The proof/harvest_odoo.py runtime script must be present (not run in tests)."""
    p = REPO_ROOT / "proof" / "harvest_odoo.py"
    assert p.exists()


def test_proof_docker_compose_exists() -> None:
    p = REPO_ROOT / "proof" / "odoo" / "docker-compose.yml"
    assert p.exists()


def test_proof_seed_script_exists() -> None:
    p = REPO_ROOT / "proof" / "odoo" / "seed_database.py"
    assert p.exists()
