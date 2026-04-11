---
name: uipath-community-cloud-gotchas
description: Brick walls hit when deploying a Portable (.NET 8 / Linux serverless) UiPath project to Community Cloud in 2025-2026. Load this before attempting any Portable deploy, Document Understanding integration, Maestro push, Action Center task, or Orchestrator API call that isn't obviously supported. Saves hours of dead-end debugging.
---

# UiPath Community Cloud Gotchas (Portable / Linux serverless)

Every item below was hit **live** during the April 2026 enterprise build and
is documented with the concrete symptom + workaround. Full evidence lives in
`docs/community_cloud_limitations.md` at the repo root.

## When to read each section

- **Before writing XAML:** §1 (no UI activities), §6 (no expressions in Main.xaml), §11 (project.json enums)
- **Before touching Document Understanding:** §2 (IntelligentOCR is Windows-only), §3 (DU scopes)
- **Before designing a Maestro flow:** §4 (no public deploy API)
- **Before designing human approval:** §5 (no Action Center in Community)
- **Before reading Orchestrator assets at runtime:** §7 (no asset → env-var bridge)
- **Before uploading PDFs via Storage Buckets:** §8 (default external app lacks scope)
- **Before invoking a job:** §9 (need a machine), §10 (requiresUserInteraction must be false)
- **Before loading project.json as a string dict:** §11, §12 (field types changed in 25.10)

## §1 — Serverless robot is Linux, `ui:*` activities silently fail

`UiPath.UIAutomation.Activities` targets `net48` and cannot load into the
.NET 8 Portable runtime. **Workaround:** drive every UI via HTTP/JSON-RPC from
a C# coded workflow. `Main.xaml` should be a minimal `<Sequence />` that
`InvokeWorkflowFile`s the compiled `.cs`.

## §2 — `UiPath.IntelligentOCR.Activities` is Windows-only

`DigitizeDocument`, `MachineLearningExtractor`, `PresentValidationStation`
cannot be used in a Portable project. `uipcli pack` errors with
`Cannot create unknown type {…intelligentocr}DigitizeDocument`.
**Workaround:** call the DU Cloud API v2 REST endpoint directly from C#
(`HttpClient` → `cloud.uipath.com/{org}/{tenant}/du_/api/framework/...`).

## §3 — DU Cloud API v2 needs extra scopes on the external app

Default external apps get `OR.Execution OR.Jobs OR.Queues OR.Assets
OR.Folders OR.Machines OR.Robots OR.Settings`. The DU endpoints reject
tokens without `Du.Digitization.Api Du.Extraction.Api Du.Classification.Api
Du.Validation.Api`. Token endpoint returns
`{"error":"invalid_scope"}` when you try to request them without registering.
**Workaround:** Register them at
`cloud.uipath.com/{org}/portal_/externalAppsRegistration` → Edit app →
Resources → **Document Understanding API** → add scopes, save, regenerate
secret. Code should catch a `DuApiScopeMissingException` and fall back to a
local extractor so the pipeline runs end-to-end regardless.

## §4 — No public Maestro deployment API (as of 2025.10 / 2026)

OData `$metadata` has no Maestro section. No REST docs, no 200 OK on any
guessed endpoint. **Workaround:** ship BPMN 2.0 + DMN 1.3 files as a
**sibling** directory (not bundled inside the `.nupkg` — Orchestrator
silently ignores extra files). Provide a manual Studio Web import guide.

## §5 — No Action Center on Community tier

`POST /odata/Tasks` with a human task returns `403 — Enterprise license
required`. **Workaround:** if targeting an ERP like Odoo, use
`mail.activity.activity_schedule(...)` on the affected record. The activity
shows as a 🔔 badge in the ERP UI. Note: direct `mail.activity.create(...)`
fails on `res_model_id` NotNullViolation — use the helper.

## §6 — Portable disables JIT compilation

Any expression in `Main.xaml` (e.g. `[myVar]`, a `ui:LogMessage.Message`
with a variable) faults the job with `JIT compilation is disabled for
non-Legacy projects`. **Workaround:** `Main.xaml` emits only literals. Real
expressions live inside compiled C#.

## §7 — Orchestrator Assets don't surface as env vars in Portable

`System.Environment.GetEnvironmentVariable("MyAsset")` returns stale
container env, not the asset value. **Workaround:** bake runtime config
(URLs, API keys) directly into C# string literals at pack time. Regenerate
and repack on every deploy if values change.

## §8 — Storage Buckets return `403 You are not authorized!`

Default external app lacks bucket scope. **Workaround:** base64-embed small
binary resources (PDFs, images, certs) as C# constants in the generated
assembly. For 5 × ~3KB invoices that's 14.5 KB total — not a problem.

## §9 — Job invoke errorCode 2818

*"no machine with Unattended runtimes in folder."* **Workaround:** create a
Standard machine via `POST /odata/Machines
{Name, Type: "Standard", UnattendedSlots: 1}` then assign to folder via
`POST /odata/Folders/UiPath.Server.Configuration.OData.AssignMachines
{"assignments": {"MachineIds": [...], "FolderIds": [...]}}`. The outer key
is `assignments`, inner fields are PascalCase `MachineIds` / `FolderIds`.

## §10 — Job invoke errorCode 1015

*"Robots without credentials cannot run interactive."* **Workaround:** set
`"requiresUserInteraction": false` and `"projectProfile": 0` (numeric!) in
`project.json`. With those two flags the Linux serverless robot runs cleanly.

## §11 — Studio 25.10 project.json enum strictness

- `targetFramework` accepts only `Windows` / `Legacy` / `Portable` /
  `Cross-Platform` — **not** `net6.0-windows` or TFM strings
- `projectProfile` must be the numeric enum (`0` or `1`), **not** the
  string `"Development"` that older docs show
- `targetFramework` for Linux serverless = `"Portable"`

## §12 — `main` field required in project.json

Robot error `ArgumentNullException: Value cannot be null (Parameter 'path2')`
inside `RobotRunner.InitWorkflowApplication`. The legacy top-level `main`
field is still required by the 25.10 workflow loader even when `entryPoints`
is set. Always include `"main": "Main.xaml"`.

## Summary table

| Capability | Status on Community Portable |
|---|---|
| UI automation (`ui:Click`) | ❌ Windows only |
| `IntelligentOCR.Activities` XAML | ❌ Windows only |
| DU via REST (C# HttpClient) | ⚠️ Needs DU scopes on external app |
| Maestro BPMN deploy via API | ❌ Studio Web only |
| Action Center tasks | ❌ Enterprise only |
| Storage Buckets | ⚠️ Needs bucket scope |
| Orchestrator Assets at runtime | ⚠️ Bake into code at pack time |
| C# CodedWorkflow + HttpClient | ✅ Works |
| Queue seed + job invoke | ✅ Works |
| Package upload + release create | ✅ Works |
