"""Tests for the embedded-invoices C# generator + compile verification."""

from __future__ import annotations

import base64
import os
import shutil
import subprocess
from pathlib import Path

import pytest

from rpa_architect.codegen.embedded_invoices_gen import (
    EmbeddedInvoice,
    generate_embedded_invoices_cs,
    load_invoices,
)

FIXTURES_DIR = Path(__file__).parent.parent / "fixtures" / "invoices"
DOTNET_ROOT = os.environ.get("DOTNET_ROOT") or str(Path.home() / ".dotnet")
DOTNET_BIN = Path(DOTNET_ROOT) / "dotnet"


def _have_dotnet() -> bool:
    return DOTNET_BIN.exists() or bool(shutil.which("dotnet"))


def test_load_invoices_reads_five_pdfs() -> None:
    invoices = load_invoices(FIXTURES_DIR)
    assert len(invoices) == 5
    for inv in invoices:
        assert inv.file_name.endswith(".pdf")
        assert inv.vendor_hint
        assert inv.expected_currency in {"USD", "EUR", "GBP"}
        assert inv.expected_total > 0


def test_loaded_invoices_have_valid_base64() -> None:
    invoices = load_invoices(FIXTURES_DIR)
    for inv in invoices:
        decoded = base64.b64decode(inv.base64_bytes)
        assert decoded[:5] == b"%PDF-", f"{inv.file_name} b64 roundtrip invalid"


def test_generate_cs_contains_all_five_invoices() -> None:
    invoices = load_invoices(FIXTURES_DIR)
    cs = generate_embedded_invoices_cs(invoices)
    for inv in invoices:
        assert inv.file_name in cs
        assert inv.vendor_hint in cs
        assert inv.expected_currency in cs
    assert "public static readonly List<EmbeddedInvoice> All" in cs
    assert "public byte[] PdfBytes" in cs


def test_generate_cs_uses_correct_namespace() -> None:
    cs = generate_embedded_invoices_cs(
        load_invoices(FIXTURES_DIR), namespace="MyCorp.Invoices"
    )
    assert "namespace MyCorp.Invoices" in cs


@pytest.mark.skipif(not _have_dotnet(), reason="dotnet SDK not installed")
def test_generated_embedded_invoices_compiles(tmp_path: Path) -> None:
    """``dotnet build`` must accept the generated C# file."""
    invoices = load_invoices(FIXTURES_DIR)
    cs = generate_embedded_invoices_cs(invoices)

    (tmp_path / "test.csproj").write_text(
        """<Project Sdk="Microsoft.NET.Sdk">
  <PropertyGroup>
    <TargetFramework>net8.0</TargetFramework>
    <OutputType>Exe</OutputType>
    <Nullable>enable</Nullable>
    <NoWarn>CS0246;CS8632</NoWarn>
  </PropertyGroup>
</Project>
"""
    )
    (tmp_path / "EmbeddedInvoices.cs").write_text(cs)
    # Smoke program that decodes the bytes — forces the compiler to
    # exercise every base64 literal.
    (tmp_path / "Program.cs").write_text(
        """using System;
using OdooInvoiceProcessing;

class Program
{
    static int Main()
    {
        foreach (var inv in EmbeddedInvoices.All)
        {
            var bytes = inv.PdfBytes;
            if (bytes.Length == 0) return 1;
            if (bytes[0] != 0x25 || bytes[1] != 0x50)  // %P
                return 2;
            Console.WriteLine($"{inv.FileName}: {bytes.Length} bytes, {inv.VendorHint}");
        }
        return 0;
    }
}
"""
    )

    env = os.environ.copy()
    env["DOTNET_ROOT"] = DOTNET_ROOT
    env["PATH"] = f"{DOTNET_ROOT}:{DOTNET_ROOT}/tools:{env.get('PATH', '')}"
    env["DOTNET_NOLOGO"] = "1"
    env["DOTNET_CLI_TELEMETRY_OPTOUT"] = "1"

    # Build
    result = subprocess.run(
        [str(DOTNET_BIN) if DOTNET_BIN.exists() else "dotnet",
         "build", str(tmp_path / "test.csproj")],
        capture_output=True, text=True, env=env, timeout=300,
    )
    assert result.returncode == 0, (
        f"build failed:\nSTDOUT:\n{result.stdout}\nSTDERR:\n{result.stderr}"
    )
    assert "Build succeeded." in result.stdout

    # Actually run the compiled program and assert every invoice decodes.
    run_result = subprocess.run(
        [str(DOTNET_BIN) if DOTNET_BIN.exists() else "dotnet",
         "run", "--project", str(tmp_path / "test.csproj"), "--no-build"],
        capture_output=True, text=True, env=env, timeout=60,
    )
    assert run_result.returncode == 0, (
        f"run failed:\nSTDOUT:\n{run_result.stdout}\nSTDERR:\n{run_result.stderr}"
    )
    assert "ACME Industrial Supplies" in run_result.stdout
    assert "Globex Logistics" in run_result.stdout
    assert "Initech Software Services" in run_result.stdout
    assert "Umbrella Pharmaceuticals" in run_result.stdout
    assert "Stark Industries" in run_result.stdout
