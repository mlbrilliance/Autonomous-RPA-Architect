"""Live selector harvest against a running Odoo Community instance.

Launches Playwright Chromium, logs into Odoo, navigates to the Vendor Bill
form, harvests selectors from each page, scores them, and writes the result
to ``demo-output/odoo/ObjectRepository/`` via the project's Object Repository
v2 generator.

Run after starting Odoo locally (see ``proof/odoo/docker-compose.yml``) and
after seeding the database (see ``proof/odoo/seed_database.py``).

Env vars (loaded from ``.env``, all REQUIRED — no hardcoded defaults):
  HARVEST_CRED_ODOO_USER  — Odoo login you created via the web UI
  HARVEST_CRED_ODOO_PASS  — the password you set for that login
  ODOO_BASE_URL           — default: http://localhost:8069
  HARVEST_HEADED          — default: false — set 'true' to show the browser
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
from pathlib import Path

# These imports are gated so the file imports cleanly in environments where
# Playwright isn't installed (e.g., during pytest collection on CI).
try:
    from playwright.async_api import async_playwright
except ImportError:  # pragma: no cover
    async_playwright = None  # type: ignore[assignment]


REPO_ROOT = Path(__file__).resolve().parent.parent
OUTPUT_DIR = REPO_ROOT / "demo-output" / "odoo"
OBJECT_REPO_DIR = OUTPUT_DIR / "ObjectRepository"

ODOO_BASE_URL = os.environ.get("ODOO_BASE_URL", "http://localhost:8069")
USER = os.environ.get("HARVEST_CRED_ODOO_USER") or ""
PASSWORD = os.environ.get("HARVEST_CRED_ODOO_PASS") or ""
HEADED = os.environ.get("HARVEST_HEADED", "false").lower() in ("1", "true", "yes")

if not USER or not PASSWORD:
    raise SystemExit(
        "error: HARVEST_CRED_ODOO_USER and HARVEST_CRED_ODOO_PASS must be "
        "set in your .env. See proof/odoo/.env.example for the template."
    )

PAGES_TO_HARVEST = [
    ("login", "/web/login"),
    ("dashboard", "/odoo"),
    ("vendor_bill_list", "/odoo/action-account.action_move_in_invoice_type"),
    ("vendor_bill_form", "/odoo/action-account.action_move_in_invoice_type/new"),
]


async def harvest() -> dict:
    if async_playwright is None:
        raise RuntimeError(
            "playwright is not installed. Install with: "
            "pip install -e .[harvest] && playwright install chromium"
        )

    OBJECT_REPO_DIR.mkdir(parents=True, exist_ok=True)
    captured: dict[str, list[dict]] = {}

    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=not HEADED)
        context = await browser.new_context(viewport={"width": 1920, "height": 1080})
        page = await context.new_page()

        # 1. Log in.
        print(f"[harvest] navigating to {ODOO_BASE_URL}/web/login")
        await page.goto(f"{ODOO_BASE_URL}/web/login", wait_until="networkidle")
        await page.fill('input[name="login"]', USER)
        await page.fill('input[name="password"]', PASSWORD)
        await page.click('button[type="submit"]')
        await page.wait_for_url("**/odoo*", timeout=30000)
        print(f"[harvest] logged in: {page.url}")

        # 2. For each target page, harvest visible interactive elements.
        for label, path in PAGES_TO_HARVEST[1:]:
            url = f"{ODOO_BASE_URL}{path}"
            print(f"[harvest] visiting {label}: {url}")
            try:
                await page.goto(url, wait_until="networkidle", timeout=60000)
            except Exception as exc:  # noqa: BLE001
                print(f"[harvest]   skip ({exc})")
                continue

            elements = await page.evaluate(
                """() => {
                    const out = [];
                    const sels = ['input', 'button', 'select', 'textarea',
                                  'a[href]', '[role="button"]', '[name]'];
                    document.querySelectorAll(sels.join(',')).forEach(el => {
                        if (el.offsetParent === null) return;
                        out.push({
                            tag: el.tagName.toLowerCase(),
                            id: el.id || null,
                            name: el.getAttribute('name'),
                            type: el.getAttribute('type'),
                            class: el.className,
                            text: (el.innerText || '').trim().slice(0, 80),
                            data_menu_xmlid: el.getAttribute('data-menu-xmlid'),
                            aria_label: el.getAttribute('aria-label'),
                            role: el.getAttribute('role'),
                            href: el.getAttribute('href'),
                        });
                    });
                    return out;
                }"""
            )
            captured[label] = elements
            print(f"[harvest]   captured {len(elements)} elements")

            screenshot = OUTPUT_DIR / f"screenshot_{label}.png"
            await page.screenshot(path=str(screenshot), full_page=True)

        await browser.close()

    out = OBJECT_REPO_DIR / "harvested_elements.json"
    out.write_text(json.dumps(captured, indent=2, default=str))
    print(f"[harvest] wrote {out}")
    return captured


def main() -> int:
    try:
        asyncio.run(harvest())
    except Exception as exc:  # noqa: BLE001
        print(f"harvest failed: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
