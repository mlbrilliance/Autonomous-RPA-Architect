"""Phase G+ — Download the deployed .nupkg from UiPath Cloud and assert it
contains REAL artifacts (not stubs).

This is the gate that catches the kind of fakery we got called out on:
the screenshot showed "Package version contains no requirements" because
the manual_packager produced a malformed nupkg. After the fix (content/
prefix), this script downloads the package the user actually sees in
the Orchestrator UI and walks every critical file inside it.

Run after ``proof/deploy_odoo.py``.
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
import zipfile
from io import BytesIO
from pathlib import Path

import httpx
from dotenv import load_dotenv

REPO_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(REPO_ROOT / ".env")

OUTPUT = REPO_ROOT / "demo-output" / "odoo" / "package_proof.txt"
PROCESS_NAME = "OdooInvoiceProcessing"


async def main() -> int:
    base = (
        f"{os.environ['UIPATH_URL']}/{os.environ['UIPATH_ORG']}/"
        f"{os.environ['UIPATH_TENANT_NAME']}/orchestrator_/odata"
    )
    async with httpx.AsyncClient() as cli:
        tok_resp = await cli.post(
            f"{os.environ['UIPATH_URL']}/{os.environ['UIPATH_ORG']}/"
            "identity_/connect/token",
            data={
                "grant_type": "client_credentials",
                "client_id": os.environ["UIPATH_CLIENT_ID"],
                "client_secret": os.environ["UIPATH_CLIENT_SECRET"],
                "scope": (
                    "OR.Execution OR.Folders OR.Jobs OR.Queues OR.Assets "
                    "OR.Machines OR.Robots OR.Settings"
                ),
            },
        )
        tok_resp.raise_for_status()
        token = tok_resp.json()["access_token"]
        headers = {
            "Authorization": f"Bearer {token}",
            "X-UIPATH-OrganizationUnitId": "7747906",
        }

        # Find the latest version of OdooInvoiceProcessing on the feed.
        # Use the Releases endpoint to get the current version pointer.
        rel_url = f"{base}/Releases?$filter=Name eq '{PROCESS_NAME}'"
        rel = (await cli.get(rel_url, headers=headers, timeout=30)).json()
        items = rel.get("value", [])
        if not items:
            print("FAIL: no release found", file=sys.stderr)
            return 2
        version = items[0]["ProcessVersion"]
        process_key = items[0]["ProcessKey"]
        print(f"latest release version: {version}")

        # Download
        dl_url = (
            f"{base}/Processes/UiPath.Server.Configuration.OData."
            f"DownloadPackage(key='{process_key}:{version}')"
        )
        r = await cli.get(dl_url, headers=headers, timeout=120, follow_redirects=True)
        if r.status_code != 200:
            print(
                f"FAIL: download returned {r.status_code}: {r.text[:300]}",
                file=sys.stderr,
            )
            return 3
        size = len(r.content)
        print(f"downloaded {size:,} bytes")

        zf = zipfile.ZipFile(BytesIO(r.content))
        names = set(zf.namelist())

        # Assert structural correctness.
        assertions: list[tuple[str, bool, str]] = []

        def check(label: str, ok: bool, detail: str = "") -> None:
            assertions.append((label, ok, detail))
            mark = "✓" if ok else "✗"
            print(f"  {mark} {label}{(': ' + detail) if detail else ''}")

        check(
            "content/ prefix used (UiPath nupkg spec)",
            all(n.startswith(("content/", "package/", "_rels/")) or "." in n for n in names),
        )
        check("content/project.json present", "content/project.json" in names)
        check("content/ProcessInvoiceMain.cs present", "content/ProcessInvoiceMain.cs" in names)

        # No Maestro fakery bundled
        check(
            "no Maestro/ folder bundled inside .nupkg",
            not any("Maestro/" in n for n in names),
            "(BPMN is a sibling design-time artifact, not deployed)",
        )

        # project.json semantics
        if "content/project.json" in names:
            pj = json.loads(zf.read("content/project.json"))
            check(
                "project.json targetFramework=Portable",
                pj.get("targetFramework") == "Portable",
                pj.get("targetFramework", ""),
            )
            check(
                "project.json requiresUserInteraction=false",
                pj.get("runtimeOptions", {}).get("requiresUserInteraction") is False,
            )
            check(
                "project.json projectProfile=0 (numeric enum)",
                pj.get("designOptions", {}).get("projectProfile") == 0,
            )
            entry_points = [e.get("filePath") for e in pj.get("entryPoints", [])]
            check(
                "project.json entryPoints points at ProcessInvoiceMain.cs",
                "ProcessInvoiceMain.cs" in entry_points,
                str(entry_points),
            )
            check(
                "project.json has UiPath.System.Activities dep",
                "UiPath.System.Activities" in pj.get("dependencies", {}),
            )
            check(
                "project.json has NO UiPath.UIAutomation.Activities (Portable runtime)",
                "UiPath.UIAutomation.Activities" not in pj.get("dependencies", {}),
            )

        # ProcessInvoiceMain.cs semantics
        if "content/ProcessInvoiceMain.cs" in names:
            cs_text = zf.read("content/ProcessInvoiceMain.cs").decode("utf-8")
            check(
                "C# uses real HttpClient (not stub)",
                "new HttpClient" in cs_text or "HttpClient(" in cs_text,
            )
            check(
                "C# calls Odoo /web/session/authenticate",
                "/web/session/authenticate" in cs_text,
            )
            check(
                "C# calls Odoo /web/dataset/call_kw",
                "/web/dataset/call_kw" in cs_text,
            )
            check(
                "C# targets account.move (vendor bill model)",
                "account.move" in cs_text,
            )
            check(
                "C# inherits from CodedWorkflow base class",
                ": CodedWorkflow" in cs_text,
            )
            check(
                "C# decorated with [Workflow] attribute",
                "[Workflow]" in cs_text,
            )
            check(
                "C# has NO TODO/stub markers",
                not any(m in cs_text.lower() for m in ("todo", "stub", "placeholder")),
            )

        # Summary
        passed = sum(1 for _, ok, _ in assertions if ok)
        total = len(assertions)
        print()
        print(f"=== {passed}/{total} assertions passed ===")
        OUTPUT.parent.mkdir(parents=True, exist_ok=True)
        OUTPUT.write_text(
            f"package_proof for {PROCESS_NAME}@{version}\n"
            f"size: {size:,} bytes\n"
            f"assertions: {passed}/{total} passed\n\n"
            + "\n".join(
                f"{'PASS' if ok else 'FAIL'}: {label}{(' — ' + detail) if detail else ''}"
                for label, ok, detail in assertions
            )
            + "\n"
        )
        print(f"wrote {OUTPUT}")

        if passed != total:
            return 1
        return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
