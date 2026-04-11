---
description: Pack the enterprise Odoo invoice processing project and deploy it to UiPath Community Cloud (upload package, create/update release, seed queue, invoke job).
argument-hint: [--dry-run]
---

# uipath-deploy

End-to-end live deploy of the Invoice Processing Factory to Community Cloud.

Wraps `proof/deploy_odoo.py` — which handles:
1. `uipcli pack` on the generated project directory
2. OAuth2 token exchange against `cloud.uipath.com/identity_/connect/token`
3. `UploadPackage` (multipart) to the Shared folder
4. `Releases.UpdateByKey` to point the existing release at the new version
5. `QueueDefinitions` ensure + seed with 5 invoice references
6. `StartJobs` against the release + resolved robot IDs
7. Poll until terminal state, print the job key

## When the user runs `/uipath-deploy`

1. Verify prerequisites (don't just assume):
   - `.env` exists with `UIPATH_CLIENT_ID`, `UIPATH_CLIENT_SECRET`, `UIPATH_ORG`, `UIPATH_TENANT_NAME`, `ODOO_PUBLIC_URL`
   - `uipcli` is on PATH (`which uipcli` or `dotnet tool list -g | grep -i uipath`)
   - The Odoo tunnel is reachable: `curl -s -o /dev/null -w "%{http_code}" "$ODOO_PUBLIC_URL/web/login"` should return 200 or 303
2. If any check fails, explain exactly what's missing and stop — don't attempt the deploy.
3. If `$ARGUMENTS` contains `--dry-run`, run `python proof/deploy_odoo.py --dry-run` which packs and validates but doesn't upload.
4. Otherwise run `python proof/deploy_odoo.py` and stream output. On success, print the job key + Orchestrator Jobs page URL so the user can click through.
5. On failure, read the last 40 lines of output and diagnose using the gotchas skill (`uipath-community-cloud-gotchas`) before reporting.

## Common failures + diagnosis

- `errorCode: 2818` → no Unattended machine in folder → see gotcha §9
- `errorCode: 1015` → `requiresUserInteraction: true` → see gotcha §10
- `invalid_scope` on token → trying to request DU scopes not registered → gotcha §3
- `ArgumentNullException path2` → `main` field missing in project.json → gotcha §12
- `401` on `ODOO_PUBLIC_URL` → cloudflared tunnel expired → restart it, update `.env`

## Don't do

- Don't use `--no-verify` or skip pre-commit on any git commits this command produces
- Don't amend a failed deploy — always create a fresh package version (timestamp-suffixed)
- Don't touch production Orchestrator folders — this command targets `Shared` only
