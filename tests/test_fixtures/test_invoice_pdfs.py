"""Verify the invoice PDF fixtures are real, parseable, and contain the expected text."""

from __future__ import annotations

from pathlib import Path

import pytest

FIXTURES_DIR = Path(__file__).parent.parent / "fixtures" / "invoices"


def _ensure_pdfs_exist() -> list[Path]:
    """Lazily regenerate the PDFs if they're missing (e.g. on fresh clones)."""
    pdfs = sorted(FIXTURES_DIR.glob("*.pdf"))
    if len(pdfs) < 5:
        import runpy

        runpy.run_path(str(FIXTURES_DIR / "generate_invoices.py"), run_name="__main__")
        pdfs = sorted(FIXTURES_DIR.glob("*.pdf"))
    return pdfs


def test_exactly_five_invoice_pdfs_exist() -> None:
    pdfs = _ensure_pdfs_exist()
    assert len(pdfs) == 5, f"got {len(pdfs)}: {[p.name for p in pdfs]}"


def test_each_pdf_is_a_valid_pdf_file() -> None:
    for pdf in _ensure_pdfs_exist():
        head = pdf.read_bytes()[:5]
        assert head == b"%PDF-", f"{pdf.name} is not a valid PDF: head={head!r}"


def test_each_pdf_has_nontrivial_size() -> None:
    for pdf in _ensure_pdfs_exist():
        assert pdf.stat().st_size > 1000, f"{pdf.name} too small ({pdf.stat().st_size} bytes)"


def test_pdf_content_contains_vendor_names() -> None:
    """Parse each PDF with pdfplumber and assert the vendor name is present."""
    try:
        import pdfplumber  # type: ignore[import-not-found]
    except ImportError:
        pytest.skip("pdfplumber not installed")

    expected_vendors = {
        "invoice_acme_corp_001.pdf": "ACME Industrial Supplies",
        "invoice_globex_002.pdf": "Globex Logistics",
        "invoice_initech_003.pdf": "Initech Software Services",
        "invoice_umbrella_004.pdf": "Umbrella Pharmaceuticals",
        "invoice_stark_005.pdf": "Stark Industries",
    }
    for pdf in _ensure_pdfs_exist():
        expected = expected_vendors.get(pdf.name)
        if not expected:
            continue
        with pdfplumber.open(str(pdf)) as doc:
            text = "\n".join(page.extract_text() or "" for page in doc.pages)
        assert expected in text, f"{pdf.name} missing vendor name {expected!r}"


def test_pdf_content_contains_invoice_reference() -> None:
    try:
        import pdfplumber
    except ImportError:
        pytest.skip("pdfplumber not installed")

    for pdf in _ensure_pdfs_exist():
        with pdfplumber.open(str(pdf)) as doc:
            text = "\n".join(page.extract_text() or "" for page in doc.pages)
        assert "Invoice #" in text, f"{pdf.name} missing 'Invoice #' header"
        assert "Total Amount" in text, f"{pdf.name} missing 'Total Amount' row"


def test_pdf_amounts_match_fixture_definitions() -> None:
    try:
        import pdfplumber
    except ImportError:
        pytest.skip("pdfplumber not installed")
    import runpy

    mod = runpy.run_path(str(FIXTURES_DIR / "generate_invoices.py"))
    fixtures = {f.file_name: f.total for f in mod["FIXTURES"]}
    for pdf in _ensure_pdfs_exist():
        expected = fixtures.get(pdf.name)
        assert expected is not None, f"no fixture definition for {pdf.name}"
        with pdfplumber.open(str(pdf)) as doc:
            text = "\n".join(page.extract_text() or "" for page in doc.pages)
        assert f"{expected:,.2f}" in text, (
            f"{pdf.name} missing expected total {expected:,.2f}"
        )
