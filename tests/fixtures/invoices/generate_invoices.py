"""Generate synthetic invoice PDFs for end-to-end DU testing.

Run this script once (after ``pip install reportlab``) to populate
``tests/fixtures/invoices/`` with five realistic-looking invoice PDFs
covering different vendors, currencies, and totals. The PDFs are not
committed to git — they're generated locally for live Phase G runs.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

# These imports are gated so the file can be byte-compiled in environments
# that don't have reportlab installed.
try:
    from reportlab.lib.pagesizes import LETTER
    from reportlab.lib.units import inch
    from reportlab.pdfgen import canvas

    REPORTLAB_AVAILABLE = True
except ImportError:  # pragma: no cover
    REPORTLAB_AVAILABLE = False

OUTPUT_DIR = Path(__file__).parent


@dataclass
class InvoiceFixture:
    file_name: str
    vendor: str
    invoice_number: str
    invoice_date: str
    currency: str
    line_items: list[tuple[str, int, float]]  # description, qty, unit_price

    @property
    def total(self) -> float:
        return sum(qty * price for _, qty, price in self.line_items)


FIXTURES: list[InvoiceFixture] = [
    InvoiceFixture(
        file_name="invoice_acme_corp_001.pdf",
        vendor="ACME Industrial Supplies, Inc.",
        invoice_number="INV-2026-0411-001",
        invoice_date="2026-04-11",
        currency="USD",
        line_items=[
            ("Hex bolts M8 (box of 100)", 4, 24.50),
            ("Hydraulic jack 2-ton", 1, 189.00),
            ("Safety goggles", 12, 7.25),
        ],
    ),
    InvoiceFixture(
        file_name="invoice_globex_002.pdf",
        vendor="Globex Logistics Ltd.",
        invoice_number="GBX/26/04/0042",
        invoice_date="2026-04-09",
        currency="EUR",
        line_items=[
            ("Container freight Hamburg→Rotterdam", 1, 1850.00),
            ("Customs handling fee", 1, 75.00),
        ],
    ),
    InvoiceFixture(
        file_name="invoice_initech_003.pdf",
        vendor="Initech Software Services",
        invoice_number="2026-INI-104",
        invoice_date="2026-04-05",
        currency="USD",
        line_items=[
            ("Cloud hosting (Apr 2026)", 1, 425.00),
            ("Premium support add-on", 1, 100.00),
        ],
    ),
    InvoiceFixture(
        file_name="invoice_umbrella_004.pdf",
        vendor="Umbrella Pharmaceuticals plc",
        invoice_number="UMB-PO-3471",
        invoice_date="2026-04-07",
        currency="GBP",
        line_items=[
            ("Lab consumables (mixed)", 1, 612.40),
            ("Cold-chain shipping surcharge", 1, 48.00),
        ],
    ),
    InvoiceFixture(
        file_name="invoice_stark_005.pdf",
        vendor="Stark Industries R&D",
        invoice_number="SI-RND-9982",
        invoice_date="2026-04-10",
        currency="USD",
        line_items=[
            ("Prototype machining", 1, 2400.00),
            ("Materials testing", 4, 75.00),
            ("Documentation package", 1, 150.00),
        ],
    ),
]


def render_invoice(fix: InvoiceFixture, out_path: Path) -> None:
    """Render a single invoice PDF using reportlab."""
    if not REPORTLAB_AVAILABLE:  # pragma: no cover
        raise RuntimeError("reportlab is required: pip install reportlab")

    c = canvas.Canvas(str(out_path), pagesize=LETTER)
    width, height = LETTER

    # Header
    c.setFont("Helvetica-Bold", 22)
    c.drawString(inch, height - inch, "INVOICE")

    c.setFont("Helvetica", 11)
    c.drawString(inch, height - 1.4 * inch, f"From: {fix.vendor}")
    c.drawString(inch, height - 1.6 * inch, f"Invoice #: {fix.invoice_number}")
    c.drawString(inch, height - 1.8 * inch, f"Date: {fix.invoice_date}")
    c.drawString(inch, height - 2.0 * inch, f"Currency: {fix.currency}")

    # Bill-to (synthetic)
    c.drawString(4.5 * inch, height - 1.4 * inch, "Bill To:")
    c.drawString(4.5 * inch, height - 1.6 * inch, "Odoo Demo Co.")
    c.drawString(4.5 * inch, height - 1.8 * inch, "1 Demo Way, Suite 100")
    c.drawString(4.5 * inch, height - 2.0 * inch, "Demoville, EX 12345")

    # Line items table
    y = height - 2.8 * inch
    c.setFont("Helvetica-Bold", 11)
    c.drawString(inch, y, "Description")
    c.drawString(4.5 * inch, y, "Qty")
    c.drawString(5.2 * inch, y, "Unit Price")
    c.drawString(6.5 * inch, y, "Line Total")
    y -= 0.15 * inch
    c.line(inch, y, 7.5 * inch, y)
    y -= 0.25 * inch

    c.setFont("Helvetica", 11)
    for desc, qty, price in fix.line_items:
        line_total = qty * price
        c.drawString(inch, y, desc[:48])
        c.drawString(4.5 * inch, y, str(qty))
        c.drawString(5.2 * inch, y, f"{price:,.2f}")
        c.drawString(6.5 * inch, y, f"{line_total:,.2f}")
        y -= 0.25 * inch

    # Total
    y -= 0.2 * inch
    c.line(5.0 * inch, y, 7.5 * inch, y)
    y -= 0.3 * inch
    c.setFont("Helvetica-Bold", 12)
    c.drawString(5.0 * inch, y, "Total Amount:")
    c.drawString(6.5 * inch, y, f"{fix.currency} {fix.total:,.2f}")

    # Footer
    c.setFont("Helvetica-Oblique", 9)
    c.drawString(inch, inch, "Payment terms: Net 30. Generated for UiPath DU end-to-end testing.")

    c.showPage()
    c.save()


def main() -> None:
    if not REPORTLAB_AVAILABLE:
        raise SystemExit(
            "reportlab is required to generate invoice fixtures. "
            "Install with: pip install reportlab"
        )
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    for fix in FIXTURES:
        out = OUTPUT_DIR / fix.file_name
        render_invoice(fix, out)
        print(f"wrote {out}")


if __name__ == "__main__":
    main()
