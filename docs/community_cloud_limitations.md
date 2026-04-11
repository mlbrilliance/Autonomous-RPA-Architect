# Community Cloud Limitations — Honest Edition

This doc lists every brick wall I hit during the April 2026 enterprise
build, the evidence for each, and the workaround the Invoice
Processing Factory uses. If you hit one of these on your own work and
think you've found a way around it, please verify live — several of
these look solvable on paper but aren't.

## 1. Serverless robot is Linux, no UI automation

**Symptom:** UI activities like `ui:Click`/`ui:TypeInto`/`ui:OpenBrowser`
silently refuse to load.

**Evidence:** Stack trace from job 661182761:
`UiPath.Executor.Core` resolves at `/mnt/_work/1/s/Studio/Robot/UiPath.Executor.Core` — a Linux path. The `UiPath.UIAutomation.Activities`
package targets `net48` (full .NET Framework), which cannot be loaded
into a .NET 8 / Portable runtime.

**Workaround:** the entire enterprise pipeline is expressed as C#
`HttpClient` calls. Odoo is driven via JSON-RPC, not through a UI.
Main.xaml is a minimal empty `<Sequence />` that invokes
`ProcessInvoiceMain.cs` via `ui:InvokeWorkflowFile`.

## 2. `UiPath.IntelligentOCR.Activities` is Windows-only

**Symptom:** `DigitizeDocument`, `MachineLearningExtractor`,
`PresentValidationStation` etc. cannot be used in a Portable project.
`uipcli pack` errors with "Cannot create unknown type
`{http://schemas.uipath.com/workflow/activities/intelligentocr}DigitizeDocument`".

**Workaround:** Document Understanding is invoked via its REST API
(`DocumentUnderstandingClient.cs`), not via XAML activities. The
client targets the DU Cloud API v2 endpoint structure
(`cloud.uipath.com/{org}/{tenant}/du_/api/framework/projects/{projectId}/…`)
— note this is different from the legacy classic endpoint at
`du.uipath.com/ie/invoices` which I tested exhaustively and
consistently returned 401 with my available headers.

## 3. DU Cloud API v2 requires DU scopes on the External Application

**Symptom:** My external app has scopes `OR.Execution OR.Jobs
OR.Queues OR.Assets OR.Folders OR.Machines OR.Robots OR.Settings` — all
granted at registration. The token endpoint rejects the DU scopes
with `400 Bad Request {"error":"invalid_scope"}` when I try to include
`Du.Digitization.Api Du.Extraction.Api` in the token request.

**Evidence:** Direct POST to `/identity_/connect/token` with
`scope=Du.Extraction.Api` → `{"error":"invalid_scope"}`.

**Workaround:** `DocumentUnderstandingClient.cs` raises
`DuApiScopeMissingException` when its token request fails with that
specific error. `ProcessState.cs` catches it and falls back to
`LocalInvoiceExtractor` which reads the ground truth from
`EmbeddedInvoice` metadata. The pipeline runs end-to-end with
`doc.Source == "local.groundtruth"` logged on every invoice. The
DU code path is present, compiles, and compiles-tested — flipping
`ProcessConfig.UseLiveDuApi = true` activates it the moment the user
updates the external app's granted scopes at
`cloud.uipath.com/{org}/portal_/externalAppsRegistration` and
recreates the app secret.

**To enable live DU today:**
1. Go to `cloud.uipath.com/{org}/portal_/externalAppsRegistration`
2. Edit the existing app (or create a new one)
3. Under "Resources", add a **Document Understanding API** resource
   with scopes `Du.Digitization.Api`, `Du.Extraction.Api`,
   `Du.Classification.Api`, `Du.Validation.Api`
4. Save, regenerate app secret, update `.env`
5. Set `ProcessConfig.UseLiveDuApi = true` in `ProcessInvoiceMain.cs`
6. Also provide a real DU `projectId` — create one at
   `cloud.uipath.com/{org}/{tenant}/du_/` → New Project

## 4. No public Maestro deployment API

**Symptom:** I looked for it extensively. The OData `$metadata` at
`cloud.uipath.com/{org}/{tenant}/orchestrator_/odata/$metadata` has no
Maestro section. Searches of `docs.uipath.com/maestro` return no API
documentation. GLM 5.1 research concurred: "as of early 2025, Maestro
deployment was Studio Web only … I cannot confirm this holds for
2025.10/2026 but no evidence of a public API in my training data."

**Workaround:** The Invoice Processing Factory emits real BPMN 2.0 +
DMN 1.3 design assets at `demo-output/odoo_project_enterprise_maestro/`
with a README explaining how to import them into Studio Web manually.
The XAML pipeline inside the `.nupkg` does NOT bundle a BPMN file
(tried that earlier — Orchestrator silently ignored it).

## 5. No Action Center in Community tier

**Symptom:** Attempts to create `pending.task` records via the
Orchestrator API return `403 — feature requires Enterprise license`.

**Workaround:** Manager approval uses Odoo's `mail.activity` model
instead — `OdooClient.CreateManagerApprovalTaskAsync` invokes the
`account.move.activity_schedule(...)` helper on the target bill with
the `mail.mail_activity_data_todo` xml_id. The activity appears as a
🔔 badge next to the bill in the Odoo list view and as a To-Do on the
bill's chatter.

**Gotcha caught live:** direct `mail.activity.create(...)` with
`res_model="account.move"` fails with `NotNullViolation: res_model_id`.
The correct pattern is `.activity_schedule()` which looks up the
`ir.model` id for you.

## 6. Portable projects disable JIT compilation

**Symptom:** Job faults with `JIT compilation is disabled for
non-Legacy projects. ExpressionToCompile { Code = "..." }` when
Main.xaml contains ANY expression (e.g. a `[variable]` in a
`ui:LogMessage.Message`).

**Workaround:** Main.xaml emits only literal content — no expressions,
no variable references. The real workflow expressions live inside
compiled C# where the compiler has already evaluated them at pack
time.

## 7. No Orchestrator asset → env-var injection in Portable

**Symptom:** I expected Assets defined in Orchestrator to surface as
environment variables inside the robot process. They don't —
`System.Environment.GetEnvironmentVariable("OdooBaseURL")` returns a
stale value from the robot container's own environment (discovered
live when the bot kept calling `localhost:8069` despite my asset
update via the OData API).

**Workaround:** `proof/deploy_odoo.py` re-generates `ProcessInvoiceMain.cs`
on every deploy with the current `ODOO_PUBLIC_URL` from `.env` baked
into a C# string literal (`default_odoo_url` parameter on
`generate_process_invoice_main_cs()`). A fresh deploy always compiles
a fresh DLL with the correct URL.

## 8. No storage bucket scope on the default External App

**Symptom:** `GET /odata/Buckets` → `403 You are not authorized!`

**Workaround:** Skip buckets entirely. Package the 5 real invoice
PDFs as base64 constants inside `EmbeddedInvoices.cs` (14.5 KB total,
compiled into the assembly). The robot has the invoices the moment
the package installs — no external fetch needed.

## 9. Job invoke 2818: "no machine with Unattended runtimes in folder"

**Symptom:** First StartJobs call returned errorCode 2818.

**Root cause:** The Shared folder had no machine template assigned.

**Workaround:** Created a Standard-type machine via
`POST /odata/Machines {Name, Type: "Standard", UnattendedSlots: 1}`,
then assigned it to Shared via
`POST /odata/Folders/UiPath.Server.Configuration.OData.AssignMachines
{"assignments": {"MachineIds": [...], "FolderIds": [...]}}`. The
correct body shape took OData `$metadata` introspection to discover
(the 400 error message "assignMachinesActionParameters must not be
null" was misleading — the outer wrapper key is `assignments`, and
the inner fields are `MachineIds`/`FolderIds` PascalCase).

## 10. Robot 1015: "Robots without credentials cannot run interactive"

**Symptom:** Even with a machine assigned, StartJobs failed with
errorCode 1015 because the Community robot has no Windows user
credentials attached.

**Root cause:** The process was marked `requiresUserInteraction=true`
in `project.json`, which tells the robot it needs a Windows desktop
session.

**Workaround:** `project.json` template now hardcodes
`"requiresUserInteraction": false` and `"projectProfile": 0` (numeric
enum, not `"Development"` — that was another surprise the live pack
caught). With those two changes the serverless Linux robot runs
the process cleanly.

## 11. Studio 25.10 project.json enum strictness

**Symptom:** `uipcli pack` error:
`'net6.0-windows' is invalid for type TargetFramework`.

**Root cause:** Studio 25.10 uses high-level enum string values
(`Windows` / `Legacy` / `Portable` / `Cross-Platform`) for
`targetFramework`, not .NET TFM strings. The old `net6.0-windows`
worked in Studio 24.x and earlier.

Similar: `projectProfile` must be numeric (0/1), not the string
`"Development"` that older docs show.

**Workaround:** Both values hardcoded correctly in the
`_PROJECT_JSON_TEMPLATE` in `src/rpa_architect/assembler/project_json_gen.py`
with comments citing the live evidence.

## 12. `main` field is required in project.json

**Symptom:** Robot error `ArgumentNullException: Value cannot be null
(Parameter 'path2')` inside `RobotRunner.InitWorkflowApplication()`.

**Root cause:** The legacy `main` top-level field in project.json is
still required by the Studio 25.10 workflow loader. Even if
`entryPoints[0].filePath` is set, `main` being absent makes the loader
call `Path.Combine(projectDir, null)` and crash.

**Workaround:** Template always sets `"main": "Main.xaml"`.

---

## Summary: what ships vs what's aspirational

| Capability | Status |
|---|---|
| OAuth → UiPath Cloud with baseline scopes | ✅ live |
| Package upload + release create + queue seed + job invoke | ✅ live |
| C# state machine compilation + execution on serverless robot | ✅ live |
| Odoo JSON-RPC auth + partner lookup/create + bill create w/ lines | ✅ live |
| Multi-currency bill creation with real `currency_id` resolution | ✅ live |
| Manager approval via `mail.activity.activity_schedule` | ✅ live |
| Document Understanding via DU Cloud API v2 | ⚠️ wired + compile-verified; needs scope grant to activate |
| Maestro BPMN deploy via public API | ❌ not available; Studio Web only (design asset ships) |
| Action Center human tasks | ❌ Enterprise tier only (using `mail.activity` as substitute) |
| Windows UI automation (`ui:Click` etc.) | ❌ not possible on serverless Linux robot |
| Document Understanding via XAML (`IntelligentOCR.Activities`) | ❌ Windows-only package; not usable in Portable |
