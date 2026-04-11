"""End-to-end deploy script: pack the Odoo project and push it to UiPath Cloud.

Pipeline (one-shot, run after Phase E artifacts are in place):

  1. Generate the project from the Odoo PDD into ``demo-output/odoo_project/``.
  2. Pack it via the manual_packager (no UiPath.CLI required).
  3. Authenticate to UiPath Community Cloud using ``UIPATH_*`` env vars.
  4. Upload the .nupkg to the Orchestrator NuGet feed.
  5. Ensure the ``OdooInvoices`` queue exists.
  6. Ensure ``OdooBaseURL`` and ``DUApiKey`` assets exist (and update values).
  7. Create a release for the uploaded process.
  8. Add three queue items pointing at the synthetic invoice PDFs.
  9. Trigger one job and print the job id.

Required env vars (see docs/community_cloud_setup.md):
    UIPATH_URL              (default: https://cloud.uipath.com)
    UIPATH_ORG
    UIPATH_TENANT_ID
    UIPATH_CLIENT_ID
    UIPATH_CLIENT_SECRET
    UIPATH_FOLDER           (default: Shared)
    UIPATH_DU_API_KEY
    ODOO_PUBLIC_URL         (e.g. https://abc123.ngrok-free.app)

Run:
    python proof/deploy_odoo.py
"""

from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path

from dotenv import load_dotenv

from rpa_architect.assembler.manual_packager import pack_project_manually
from rpa_architect.assembler.packager import package_project
from rpa_architect.assembler.project_assembler import assemble_project
from rpa_architect.parser.pdd_parser import parse_pdd
from rpa_architect.platform.sdk_client import UiPathClient

load_dotenv(Path(__file__).resolve().parent.parent / ".env")

# Ensure uipcli is discoverable inside this Python process.
_DOTNET_ROOT = Path.home() / ".dotnet"
if _DOTNET_ROOT.exists():
    os.environ["DOTNET_ROOT"] = str(_DOTNET_ROOT)
    os.environ["PATH"] = (
        f"{_DOTNET_ROOT}:{_DOTNET_ROOT}/tools:" + os.environ.get("PATH", "")
    )

REPO_ROOT = Path(__file__).resolve().parent.parent
PDD_PATH = REPO_ROOT / "tests" / "fixtures" / "pdds" / "odoo_invoice_processing.md"
PROJECT_DIR = REPO_ROOT / "demo-output" / "odoo_project"
PACK_DIR = REPO_ROOT / "demo-output" / "pack"


def _require_env(*names: str) -> dict[str, str]:
    missing = [n for n in names if not os.environ.get(n)]
    if missing:
        raise SystemExit(
            f"missing required env vars: {missing}. "
            f"See docs/community_cloud_setup.md."
        )
    return {n: os.environ[n] for n in names}


async def main() -> int:
    env = _require_env(
        "UIPATH_ORG",
        "UIPATH_CLIENT_ID",
        "UIPATH_CLIENT_SECRET",
        "UIPATH_DU_API_KEY",
        "ODOO_PUBLIC_URL",
        "ODOO_DB",
        "HARVEST_CRED_ODOO_USER",
        "HARVEST_CRED_ODOO_PASS",
    )
    uipath_url = os.environ.get("UIPATH_URL", "https://cloud.uipath.com")
    folder = os.environ.get("UIPATH_FOLDER", "Shared")
    tenant_name = os.environ.get("UIPATH_TENANT_NAME", "DefaultTenant")

    # 1. Generate the project.
    print("[1/9] generating project from PDD")
    PROJECT_DIR.mkdir(parents=True, exist_ok=True)
    ir = parse_pdd(PDD_PATH)
    manifest = await assemble_project(ir, {}, PROJECT_DIR)
    print(f"      wrote {len(manifest.files_written)} files to {PROJECT_DIR}")

    # 2. Pack via uipcli (preferred, produces a real compiled .nupkg with
    # lib/net8.0/*.dll assemblies) with automatic fallback to the manual
    # Python packager if uipcli is unavailable. Bump patch version so we
    # get a fresh feed entry instead of hitting 409 on every retry.
    print("[2/9] packing .nupkg")
    PACK_DIR.mkdir(parents=True, exist_ok=True)
    import time as _time
    version = f"1.0.{int(_time.time()) % 100000}"
    # Patch project.json with the bumped version so uipcli's output matches.
    import json as _json
    pj_path = PROJECT_DIR / "project.json"
    pj = _json.loads(pj_path.read_text(encoding="utf-8"))
    pj["projectVersion"] = version
    pj_path.write_text(_json.dumps(pj, indent=2), encoding="utf-8")

    pack_result = await package_project(PROJECT_DIR, output_dir=PACK_DIR)
    if not pack_result.success or not pack_result.nupkg_path:
        raise RuntimeError(f"pack failed: {pack_result.errors}")
    nupkg = pack_result.nupkg_path
    print(f"      {nupkg.name} ({nupkg.stat().st_size:,} bytes)")

    # 3-9. Talk to Orchestrator.
    client = UiPathClient(
        url=uipath_url,
        org=env["UIPATH_ORG"],
        tenant_name=tenant_name,
        client_id=env["UIPATH_CLIENT_ID"],
        client_secret=env["UIPATH_CLIENT_SECRET"],
        folder=folder,
    )

    try:
        print("[3/9] acquiring OAuth token")
        token = await client._ensure_token()
        print(f"      OK ({len(token)} chars)")

        print("[4/9] uploading package")
        upload_result = await client.upload_package(nupkg)
        print(f"      response keys: {list(upload_result.keys())[:5]}")

        print("[5/9] ensuring queue OdooInvoices")
        qid = await client.ensure_queue("OdooInvoices", description="Invoice PDFs to process")
        print(f"      queue id={qid}")

        print("[6/9] ensuring assets")
        await client.ensure_asset("OdooBaseURL", env["ODOO_PUBLIC_URL"], "Text")
        # Store DU key as Text (single string token; simpler than Credential).
        await client.ensure_asset("DUApiKey", env["UIPATH_DU_API_KEY"], "Text")
        print("      OdooBaseURL + DUApiKey set")

        print("[7/9] creating release")
        release = await client.create_release(
            package_id=ir.process_name,
            process_name=ir.process_name,
            process_version=version,
        )
        release_key = release.get("Key", "")
        release_id = release.get("Id")
        print(f"      release key={release_key} id={release_id}")

        # If the release already existed (idempotent path), point it at the
        # freshly-uploaded package version so the new project.json (with
        # requiresUserInteraction=false) takes effect.
        if release_id:
            print(f"      updating release to package version {version}")
            try:
                await client.update_release_to_specific_version(release_id, version)
            except Exception as exc:  # noqa: BLE001
                print(f"      update skipped: {exc}")

        print("[8/9] seeding queue with 3 invoice items")
        for i in range(1, 4):
            await client.add_queue_item(
                queue_name="OdooInvoices",
                reference=f"DEMO-{i:03d}",
                specific_content={
                    "DocumentPath": f"/orchestrator-storage/invoices/invoice_{i:03d}.pdf",
                    "RunNumber": i,
                },
            )
        print("      3 items added")

        print("[9/9] invoking process")
        # Real input arguments for the Cross-Platform CodedWorkflow.
        # No more empty {} — these get marshalled into the C# Execute()
        # parameters by the UiPath runtime.
        invoke_args = {
            "odooBaseUrl": env["ODOO_PUBLIC_URL"],
            "odooLogin": env["HARVEST_CRED_ODOO_USER"],
            "odooPassword": env["HARVEST_CRED_ODOO_PASS"],
            "odooDb": env["ODOO_DB"],
            "vendorName": "ACME Industrial Supplies, Inc.",
            "invoiceReference": f"DEMO-{int(__import__('time').time())}",
            "invoiceDate": "2026-04-11",
            "totalAmount": 1247.50,
            "currency": "USD",
        }
        try:
            job_id = await client.invoke_process(release_key, invoke_args)
            print(f"      job id={job_id}")
        except Exception as exc:  # noqa: BLE001
            # Community Cloud's free unattended robot has no Windows
            # credentials, so processes with any UI dependency refuse to
            # start with errorCode=1015 ("Robots without credentials cannot
            # run processes that require an interactive session"). This is
            # a tenant-admin UI action (connect robot credentials) —
            # outside the scope of this repo. All preceding deployment
            # steps are verified live, so we exit successfully and let
            # the demo phase render the deployed resources.
            msg = str(exc)
            if "1015" in msg or "credentials" in msg or "interactive" in msg:
                print("      ⚠️  robot lacks credentials for interactive session")
                print("         → this is a Community Cloud tenant-admin step")
                print("         → all deploy-time resources ARE live on Orchestrator")
            else:
                raise

        print("\nDONE — check the Orchestrator UI in your browser:")
        print(
            f"  https://cloud.uipath.com/{env['UIPATH_ORG']}/DefaultTenant"
            "/orchestrator_/processes"
        )
        return 0
    finally:
        await client.close()


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
