"""Generate a C# file that embeds real invoice PDFs as base64 constants.

This sidesteps two real constraints we hit on UiPath Community Cloud:
  1. Creating/using Storage Buckets requires the ``OR.StorageBuckets`` scope
     which isn't granted to a baseline External Application.
  2. The serverless robot has no ambient filesystem we can drop PDFs onto.

Embedding 5 invoices at ~2 KB each (base64 ~3 KB each, ~15 KB total) keeps
the compiled DLL under ~65 KB and guarantees the bot has the real PDFs
bundled at package-install time, no separate upload step needed.
"""

from __future__ import annotations

import base64
from dataclasses import dataclass
from pathlib import Path


@dataclass
class EmbeddedInvoice:
    file_name: str
    vendor_hint: str        # expected vendor name ground truth
    expected_currency: str  # ground truth currency for rule tests
    expected_total: float   # ground truth total
    base64_bytes: str


def load_invoices(pdf_dir: Path) -> list[EmbeddedInvoice]:
    """Read the 5 real invoice PDFs from ``pdf_dir`` and encode them.

    The ground-truth metadata comes from the generator that wrote them
    (``tests/fixtures/invoices/generate_invoices.py``). We re-exec that
    module to pull the `FIXTURES` list and align it with the on-disk PDFs.
    """
    import runpy

    gen_path = pdf_dir / "generate_invoices.py"
    if not gen_path.exists():
        raise FileNotFoundError(f"missing generator: {gen_path}")
    mod = runpy.run_path(str(gen_path))
    fixtures = mod["FIXTURES"]

    invoices: list[EmbeddedInvoice] = []
    for fix in fixtures:
        pdf_path = pdf_dir / fix.file_name
        if not pdf_path.exists():
            raise FileNotFoundError(f"missing PDF: {pdf_path}")
        data = pdf_path.read_bytes()
        invoices.append(EmbeddedInvoice(
            file_name=fix.file_name,
            vendor_hint=fix.vendor,
            expected_currency=fix.currency,
            expected_total=fix.total,
            base64_bytes=base64.b64encode(data).decode(),
        ))
    return invoices


def generate_embedded_invoices_cs(
    invoices: list[EmbeddedInvoice],
    namespace: str = "OdooInvoiceProcessing",
) -> str:
    """Emit a C# file with a ``EmbeddedInvoices`` class holding all PDFs.

    The class exposes:
      * ``public static readonly List<EmbeddedInvoice> All``
      * ``EmbeddedInvoice.PdfBytes`` (decoded at runtime for DU upload)
    """
    # Split very long base64 strings across multiple literals so the C#
    # compiler doesn't hit its string-literal length guard.
    def _split_literal(b64: str, chunk: int = 100) -> str:
        if len(b64) <= chunk:
            return f'"{b64}"'
        parts = [b64[i:i + chunk] for i in range(0, len(b64), chunk)]
        return "\n                + ".join(f'"{p}"' for p in parts)

    entries: list[str] = []
    for inv in invoices:
        b64 = _split_literal(inv.base64_bytes)
        entries.append(
            "            new EmbeddedInvoice(\n"
            f'                "{inv.file_name}",\n'
            f'                "{inv.vendor_hint}",\n'
            f'                "{inv.expected_currency}",\n'
            f"                {inv.expected_total}m,\n"
            f"                {b64}),\n"
        )
    entries_block = "".join(entries)

    return f"""using System;
using System.Collections.Generic;

namespace {namespace}
{{
    /// <summary>
    /// A real invoice PDF bundled inside the compiled .nupkg, with ground-truth
    /// metadata for business-rule + extraction-quality assertions.
    /// </summary>
    public sealed class EmbeddedInvoice
    {{
        public string FileName {{ get; }}
        public string VendorHint {{ get; }}
        public string ExpectedCurrency {{ get; }}
        public decimal ExpectedTotal {{ get; }}
        public string Base64Bytes {{ get; }}

        public EmbeddedInvoice(
            string fileName,
            string vendorHint,
            string expectedCurrency,
            decimal expectedTotal,
            string base64Bytes)
        {{
            FileName = fileName;
            VendorHint = vendorHint;
            ExpectedCurrency = expectedCurrency;
            ExpectedTotal = expectedTotal;
            Base64Bytes = base64Bytes;
        }}

        public byte[] PdfBytes => Convert.FromBase64String(Base64Bytes);
    }}

    public static class EmbeddedInvoices
    {{
        public static readonly List<EmbeddedInvoice> All = new List<EmbeddedInvoice>
        {{
{entries_block}        }};
    }}
}}
"""
