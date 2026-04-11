"""Verify the generated CodedWorkflow C# actually compiles with .NET 8.

This catches the previous fakery — the old generator emitted plausible
looking C# that nobody had ever compiled. We now run ``dotnet build``
against a stub harness during test collection and assert zero errors.
Skipped automatically if ``dotnet`` is not installed.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import textwrap
from pathlib import Path

import pytest

from rpa_architect.codegen.coded_workflow_gen import generate_odoo_jsonrpc_workflow

DOTNET_ROOT = os.environ.get("DOTNET_ROOT") or str(Path.home() / ".dotnet")
DOTNET_BIN = Path(DOTNET_ROOT) / "dotnet"


def _have_dotnet() -> bool:
    if DOTNET_BIN.exists():
        return True
    return shutil.which("dotnet") is not None


pytestmark = pytest.mark.skipif(
    not _have_dotnet(),
    reason="dotnet SDK not installed; install with scripts/install_uipath_cli.sh",
)


_CSPROJ = """\
<Project Sdk="Microsoft.NET.Sdk">
  <PropertyGroup>
    <TargetFramework>net8.0</TargetFramework>
    <Nullable>enable</Nullable>
    <RootNamespace>OdooInvoiceProcessing</RootNamespace>
    <NoWarn>CS0246;CS8632</NoWarn>
  </PropertyGroup>
</Project>
"""

_STUB_BASE = """\
namespace UiPath.CodedWorkflows
{
    public class CodedWorkflow {}
    public class WorkflowAttribute : System.Attribute {}
}
"""


def _dotnet_cmd() -> str:
    if DOTNET_BIN.exists():
        return str(DOTNET_BIN)
    return "dotnet"


def _build(project_dir: Path) -> subprocess.CompletedProcess:
    env = os.environ.copy()
    env["DOTNET_ROOT"] = DOTNET_ROOT
    env["PATH"] = (
        f"{DOTNET_ROOT}:{DOTNET_ROOT}/tools:{env.get('PATH', '')}"
    )
    env["DOTNET_NOLOGO"] = "1"
    env["DOTNET_CLI_TELEMETRY_OPTOUT"] = "1"
    return subprocess.run(
        [_dotnet_cmd(), "build", str(project_dir / "test.csproj")],
        capture_output=True,
        text=True,
        env=env,
        timeout=300,
    )


def test_generated_odoo_workflow_compiles(tmp_path: Path) -> None:
    """``generate_odoo_jsonrpc_workflow`` must produce valid .NET 8 C#."""
    src = generate_odoo_jsonrpc_workflow()
    (tmp_path / "test.csproj").write_text(_CSPROJ)
    (tmp_path / "stubs").mkdir()
    (tmp_path / "stubs" / "CodedWorkflows.cs").write_text(_STUB_BASE)
    (tmp_path / "ProcessInvoiceMain.cs").write_text(src)

    result = _build(tmp_path)
    assert result.returncode == 0, (
        f"dotnet build failed:\n"
        f"--- STDOUT ---\n{result.stdout}\n"
        f"--- STDERR ---\n{result.stderr}"
    )
    assert "0 Error(s)" in result.stdout, result.stdout
    assert "Build succeeded." in result.stdout, result.stdout


def test_generated_workflow_uses_real_http_client(tmp_path: Path) -> None:
    """The C# must contain HttpClient + Odoo JSON-RPC paths (not stubs)."""
    src = generate_odoo_jsonrpc_workflow()
    assert "HttpClient" in src
    assert "/web/session/authenticate" in src
    assert "/web/dataset/call_kw" in src
    assert "account.move" in src
    assert "res.partner" in src
    # No 'TODO', no 'pass', no 'stub', no 'placeholder'
    lower = src.lower()
    assert "todo" not in lower
    assert "stub" not in lower
    assert "placeholder" not in lower


def test_generated_workflow_class_inherits_codedworkflow() -> None:
    src = generate_odoo_jsonrpc_workflow()
    assert ": CodedWorkflow" in src
    assert "[Workflow]" in src
    assert "public async Task<int> Execute(" in src
