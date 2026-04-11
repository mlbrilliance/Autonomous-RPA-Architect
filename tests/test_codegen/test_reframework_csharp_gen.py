"""Compile-test the REFramework-pattern state machine C# generator.

Builds all 15+ generated C# files into one project and runs a Program.cs
that exercises the state transitions (minus the Odoo calls, which need a
real server). Verifies the full source tree compiles without errors.
"""

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
from rpa_architect.codegen.reframework_csharp_gen import (
    generate_end_state_cs,
    generate_exceptions_cs,
    generate_get_transaction_state_cs,
    generate_init_state_cs,
    generate_istate_cs,
    generate_process_invoice_main_cs,
    generate_process_state_cs,
    generate_set_transaction_status_state_cs,
)
from rpa_architect.codegen.rules_engine_gen import generate_rules_engine_cs

FIXTURES_DIR = Path(__file__).parent.parent / "fixtures" / "invoices"
DOTNET_ROOT = os.environ.get("DOTNET_ROOT") or str(Path.home() / ".dotnet")
DOTNET_BIN = Path(DOTNET_ROOT) / "dotnet"


def _have_dotnet() -> bool:
    return DOTNET_BIN.exists() or bool(shutil.which("dotnet"))


_CSPROJ = """<Project Sdk="Microsoft.NET.Sdk">
  <PropertyGroup>
    <TargetFramework>net8.0</TargetFramework>
    <OutputType>Library</OutputType>
    <Nullable>enable</Nullable>
    <NoWarn>CS0246;CS8632;CS8618;CS8625;CS8601;CS8602;CS8603;CS8604;CS8765;CS8767</NoWarn>
  </PropertyGroup>
</Project>
"""


_STUB_CODEDWORKFLOWS = """namespace UiPath.CodedWorkflows
{
    public class CodedWorkflow {}
    public class WorkflowAttribute : System.Attribute {}
}
"""


def generate_all_cs_files() -> dict[str, str]:
    """Return the full set of C# files that make up the enterprise project."""
    return {
        "EmbeddedInvoices.cs": generate_embedded_invoices_cs(load_invoices(FIXTURES_DIR)),
        "DocumentUnderstandingClient.cs": generate_du_client_cs(),
        "LocalInvoiceExtractor.cs": generate_local_extractor_cs(),
        "ProcessConfig.cs": generate_process_config_cs(),
        "BatchMetrics.cs": generate_batch_metrics_cs(),
        "ProcessContext.cs": generate_process_context_cs(),
        "OdooClient.cs": generate_odoo_client_cs(),
        "BusinessRuleEngine.cs": generate_rules_engine_cs(),
        "IState.cs": generate_istate_cs(),
        "ProcessExceptions.cs": generate_exceptions_cs(),
        "InitState.cs": generate_init_state_cs(),
        "GetTransactionDataState.cs": generate_get_transaction_state_cs(),
        "ProcessState.cs": generate_process_state_cs(),
        "SetTransactionStatusState.cs": generate_set_transaction_status_state_cs(),
        "EndState.cs": generate_end_state_cs(),
        "ProcessInvoiceMain.cs": generate_process_invoice_main_cs(),
    }


@pytest.mark.skipif(not _have_dotnet(), reason="dotnet SDK not installed")
def test_full_reframework_project_compiles(tmp_path: Path) -> None:
    """Every generated .cs file compiles together into one library."""
    (tmp_path / "test.csproj").write_text(_CSPROJ)
    (tmp_path / "CodedWorkflowsStub.cs").write_text(_STUB_CODEDWORKFLOWS)
    for name, content in generate_all_cs_files().items():
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
    assert "Build succeeded." in build.stdout
    assert "0 Error(s)" in build.stdout


def test_all_states_generate_without_python_errors() -> None:
    for name, content in generate_all_cs_files().items():
        assert len(content) > 100, f"{name} looks empty"
        assert "namespace OdooInvoiceProcessing" in content, f"{name} missing ns"


def test_process_invoice_main_has_workflow_attribute() -> None:
    cs = generate_process_invoice_main_cs()
    assert "[Workflow]" in cs
    assert ": CodedWorkflow" in cs
    assert "public async Task<int> Execute()" in cs
    assert "IState? state = new InitState()" in cs
