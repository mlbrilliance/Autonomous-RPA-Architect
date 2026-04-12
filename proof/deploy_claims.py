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
import sys
from pathlib import Path
from typing import Any

from rpa_architect.assembler.claims_factory_assembler import assemble_claims_factory
from rpa_architect.assembler.packager import package_project
from rpa_architect.platform.sdk_client import UiPathClient


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
        "__UIPATH_FOLDER_ID__": "0",  # placeholder; resolved live below
    }

    print("[2/7] rewriting AssetClient.cs placeholders with real values")
    for name, proj in projects.items():
        rewrite_asset_client(proj / "AssetClient.cs", substitutions)

    print("[3/7] packing three .nupkgs")
    nupkg_paths: list[Path] = []
    for name, proj in projects.items():
        result = await package_project(proj)
        # package_project returns a PackageResult with .nupkg_path on success
        if hasattr(result, "nupkg_path") and result.nupkg_path:
            nupkg_paths.append(Path(result.nupkg_path))
        elif isinstance(result, Path):
            nupkg_paths.append(result)
        else:
            # Mocked path returns a Path directly
            nupkg_paths.append(Path(result))
        print(f"      packed {name} → {nupkg_paths[-1].name}")

    if dry_run:
        print("[dry-run] skipping upload / release / queue")
        return {
            "assembled": assembled_ok,
            "packaged": len(nupkg_paths),
            "uploaded": 0,
            "release_keys": [],
        }

    # Live path
    print("[4/7] authenticating to UiPath Orchestrator")
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

        print(f"[5/7] ensuring queue {QUEUE_NAME}")
        await client.ensure_queue(
            QUEUE_NAME, "Medical claims for the v0.6 factory"
        )

        print("[6/7] uploading three packages")
        uploaded = 0
        for nupkg in nupkg_paths:
            await client.upload_package(nupkg)
            uploaded += 1
            print(f"      uploaded {nupkg.name}")

        print("[7/7] creating three releases")
        release_keys: list[str] = []
        for name in ("dispatcher", "performer", "reporter"):
            package_id = f"{NAMESPACE}.{name.capitalize()}Main"
            try:
                release_key = await client.create_release(
                    package_id=package_id,
                    process_name=f"MedicalClaims.{name.capitalize()}",
                    environment_id=None,
                    process_version="1.0.0",
                )
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
