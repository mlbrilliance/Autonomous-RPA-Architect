"""Compile-test the full Models + OdooClient + BusinessRuleEngine stack."""

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
from rpa_architect.codegen.models_gen import (
    generate_batch_metrics_cs,
    generate_process_config_cs,
    generate_process_context_cs,
)
from rpa_architect.codegen.odoo_client_gen import generate_odoo_client_cs
from rpa_architect.codegen.rules_engine_gen import generate_rules_engine_cs

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
    <NoWarn>CS0246;CS8632;CS8618;CS8625;CS8601;CS8602;CS8603;CS8604;CS8765;CS8767</NoWarn>
  </PropertyGroup>
</Project>
"""


_PROGRAM = """using System;
using System.Collections.Generic;
using System.Threading.Tasks;
using OdooInvoiceProcessing;

class Program
{
    static async Task<int> Main()
    {
        var invoices = EmbeddedInvoices.All;
        var extractor = new LocalInvoiceExtractor();
        var config = new ProcessConfig
        {
            OdooBaseUrl = "http://localhost:8069",
            AmountThresholdUsd = 2000m,  // deliberately low so $2850 Stark flags
            AllowedCurrencies = new List<string> { "USD", "EUR", "GBP" },
        };
        // Don't actually talk to Odoo — skip rules that hit Odoo.
        var engine = new BusinessRuleEngine(new IRule[]
        {
            new CurrencyWhitelistRule(),
            new AmountThresholdRule(),
        });
        int passed = 0, flagged = 0, rejected = 0;
        foreach (var inv in invoices)
        {
            var doc = extractor.Extract(inv);
            var ctx = new RuleContext
            {
                Document = doc,
                SourceInvoice = inv,
                Config = config,
                // Odoo left null because the two rules above don't use it.
            };
            var result = await engine.EvaluateAsync(ctx);
            Console.WriteLine($"{inv.FileName}: {result.FinalVerdict} — {result.Summary}");
            switch (result.FinalVerdict)
            {
                case RuleVerdict.AutoProcess: passed++; break;
                case RuleVerdict.FlagForReview: flagged++; break;
                case RuleVerdict.Reject: rejected++; break;
            }
        }
        Console.WriteLine($"summary: passed={passed} flagged={flagged} rejected={rejected}");
        // With threshold 2000 USD: EUR 1925*1.08=2079 flags, GBP 660*1.27=838 passes,
        // USD 2850 flags, USD 525 passes, USD 374 passes -> 3 pass, 2 flag, 0 reject.
        if (rejected != 0) return 1;
        if (flagged < 1) return 2;
        return 0;
    }
}
"""


@pytest.mark.skipif(not _have_dotnet(), reason="dotnet SDK not installed")
def test_full_project_compiles_and_runs_rules(tmp_path: Path) -> None:
    (tmp_path / "test.csproj").write_text(_CSPROJ)
    files = {
        "EmbeddedInvoices.cs": generate_embedded_invoices_cs(load_invoices(FIXTURES_DIR)),
        "DocumentUnderstandingClient.cs": generate_du_client_cs(),
        "LocalInvoiceExtractor.cs": generate_local_extractor_cs(),
        "ProcessConfig.cs": generate_process_config_cs(),
        "BatchMetrics.cs": generate_batch_metrics_cs(),
        "ProcessContext.cs": generate_process_context_cs(),
        "OdooClient.cs": generate_odoo_client_cs(),
        "BusinessRuleEngine.cs": generate_rules_engine_cs(),
        "Program.cs": _PROGRAM,
    }
    for name, content in files.items():
        (tmp_path / name).write_text(content)

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
        f"run rc={run.returncode}:\nSTDOUT:\n{run.stdout}\nSTDERR:\n{run.stderr}"
    )
    assert "summary: passed=" in run.stdout
    assert "FlagForReview" in run.stdout or "flagged=" in run.stdout
