"""Seed a local Odoo Community instance for UiPath end-to-end testing.

Uses Odoo's JSON-RPC ``/web/dataset/call_kw`` endpoint to:
  1. Authenticate as the admin user.
  2. Verify the Accounting module is installed.
  3. Create three sample vendors (res.partner with supplier_rank=1).

Idempotent — re-running is safe; existing vendors are detected and skipped.

Requires the database to already exist (create one via the Odoo web UI on
first run).

Env vars (REQUIRED — no defaults, to avoid any hardcoded credentials):
  ODOO_BASE_URL    (e.g. http://localhost:8069)
  ODOO_DB          (database name created via the Odoo web UI)
  ODOO_ADMIN_LOGIN (the login you used when creating the database)
  ODOO_ADMIN_PASS  (the password you used when creating the database)

All four must be set in your environment or in ``proof/odoo/.env``. See
``proof/odoo/.env.example`` for the template.
"""

from __future__ import annotations

import json
import os
import sys
from typing import Any

import httpx


def _require_env(name: str) -> str:
    val = os.environ.get(name)
    if not val:
        raise SystemExit(
            f"error: {name} not set. Copy proof/odoo/.env.example to "
            "proof/odoo/.env, fill in your local values, and source it "
            "before running this script."
        )
    return val


BASE_URL = os.environ.get("ODOO_BASE_URL", "http://localhost:8069")
DB = _require_env("ODOO_DB")
LOGIN = _require_env("ODOO_ADMIN_LOGIN")
PASSWORD = _require_env("ODOO_ADMIN_PASS")

SAMPLE_VENDORS = [
    {
        "name": "ACME Industrial Supplies, Inc.",
        "email": "billing@acme-industrial.example.com",
        "is_company": True,
    },
    {
        "name": "Globex Logistics Ltd.",
        "email": "accounts@globex-logistics.example.com",
        "is_company": True,
    },
    {
        "name": "Initech Software Services",
        "email": "billing@initech.example.com",
        "is_company": True,
    },
]


def ensure_account_module(client: httpx.Client) -> None:
    """Ensure the `account` module is installed so vendor bills work.

    Odoo's base ``res.partner`` has no ``supplier_rank`` until ``account``
    (Invoicing) is installed. We install it before creating any vendors
    so the PDD's account.move flow is exercisable.
    """
    ir_module_ids = call_kw(
        client,
        "ir.module.module",
        "search",
        [[("name", "=", "account"), ("state", "in", ["uninstalled", "to install"])]],
        {"limit": 1},
    )
    if not ir_module_ids:
        print("  ✓ account module already installed")
        return
    print("  + installing account module (this may take 30-60 seconds)...")
    call_kw(client, "ir.module.module", "button_immediate_install", [ir_module_ids])
    print("  + account module installed")


def _rpc_call(client: httpx.Client, endpoint: str, params: dict[str, Any]) -> Any:
    response = client.post(
        f"{BASE_URL}{endpoint}",
        headers={"Content-Type": "application/json"},
        content=json.dumps({"jsonrpc": "2.0", "method": "call", "params": params}),
        timeout=300.0,
    )
    response.raise_for_status()
    payload = response.json()
    if "error" in payload:
        raise RuntimeError(f"Odoo RPC error: {payload['error']}")
    return payload.get("result")


def authenticate(client: httpx.Client) -> int:
    """Return the authenticated user UID."""
    result = _rpc_call(
        client,
        "/web/session/authenticate",
        {"db": DB, "login": LOGIN, "password": PASSWORD},
    )
    if not result or not result.get("uid"):
        raise RuntimeError(
            f"Authentication failed for db={DB} login={LOGIN}. "
            "Make sure the database exists and the password is correct."
        )
    return int(result["uid"])


def call_kw(
    client: httpx.Client,
    model: str,
    method: str,
    args: list[Any],
    kwargs: dict[str, Any] | None = None,
) -> Any:
    return _rpc_call(
        client,
        "/web/dataset/call_kw",
        {
            "model": model,
            "method": method,
            "args": args,
            "kwargs": kwargs or {},
        },
    )


def find_existing_partner(client: httpx.Client, name: str) -> int | None:
    found = call_kw(
        client,
        "res.partner",
        "search",
        [[("name", "=", name)]],
        {"limit": 1},
    )
    return int(found[0]) if found else None


def create_partner(client: httpx.Client, vendor: dict[str, Any]) -> int:
    return int(call_kw(client, "res.partner", "create", [vendor]))


def main() -> int:
    print(f"connecting to Odoo at {BASE_URL} (db={DB})...")
    with httpx.Client() as client:
        try:
            uid = authenticate(client)
        except Exception as exc:
            print(f"  authentication failed: {exc}", file=sys.stderr)
            return 2

        print(f"  authenticated as uid={uid}")

        ensure_account_module(client)

        for vendor in SAMPLE_VENDORS:
            existing = find_existing_partner(client, vendor["name"])
            if existing:
                print(f"  ✓ vendor exists: {vendor['name']} (id={existing})")
                continue
            new_id = create_partner(client, vendor)
            print(f"  + created vendor: {vendor['name']} (id={new_id})")

    print("seed complete.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
