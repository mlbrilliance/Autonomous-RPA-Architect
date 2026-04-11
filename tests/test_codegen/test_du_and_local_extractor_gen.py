"""TDD: Compile-verify DocumentUnderstandingClient.cs + LocalInvoiceExtractor.cs."""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

import pytest

from rpa_architect.codegen.du_client_gen import generate_du_client_cs
from rpa_architect.codegen.embedded_invoices_gen import (
    generate_embedded_invoices_cs,
    load_invoices,
)
from rpa_architect.codegen.local_extractor_gen import generate_local_extractor_cs

FIXTURES_DIR = Path(__file__).parent.parent / "fixtures" / "invoices"
DOTNET_ROOT = os.environ.get("DOTNET_ROOT") or str(Path.home() / ".dotnet")
DOTNET_BIN = Path(DOTNET_ROOT) / "dotnet"


def _have_dotnet() -> bool:
    return DOTNET_BIN.exists() or bool(shutil.which("dotnet"))


_CSPROJ = """<Project Sdk="Microsoft.NET.Sdk">
  <PropertyGroup>
    <TargetFramework>net8.0</TargetFramework>
    <OutputType>Exe</OutputType>
    <Nullable>enable</Nullable>
    <NoWarn>CS0246;CS8632</NoWarn>
  </PropertyGroup>
</Project>
"""

_PROGRAM = """using System;
using System.Linq;
using OdooInvoiceProcessing;

class Program
{
    static int Main()
    {
        // 1. Embedded invoices load correctly.
        if (EmbeddedInvoices.All.Count != 5)
        {
            Console.Error.WriteLine($"expected 5 embedded invoices, got {EmbeddedInvoices.All.Count}");
            return 1;
        }
        // 2. LocalInvoiceExtractor returns real data for each.
        var extractor = new LocalInvoiceExtractor();
        foreach (var inv in EmbeddedInvoices.All)
        {
            var result = extractor.Extract(inv);
            if (result.VendorName != inv.VendorHint)
            {
                Console.Error.WriteLine($"vendor mismatch: {result.VendorName} != {inv.VendorHint}");
                return 2;
            }
            if (result.TotalAmount != inv.ExpectedTotal)
            {
                Console.Error.WriteLine($"total mismatch: {result.TotalAmount} != {inv.ExpectedTotal}");
                return 3;
            }
            if (result.Source != "local.groundtruth")
            {
                Console.Error.WriteLine($"source mismatch: {result.Source}");
                return 4;
            }
            if (result.Fields.Count != 5)
            {
                Console.Error.WriteLine($"expected 5 fields, got {result.Fields.Count}");
                return 5;
            }
            if (result.Fields.Any(f => f.Confidence < 0.9))
            {
                Console.Error.WriteLine("confidence too low");
                return 6;
            }
            Console.WriteLine($"{inv.FileName}: {result.VendorName} {result.TotalAmount} {result.Currency} conf={result.AvgConfidence}");
        }
        // 3. DocumentUnderstandingClient instantiates without throwing
        //    (construction is pure — no network call).
        var du = new DocumentUnderstandingClient(
            "https://cloud.uipath.com", "testorg", "testtenant",
            "project-guid", "client-id", "client-secret");
        Console.WriteLine("du client constructed");
        return 0;
    }
}
"""


@pytest.mark.skipif(not _have_dotnet(), reason="dotnet SDK not installed")
def test_du_and_local_extractor_compile_and_run(tmp_path: Path) -> None:
    (tmp_path / "test.csproj").write_text(_CSPROJ)
    (tmp_path / "EmbeddedInvoices.cs").write_text(
        generate_embedded_invoices_cs(load_invoices(FIXTURES_DIR))
    )
    (tmp_path / "DocumentUnderstandingClient.cs").write_text(generate_du_client_cs())
    (tmp_path / "LocalInvoiceExtractor.cs").write_text(generate_local_extractor_cs())
    (tmp_path / "Program.cs").write_text(_PROGRAM)

    env = os.environ.copy()
    env["DOTNET_ROOT"] = DOTNET_ROOT
    env["PATH"] = f"{DOTNET_ROOT}:{DOTNET_ROOT}/tools:{env.get('PATH', '')}"
    env["DOTNET_NOLOGO"] = "1"
    env["DOTNET_CLI_TELEMETRY_OPTOUT"] = "1"

    dn = str(DOTNET_BIN) if DOTNET_BIN.exists() else "dotnet"
    build = subprocess.run(
        [dn, "build", str(tmp_path / "test.csproj")],
        capture_output=True, text=True, env=env, timeout=300,
    )
    assert build.returncode == 0, (
        f"build failed:\nSTDOUT:\n{build.stdout}\nSTDERR:\n{build.stderr}"
    )
    run = subprocess.run(
        [dn, "run", "--project", str(tmp_path / "test.csproj"), "--no-build"],
        capture_output=True, text=True, env=env, timeout=120,
    )
    assert run.returncode == 0, (
        f"run failed (rc={run.returncode}):\nSTDOUT:\n{run.stdout}\nSTDERR:\n{run.stderr}"
    )
    # Every invoice's vendor must appear in the output.
    expected_vendors = [
        "ACME Industrial Supplies",
        "Globex Logistics",
        "Initech Software Services",
        "Umbrella Pharmaceuticals",
        "Stark Industries",
    ]
    for v in expected_vendors:
        assert v in run.stdout, f"{v} not in output:\n{run.stdout}"
    assert "du client constructed" in run.stdout
