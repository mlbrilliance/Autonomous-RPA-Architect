# UiPath Community Cloud Setup — Required for Phases F–H

This guide walks through the one-time manual setup that the live deployment
phases (F: deploy, G: execute, H: record demo) of the Odoo Invoice
Processing build depend on. None of these steps can be automated for you —
they require interactive sign-in to your UiPath account.

> **Outcome:** A `.env` file at the repo root with the four `UIPATH_*`
> credentials, one `UIPATH_DU_API_KEY`, and one `ODOO_PUBLIC_URL` value.

## 1. Sign up for a UiPath Community Cloud account

1. Visit <https://cloud.uipath.com/portal_/register>.
2. Choose **Community** (free) tier when prompted.
3. After verification, note your **organization name**. The URL bar will show
   `https://cloud.uipath.com/{ORG_NAME}/...` — copy `{ORG_NAME}` into
   `UIPATH_ORG` in `.env`.

## 2. Find your tenant id

1. Sign in at <https://cloud.uipath.com>.
2. Click **Admin** in the top-right, then **Tenants** in the left sidebar.
3. The default tenant is named `DefaultTenant`. Click its name and copy the
   **Tenant ID** (a GUID). Paste into `UIPATH_TENANT_ID`.

> Tip: the tenant id is also visible in the URL when you open
> `Admin → Tenants → DefaultTenant`.

## 3. Register an External Application (OAuth client)

1. Still in **Admin**, navigate to **External Applications** in the left
   sidebar.
2. Click **Add Application**.
3. Choose **Confidential application** (server-to-server, no user UI).
4. Name it `Autonomous RPA Architect` (or anything you like).
5. Under **Resources** → **Orchestrator API access**, grant these scopes
   (Application scopes, NOT user scopes):

   | Scope | Why we need it |
   |---|---|
   | `OR.Execution` | invoke processes via the SDK client |
   | `OR.Jobs` | poll job status, fetch logs |
   | `OR.Queues` | create the `OdooInvoices` queue + add items |
   | `OR.Assets` | store `OdooBaseURL` and `DUApiKey` |
   | `OR.Folders` | resolve the `Shared` folder |
   | `OR.Machines` | needed by package upload |
   | `OR.Robots` | inspect the Unattended robot |
   | `OR.Settings` | required by some upload endpoints |

6. Click **Add**, then **Save**.
7. The portal will display the **App ID** (client id) and **App Secret**
   exactly **once**. Copy both:
   - `UIPATH_CLIENT_ID` ← App ID
   - `UIPATH_CLIENT_SECRET` ← App Secret

## 4. Create a Document Understanding API key

1. In Cloud, switch to the **Document Understanding** service (top-right
   service switcher).
2. Click **API Keys** in the left sidebar.
3. Click **Add API Key** → name it `du-invoice-public` → copy the value to
   `UIPATH_DU_API_KEY`.

> Community tier includes access to the public pre-trained Invoice model at
> `https://du.uipath.com/document/invoices`. No model deployment is
> required.

## 5. Expose your local Odoo to UiPath Cloud

The Unattended robot runs on UiPath's managed Windows VM and needs to reach
your local Odoo via the public internet.

1. Start the local Odoo Docker stack:
   ```bash
   cd proof/odoo
   docker compose up -d
   ```
2. Wait ~30 s for Odoo to initialise. Visit <http://localhost:8069> in a
   browser, create a database (any name; demo data ON; admin password
   `admin`), then run:
   ```bash
   python proof/odoo/seed_database.py
   ```
3. In a separate terminal, expose Odoo via ngrok (or any equivalent
   tunneling service):
   ```bash
   ngrok http 8069
   ```
4. Copy the `https://*.ngrok-free.app` URL into `.env` as
   `ODOO_PUBLIC_URL`. **Keep the ngrok session running for the duration of
   the demo** — its URL changes if you restart it.

## 6. Final `.env`

Create or update `.env` at the repository root with:

```bash
UIPATH_URL=https://cloud.uipath.com
UIPATH_ORG=<your-org>                    # from step 1
UIPATH_TENANT_ID=<your-tenant-guid>      # from step 2
UIPATH_CLIENT_ID=<your-client-id>        # from step 3
UIPATH_CLIENT_SECRET=<your-client-secret># from step 3
UIPATH_FOLDER=Shared
UIPATH_DU_API_KEY=<your-du-key>          # from step 4
ODOO_PUBLIC_URL=https://<random>.ngrok-free.app  # from step 5
HARVEST_CRED_ODOO_USER=admin
HARVEST_CRED_ODOO_PASS=admin
ODOO_BASE_URL=http://localhost:8069
```

## 7. Verify

```bash
source .venv/bin/activate
python -c "
from rpa_architect.platform.sdk_client import UiPathClient
import asyncio, os
async def test():
    c = UiPathClient(
        url=os.environ['UIPATH_URL'],
        tenant_id=os.environ['UIPATH_TENANT_ID'],
        client_id=os.environ['UIPATH_CLIENT_ID'],
        client_secret=os.environ['UIPATH_CLIENT_SECRET'],
        organization=os.environ['UIPATH_ORG'],
    )
    token = await c._ensure_token()
    print('OAuth OK, token length =', len(token))
asyncio.run(test())
"
```

A successful run prints `OAuth OK, token length = ~1500`. If you see
`401 Unauthorized`, re-check the scopes on the External Application and
make sure the secret was copied correctly.

## Common pitfalls

| Symptom | Cause | Fix |
|---|---|---|
| `unauthorized_client` | scopes missing | re-add `OR.Execution`, `OR.Jobs`, etc. |
| `invalid_client` | wrong secret | regenerate the External Application |
| `Folder not found` | wrong `UIPATH_FOLDER` value | use `Shared` (default) |
| ngrok URL keeps rotating | free-tier session expired | restart `ngrok http 8069` and re-set the asset before re-running the bot |
| DU 403 from robot | DU API key not granted to the org | recreate API key under the same org as the robot |
