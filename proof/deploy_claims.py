"""Deploy the three-process medical claims factory to UiPath Community Cloud.

Pipeline:
  1. Assemble three sibling project dirs (dispatcher/, performer/, reporter/)
  2. Rewrite AssetClient.cs in each with real env values so the compiled
     DLL has current SuiteCRM + UiPath credentials baked in (BW-07)
  3. Pack each project dir into a .nupkg
  4. OAuth to UiPath, ensure queue, upload all three packages, create
     three releases

Environment (all REQUIRED — see proof/suitecrm/.env.example for SuiteCRM):
  UIPATH_ORG
  UIPATH_TENANT_NAME       (default: DefaultTenant)
  UIPATH_CLIENT_ID
  UIPATH_CLIENT_SECRET
  UIPATH_FOLDER            (default: Shared)

  SUITECRM_PUBLIC_URL      (https://*.trycloudflare.com)
  SUITECRM_CLIENT_ID
  SUITECRM_CLIENT_SECRET
  SUITECRM_USERNAME
  SUITECRM_PASSWORD

Usage:
  python proof/deploy_claims.py              # live deploy
  python proof/deploy_claims.py --dry-run    # assemble + pack only
"""

from __future__ import annotations

import argparse
import asyncio
import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

from rpa_architect.assembler.claims_factory_assembler import assemble_claims_factory
from rpa_architect.assembler.packager import package_project
from rpa_architect.platform.sdk_client import UiPathClient


DOTNET_ROOT = os.environ.get("DOTNET_ROOT") or str(Path.home() / ".dotnet")
DOTNET_BIN = Path(DOTNET_ROOT) / "dotnet"

_CSPROJ = """<Project Sdk="Microsoft.NET.Sdk">
  <PropertyGroup>
    <TargetFramework>net8.0</TargetFramework>
    <OutputType>Library</OutputType>
    <AssemblyName>{assembly_name}</AssemblyName>
    <RootNamespace>MedicalClaimsProcessing</RootNamespace>
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


def _compile_project_to_dll(project_dir: Path, assembly_name: str) -> Path | None:
    """Compile C# files in project_dir to a DLL using `dotnet build`.

    The UiPath Community Cloud serverless runtime requires a pre-compiled
    DLL at ``lib/net8.0/{name}.dll`` inside the .nupkg. The manual packager
    doesn't compile — it just zips source files — so we need this extra
    step.

    Returns the path to the compiled DLL, or None on failure.
    """
    # Build dir MUST be OUTSIDE the project dir — uipcli recursively
    # discovers all .cs files and the symlinks in .build/ would create
    # "ambiguity between X and X" compile errors (CS0229/CS0121).
    build_dir = project_dir.parent / f".build-{project_dir.name}"
    build_dir.mkdir(exist_ok=True)

    # Write csproj
    (build_dir / "build.csproj").write_text(
        _CSPROJ.format(assembly_name=assembly_name),
        encoding="utf-8",
    )

    # Stub UiPath.CodedWorkflows
    (build_dir / "CodedWorkflowsStub.cs").write_text(
        _STUB_CODEDWORKFLOWS, encoding="utf-8"
    )

    # Symlink all .cs files from project_dir into build_dir
    for cs_file in project_dir.glob("*.cs"):
        link_target = build_dir / cs_file.name
        if not link_target.exists():
            link_target.symlink_to(cs_file.resolve())

    dn = str(DOTNET_BIN) if DOTNET_BIN.exists() else "dotnet"
    env = os.environ.copy()
    env["DOTNET_ROOT"] = DOTNET_ROOT
    env["PATH"] = f"{DOTNET_ROOT}:{DOTNET_ROOT}/tools:{env.get('PATH', '')}"
    env["DOTNET_NOLOGO"] = "1"
    env["DOTNET_CLI_TELEMETRY_OPTOUT"] = "1"

    result = subprocess.run(
        [dn, "build", str(build_dir / "build.csproj"),
         "-o", str(build_dir / "out")],
        capture_output=True, text=True, env=env, timeout=120,
    )

    if result.returncode != 0:
        print(f"  dotnet build FAILED for {assembly_name}:")
        print(result.stdout[-500:] if len(result.stdout) > 500 else result.stdout)
        return None

    dll_path = build_dir / "out" / f"{assembly_name}.dll"
    if not dll_path.exists():
        print(f"  DLL not found at {dll_path}")
        return None

    print(f"  compiled {assembly_name}.dll ({dll_path.stat().st_size} bytes)")
    return dll_path


REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_OUTPUT = REPO_ROOT / "demo-output" / "claims_factory"
NAMESPACE = "MedicalClaimsProcessing"
QUEUE_NAME = "MedicalClaims"


def _require_env(*names: str) -> dict[str, str]:
    missing = [n for n in names if not os.environ.get(n)]
    if missing:
        raise SystemExit(
            f"error: missing env vars: {', '.join(missing)}. "
            "See proof/suitecrm/.env.example + .env at repo root."
        )
    return {n: os.environ[n] for n in names}


def rewrite_asset_client(path: Path, substitutions: dict[str, str]) -> None:
    """Replace every placeholder constant in AssetClient.cs with a real value.

    The generator at ``src/rpa_architect/codegen/dispatcher_gen.py`` emits
    placeholders like ``"__SUITECRM_BASE_URL__"`` which this function
    replaces with real env values before packing. Idempotent — running
    twice with the same substitutions yields the same output.
    """
    content = path.read_text(encoding="utf-8")
    for placeholder, real_value in substitutions.items():
        content = content.replace(placeholder, real_value)
    path.write_text(content, encoding="utf-8")


async def main(
    output_dir: Path | None = None,
    dry_run: bool = False,
) -> dict[str, Any]:
    """Run the deploy pipeline.

    Returns a dict with keys:
      assembled     — True if 3 project dirs were produced
      packaged      — count of .nupkg files produced
      uploaded      — count successfully uploaded (0 on dry-run)
      release_keys  — list of Orchestrator release keys (empty on dry-run)
    """
    output_dir = output_dir or DEFAULT_OUTPUT
    output_dir = Path(output_dir)

    print(f"[1/7] assembling three sibling projects under {output_dir}")
    projects = assemble_claims_factory(
        namespace=NAMESPACE,
        output_dir=output_dir,
    )
    assembled_ok = all(p.exists() for p in projects.values())

    # Credentials for AssetClient rewrite (required in both dry-run and
    # live mode so the packaged DLL has working creds baked in).
    env = _require_env(
        "UIPATH_ORG",
        "UIPATH_CLIENT_ID",
        "UIPATH_CLIENT_SECRET",
        "SUITECRM_PUBLIC_URL",
        "SUITECRM_CLIENT_ID",
        "SUITECRM_CLIENT_SECRET",
        "SUITECRM_USERNAME",
        "SUITECRM_PASSWORD",
    )
    folder = os.environ.get("UIPATH_FOLDER", "Shared")
    tenant_name = os.environ.get("UIPATH_TENANT_NAME", "DefaultTenant")
    uipath_url = os.environ.get("UIPATH_URL", "https://cloud.uipath.com")

    orchestrator_base = (
        f"{uipath_url}/{env['UIPATH_ORG']}/{tenant_name}/orchestrator_/odata"
    )

    substitutions = {
        "__SUITECRM_BASE_URL__": env["SUITECRM_PUBLIC_URL"],
        "__SUITECRM_CLIENT_ID__": env["SUITECRM_CLIENT_ID"],
        "__SUITECRM_CLIENT_SECRET__": env["SUITECRM_CLIENT_SECRET"],
        "__SUITECRM_USERNAME__": env["SUITECRM_USERNAME"],
        "__SUITECRM_PASSWORD__": env["SUITECRM_PASSWORD"],
        "__UIPATH_IDENTITY_URL__": uipath_url,
        "__UIPATH_ORCHESTRATOR_URL__": orchestrator_base,
        "__UIPATH_CLIENT_ID__": env["UIPATH_CLIENT_ID"],
        "__UIPATH_CLIENT_SECRET__": env["UIPATH_CLIENT_SECRET"],
        "__UIPATH_FOLDER_ID__": "7747906",  # Shared folder — resolved from Orchestrator API
    }

    print("[2/7] rewriting AssetClient.cs placeholders with real values")
    for name, proj in projects.items():
        rewrite_asset_client(proj / "AssetClient.cs", substitutions)

    # Compile C# to DLL first — the robot needs a pre-compiled assembly.
    project_assemblies = {
        "dispatcher": "ClaimsDispatcher",
        "performer": "ClaimsPerformer",
        "reporter": "ClaimsReporter",
    }
    print("[3/8] compiling C# → DLL via dotnet build")
    dlls: dict[str, Path] = {}
    for name, proj in projects.items():
        asm_name = project_assemblies[name]
        dll = _compile_project_to_dll(proj, asm_name)
        if dll:
            dlls[name] = dll
        else:
            print(f"  WARNING: {name} compilation failed; proceeding with source-only")

    print("[4/8] packing three .nupkgs")
    nupkg_paths: list[Path] = []
    for name, proj in projects.items():
        result = await package_project(proj)
        # package_project returns a PackageResult with .nupkg_path on success
        if hasattr(result, "nupkg_path") and result.nupkg_path:
            nupkg_path = Path(result.nupkg_path)
        elif isinstance(result, Path):
            nupkg_path = result
        else:
            nupkg_path = Path(result)

        # Inject the compiled DLL into the nupkg under lib/net8.0/
        if name in dlls:
            import zipfile
            with zipfile.ZipFile(nupkg_path, "a") as z:
                dll = dlls[name]
                z.write(dll, f"lib/net8.0/{dll.name}")
            print(f"      packed {name} → {nupkg_path.name} (with DLL)")
        else:
            print(f"      packed {name} → {nupkg_path.name} (source-only)")

        nupkg_paths.append(nupkg_path)

    if dry_run:
        print("[dry-run] skipping upload / release / queue")
        return {
            "assembled": assembled_ok,
            "packaged": len(nupkg_paths),
            "uploaded": 0,
            "release_keys": [],
        }

    # Live path
    print("[5/8] authenticating to UiPath Orchestrator")
    client = UiPathClient(
        url=uipath_url,
        org=env["UIPATH_ORG"],
        tenant_name=tenant_name,
        client_id=env["UIPATH_CLIENT_ID"],
        client_secret=env["UIPATH_CLIENT_SECRET"],
        folder=folder,
    )
    try:
        await client._ensure_token()

        print(f"[6/8] ensuring queue {QUEUE_NAME}")
        await client.ensure_queue(
            QUEUE_NAME, "Medical claims for the v0.6 factory"
        )

        print("[7/8] uploading three packages")
        uploaded = 0
        for nupkg in nupkg_paths:
            await client.upload_package(nupkg)
            uploaded += 1
            print(f"      uploaded {nupkg.name}")

        print("[8/8] creating three releases")
        release_keys: list[str] = []
        # Package names must match the `name` field in project.json, which
        # the assembler sets to "ClaimsDispatcher" / "ClaimsPerformer" /
        # "ClaimsReporter" (see claims_factory_assembler.py).
        project_names = {
            "dispatcher": "ClaimsDispatcher",
            "performer": "ClaimsPerformer",
            "reporter": "ClaimsReporter",
        }
        for name, pkg_name in project_names.items():
            try:
                # ProcessKey must match the uploaded package's Id field
                # (= project.json name), NOT a custom display name.
                release_data = await client._request(
                    "POST",
                    "Releases",
                    json={
                        "Name": f"MedicalClaims.{name.capitalize()}",
                        "ProcessKey": pkg_name,
                        "ProcessVersion": "1.0.0",
                        "Description": "Claims factory v0.6",
                    },
                )
                release_key = str(release_data.get("Key", ""))
                release_keys.append(release_key)
                print(f"      release created: {name} → {release_key}")
            except Exception as exc:
                print(f"      release creation for {name} failed: {exc}")

        return {
            "assembled": assembled_ok,
            "packaged": len(nupkg_paths),
            "uploaded": uploaded,
            "release_keys": release_keys,
        }
    finally:
        await client.close()


def _cli() -> int:
    parser = argparse.ArgumentParser(description="Deploy the claims factory.")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Assemble + pack but skip upload/release/queue",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help="Output directory (default: demo-output/claims_factory)",
    )
    args = parser.parse_args()

    result = asyncio.run(main(output_dir=args.output, dry_run=args.dry_run))
    print(f"\nfinal: {result}")
    return 0 if result["assembled"] and result["packaged"] == 3 else 1


if __name__ == "__main__":
    raise SystemExit(_cli())
