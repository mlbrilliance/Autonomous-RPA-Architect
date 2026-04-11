---
name: odoo-jsonrpc-patterns
description: JSON-RPC patterns for Odoo 17 (Community + Enterprise) — session auth, `account.move` vendor bill creation with line items, multi-currency resolution, and `mail.activity` manager approvals. Load this when writing C# or Python code that talks to Odoo without the official XML-RPC library, or when debugging `NotNullViolation` / inactive currency errors.
---

# Odoo 17 JSON-RPC Patterns

All of this is code-verified against a real Odoo 17 Community running in
Docker. Reference implementations are in
`src/rpa_architect/codegen/odoo_client_gen.py` (C#) and
`proof/odoo/seed_database.py` (Python).

## Session authentication (cookie-based)

Odoo's `/web/session/authenticate` returns a `session_id` cookie. All
subsequent calls to `/web/dataset/call_kw` reuse that cookie. Do NOT try
XML-RPC or OAuth — Odoo Community 17's user-facing API is cookie JSON-RPC.

```
POST /web/session/authenticate
{
  "jsonrpc": "2.0",
  "params": {"db": "odoo", "login": "admin", "password": "admin"}
}
```

In C# use `HttpClientHandler { CookieContainer = new CookieContainer(), UseCookies = true }`
so the session cookie is automatically attached on follow-up calls.

## `call_kw` request shape

```
POST /web/dataset/call_kw
{
  "jsonrpc": "2.0",
  "method": "call",
  "params": {
    "model": "account.move",
    "method": "create",
    "args": [[{...record_values...}]],
    "kwargs": {}
  }
}
```

The `args` outer list wraps a single list of records. The inner list
contains one record dict per entity to create. Forgetting one layer yields
`TypeError: unsupported operand type(s)`.

## Creating a vendor bill with line items

`account.move` with `move_type: "in_invoice"` is a vendor bill. Line items
go in `invoice_line_ids` using the special ORM **command tuples**:

```json
{
  "move_type": "in_invoice",
  "partner_id": 42,
  "invoice_date": "2026-04-10",
  "ref": "INV-2026-001",
  "currency_id": 3,
  "invoice_line_ids": [
    [0, 0, {"name": "Hex bolts M8", "quantity": 100, "price_unit": 0.45}],
    [0, 0, {"name": "Safety goggles", "quantity": 4, "price_unit": 12.50}]
  ]
}
```

- `[0, 0, {...}]` = "create new record with these values"
- `[1, id, {...}]` = "update existing record id"
- `[2, id]` = "delete record id"
- `[4, id]` = "link existing record id"

After create, the `amount_total` is **computed** — you must `read` it back:

```
{"model": "account.move", "method": "read",
 "args": [[bill_id], ["name", "amount_total", "state"]]}
```

## Multi-currency gotcha — EUR/GBP ship inactive

Odoo 17 Community databases ship with EUR and GBP rows in `res.currency`
but with `active: false`. Passing `currency_id` that resolves to an
inactive currency silently falls back to company currency (usually USD)
without raising.

**Fix:** before creating a bill in a non-default currency, run:

```
{"model": "res.currency", "method": "search_read",
 "args": [[["name", "=", "EUR"]], ["id", "active"]]}

# if active == false:
{"model": "res.currency", "method": "write",
 "args": [[id], {"active": true}]}
```

## Manager approval via `mail.activity` (the correct pattern)

Direct `mail.activity.create(...)` with `res_model: "account.move"` fails:

```
NotNullViolation: null value in column "res_model_id" violates not-null constraint
```

because Odoo 17 stores the model as a foreign key to `ir.model`, not the
string. Use the model-level `activity_schedule` helper which looks up the
`ir.model` id internally:

```json
{
  "model": "account.move",
  "method": "activity_schedule",
  "args": [[bill_id]],
  "kwargs": {
    "act_type_xmlid": "mail.mail_activity_data_todo",
    "summary": "Review high-value invoice",
    "note": "Amount $5,500 exceeds threshold",
    "user_id": 2
  }
}
```

The activity appears as a 🔔 badge on the bill record in the Odoo UI and
as a To-Do on the bill's chatter. This is the Community-tier substitute
for UiPath Action Center (which is Enterprise only — see
`uipath-community-cloud-gotchas` §5).

## Finding or creating vendors idempotently

Pattern: `search_read` by name; if empty, `create`; return the id either way.

```
# Find
{"model": "res.partner", "method": "search_read",
 "args": [[["name", "=", vendor_name], ["supplier_rank", ">", 0]],
          ["id", "name"]],
 "kwargs": {"limit": 1}}

# Create
{"model": "res.partner", "method": "create",
 "args": [[{"name": vendor_name, "supplier_rank": 1,
            "is_company": true}]]}
```

`supplier_rank > 0` is what marks a partner as a vendor — don't rely on
`is_supplier` (removed in Odoo 13+) or `category_id`.

## Duplicate-invoice detection

Use `search_count` on `(ref, partner_id)` composite — cheap, no row fetch:

```
{"model": "account.move", "method": "search_count",
 "args": [[["ref", "=", invoice_number],
           ["partner_id", "=", partner_id],
           ["move_type", "=", "in_invoice"]]]}
```

Non-zero = already processed. This is the core "idempotency key" for RPA
invoice-processing bots.

## Exposing local Odoo to UiPath Community Cloud

The serverless robot needs a public URL. Options tested live:

- **cloudflared tunnel** (recommended): `cloudflared tunnel --url http://localhost:8069`
  → stable for session, no account needed, URL is `https://*.trycloudflare.com`
- **ngrok**: works but free tier rotates URL on restart
- **Direct public IP**: only if the host is on a public IP with port 8069 open

Bake the public URL into the C# bot at pack time (§7 of
`uipath-community-cloud-gotchas` explains why env-var approaches don't work
in Portable).
