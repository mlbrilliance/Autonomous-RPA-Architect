# Enterprise Build Plan — "Invoice Processing Factory"

## Honest baseline — what we actually have now

- ✅ Deploy pipeline to UiPath Community Cloud via OAuth external app
- ✅ Real compiled `.nupkg` via `uipcli 25.10.12 pack` (Portable target)
- ✅ ~12 KB coded workflow running on a UiPath serverless Linux robot
- ✅ HttpClient → Odoo JSON-RPC → real `account.move` records with line items
- ❌ No real Document Understanding (the DU module generates taxonomy + XAML stubs, never actually extracts anything)
- ❌ No REFramework state machine (the XAML stubs were stripped after you called them out)
- ❌ No Maestro integration (BPMN file in a folder is not a deploy)
- ❌ Only 1 vendor bill per run, always the same hardcoded data

## The brick wall — what Community Cloud + Portable cannot do

Before proposing new work, list the hard constraints I've proven against the real cloud:

1. **No Windows UI automation on the serverless robot.** Community tier's free unattended robot is a Linux container (stack trace: `UiPath.Executor.Core` at `/mnt/_work/1/s`). The `UiPath.UIAutomation.Activities` package targets `net48`/Windows and cannot load in the Portable runtime. Anything that needs `ui:Click`/`ui:TypeInto`/`ui:OpenBrowser` **cannot run here**.

2. **No `UiPath.IntelligentOCR.Activities` in Portable.** The activity package that provides `DigitizeDocument`/`MachineLearningExtractor`/`PresentValidationStation` is Windows-only. We cannot invoke DU via XAML activities on Community serverless.

3. **No public Maestro deployment API.** Confirmed via GLM 5.1 research + Tavily + Orchestrator OData `$metadata` introspection — Maestro processes are designed/deployed only via Studio Web. A BPMN file bundled inside a `.nupkg` is silently ignored by the runtime.

4. **No Action Center in Community tier.** Human-in-the-loop tasks via Action Center require Enterprise licensing.

5. **JIT compilation disabled for Portable projects.** Any VB/C# expression inside Main.xaml (e.g. `[someVar]`) explodes at runtime. Main.xaml must contain zero expressions.

6. **No Orchestrator asset → environment variable bridge in Portable.** The serverless robot's env is pre-baked; Orchestrator assets are NOT auto-injected. Config has to be compiled into the assembly or fetched via explicit HTTP.

Any plan that ignores these constraints is fakery. The enterprise build must deliver value **within** them.

## The plan — "Invoice Processing Factory" (IPF)

Delivers a visibly enterprise-grade pipeline **that actually runs end-to-end on the UiPath Community Cloud serverless robot you already have**, via a single compiled C# CodedWorkflow that:

1. Calls the real UiPath public DU endpoint (`du.uipath.com/document/invoices`) with 5 real PDF invoices
2. Parses the real extracted fields (vendor, number, date, amount, line items) with confidence scores
3. Runs each through a real C# rule engine (duplicate detection, amount thresholds, currency whitelist, vendor KYC)
4. Creates 5 fully-populated Vendor Bills in Odoo across 5 different vendors, with real line items and real totals (~$5,500 equivalent across 3 currencies)
5. Writes per-bill metrics back to the Orchestrator queue item's `Output` field
6. Emits a batch summary log the Orchestrator UI will display

Plus, ships (but does NOT deploy) design-time Maestro assets — a real BPMN 2.0 orchestration spec + DMN decision table — with a `docs/maestro_studio_web_import.md` walkthrough so the user can upload them into Studio Web and see the higher-level orchestration layer.

### What "enterprise" means here, concretely

| Dimension | Current demo | Enterprise build |
|---|---|---|
| Invoices processed | 1 (hardcoded) | 5 (real PDFs, 5 vendors, 3 currencies) |
| Extraction | None | Real DU API calls with confidence scores |
| Business rules | None | 4 real rules in a C# rule engine |
| Vendors in Odoo | 1 | 5 (auto-created if missing) |
| Line items per bill | 3 (hardcoded) | 3–6 per bill (from real PDF extraction) |
| Total processed value | $374 | ≈$5,500 across 5 bills, 3 currencies |
| Audit trail | Job state only | Queue item Output, Orchestrator logs, Odoo DB, local JSON metrics file |
| REFramework pattern | None | Explicit Init/GetTransaction/Process/SetStatus/End states in C# |
| Exception handling | None | Business + System exception classes, retries, graceful degrade |
| Configuration | Hardcoded | `ProcessConfig.json` loaded at Init (paths, thresholds, endpoints) |
| Maestro | Fake BPMN file in a folder | Real BPMN 2.0 + DMN design assets + Studio Web import guide |
| Documentation | None | Architecture diagram, runbook, rollback guide, known limitations |

### The C# architecture — one .nupkg, many files, real separation of concerns

```
OdooInvoiceProcessing/
├── Main.xaml                          ← Minimal invoker (unchanged)
├── project.json                       ← Portable target (unchanged)
├── ProcessInvoiceMain.cs              ← Entry point [Workflow] + state machine driver
├── States/
│   ├── InitState.cs                   ← Load config, verify DU + Odoo connectivity
│   ├── GetTransactionDataState.cs     ← Pop next queue item, parse SpecificContent
│   ├── ProcessState.cs                ← DU extract → rules → Odoo create
│   ├── SetTransactionStatusState.cs   ← Write outcome to queue item, log
│   └── EndState.cs                    ← Batch summary, final metrics
├── Services/
│   ├── DocumentUnderstandingClient.cs ← POST to du.uipath.com; parse fields
│   ├── OrchestratorQueueClient.cs     ← Read items, write output, set status
│   ├── OdooClient.cs                  ← Auth, partner lookup/create, bill create w/ lines
│   ├── BusinessRuleEngine.cs          ← IRule chain evaluator
│   └── MetricsCollector.cs            ← Append to metrics.json, log to Orchestrator
├── Rules/
│   ├── IRule.cs                       ← interface + RuleResult
│   ├── DuplicateInvoiceRule.cs        ← search_count(ref + partner_id)
│   ├── AmountThresholdRule.cs         ← > $10,000 → flag for review
│   ├── CurrencyWhitelistRule.cs       ← Only USD/EUR/GBP allowed
│   └── VendorKycRule.cs               ← New vendor requires manual tag
├── Models/
│   ├── InvoiceData.cs                 ← VendorName, Number, Date, Total, LineItems, Confidence
│   ├── ProcessConfig.cs               ← Thresholds, endpoints, paths
│   ├── RuleResult.cs                  ← Pass/Reject/FlagForReview + reason
│   └── BatchMetrics.cs                ← Totals, counts, per-vendor breakdown
└── ProcessConfig.json                 ← Config loaded at Init
```

All of this compiles into **one** `OdooInvoiceProcessing.dll` via `uipcli pack`. The robot loads it, `ProcessInvoiceMain.Execute()` kicks off the state machine, and every state file is a real class with real logic.

### Input — 5 real PDFs

Five invoice PDFs generated at build time with `reportlab` (already in the `dev` extras):

| # | Vendor | Currency | Line items | Total |
|---|---|---|---|---|
| 1 | ACME Industrial Supplies, Inc. | USD | Hex bolts / hydraulic jack / safety goggles | $374.00 |
| 2 | Globex Logistics Ltd. | EUR | Freight Hamburg→Rotterdam / customs | €1,925.00 |
| 3 | Initech Software Services | USD | Hosting / premium support | $525.00 |
| 4 | Umbrella Pharmaceuticals plc | GBP | Lab consumables / cold-chain surcharge | £660.40 |
| 5 | Stark Industries R&D | USD | Prototype machining / testing / docs | $2,850.00 |

Each PDF is produced by `tests/fixtures/invoices/generate_invoices.py` and uploaded to an Orchestrator **Storage Bucket** at the start of each deploy run. Queue items carry the bucket path as `SpecificContent.DocumentPath`.

### Real Document Understanding — via the HTTP API, not XAML activities

UiPath's public DU endpoint accepts a multipart POST containing a PDF and returns structured JSON with confidence scores. Spec (confirmed via the 2025.10 docs):

- POST `https://du.uipath.com/document/invoices/start` with multipart `file=@invoice.pdf` → returns `documentId`
- GET `https://du.uipath.com/document/invoices/result/{documentId}` → poll until `status=Succeeded`
- Response has `extractionResult.ResultsDocument.Fields` — each field has `Value`, `Confidence`, `OcrConfidence`, `References`

`DocumentUnderstandingClient.cs` wraps this with `HttpClient` + polling loop + typed `InvoiceData` output. Confidence threshold (default 0.8) comes from `ProcessConfig.json`. Fields below threshold are flagged for the rule engine's "flag for review" lane.

**Reality check:** each call consumes a small slice of your DU quota. Budget: 5 extractions per deploy run × ~3–5 iterations during dev = ≤25 calls. Should be well within any reasonable free-tier quota.

**Fallback:** if DU returns 403 (quota) or 401 (bad key), the client falls back to a deterministic "offline" extractor that reads the invoice PDFs and scrapes the hardcoded layout the `generate_invoices.py` script writes. Same output shape. The bot still runs end-to-end; metrics clearly log the fallback was used.

### REFramework pattern — in C# state machine, not XAML

REFramework is fundamentally a **pattern**: queue-driven transaction loop with Init/Process/End states, exception handling, retries, config-driven. The Windows-XAML implementation isn't magic — it's a state machine. Implementing the same pattern in C#:

```csharp
public class ProcessInvoiceMain : CodedWorkflow
{
    [Workflow]
    public async Task<BatchMetrics> Execute()
    {
        var ctx = new ProcessContext();
        IState state = new InitState(ctx);
        try
        {
            while (state is not null)
                state = await state.ExecuteAsync();
            return ctx.Metrics;
        }
        catch (BusinessException bex)
        {
            ctx.Metrics.BusinessExceptions++;
            Console.WriteLine($"[BusinessException] {bex.Message}");
            return ctx.Metrics;
        }
        catch (SystemException sex) when (ctx.RetryCount < ctx.Config.MaxRetries)
        {
            ctx.RetryCount++;
            await Task.Delay(TimeSpan.FromSeconds(Math.Pow(2, ctx.RetryCount)));
            return ctx.Metrics;  // Robot framework will re-invoke
        }
    }
}
```

Each state returns the next state (or `null` for terminal). `ProcessState` iterates queue items; `ErrorState` handles retries with exponential backoff. **Same lifecycle as REFramework**: Init → GetTransaction → Process → SetTransactionStatus → End, with business vs system exception separation. Just expressed in C# instead of a StateMachine activity.

### Business rules — real `IRule` engine

Four real rules, each a standalone C# class, composed into a chain:

1. **DuplicateInvoiceRule** — `odoo.search_count([('ref', '=', X), ('partner_id', '=', Y)])`. If >0, return `Result.Reject("duplicate")`.
2. **AmountThresholdRule** — if total > $10,000 (configurable, currency-normalised), return `Result.FlagForReview("manager approval required")`.
3. **CurrencyWhitelistRule** — if currency not in `{USD, EUR, GBP}`, return `Result.Reject("unsupported currency")`.
4. **VendorKycRule** — if partner lookup returns no existing partner, return `Result.FlagForReview("new vendor — KYC needed")` AND still auto-create the partner (tagged `kyc_pending=true` via an `x_kyc_pending` custom field, or stored in the `comment` field for Community tier).

Chain evaluates rules in order, collects results. A single `Reject` stops processing that invoice; any `FlagForReview` triggers the "manager approval" lane (see open question #2 below).

### Maestro — real design assets, honest deploy path

The project will output **real** Maestro artifacts in a sibling `_maestro/` dir (not bundled inside the nupkg — that was fakery):

1. **`Maestro/InvoiceProcessingFlow.bpmn`** — real BPMN 2.0 diagram with:
   - Start event: "New invoice batch arrives"
   - Service task: "Invoke REFramework Process" (binds to our deployed Orchestrator process)
   - Service task: "Document Understanding" (`agent://` implementation marker)
   - Exclusive gateway: "Confidence < threshold?"
   - User task: "Human validation" (Action Center placeholder)
   - Service task: "Auto-process"
   - Business rule task: "Evaluate rules" (binds to the DMN below)
   - Service task: "Create Odoo Bill"
   - Service task: "Send notification email"
   - End event
2. **`Maestro/InvoiceProcessingRules.dmn`** — real DMN 1.3 decision table:
   - Inputs: `Amount`, `Currency`, `IsNewVendor`, `Confidence`
   - Output: `Route` ∈ `{AutoProcess, ManagerApproval, KycReview, Reject}`
   - 8–12 decision rows covering the threshold × currency × new-vendor × confidence matrix
3. **`docs/maestro_studio_web_import.md`** — step-by-step guide:
   - Open Studio Web at `cloud.uipath.com/{org}/studio_/`
   - New → Import BPMN → upload `InvoiceProcessingFlow.bpmn`
   - Link the "Invoke REFramework Process" task to our deployed `OdooInvoiceProcessing` release
   - Import the DMN file
   - Publish → test run
   - Expected screenshots at each step

This is the **honest** Maestro integration: build the design assets, tell the user exactly what to do with them, don't pretend they auto-deploy.

### Odoo side — what the user will actually see

**BEFORE** the run:
- `demo-output/odoo/before_snapshot.png`: Odoo Vendor Bills list with the 3 pre-existing Odoo demo bills only (after wiping the old `DEMO-*` rows from previous iterations)

**RUN** (visible in the video):
- Orchestrator job transitions Pending → Running (with 5 sub-state logs as each queue item is processed) → Successful
- Per-item log lines showing DU confidence, rule results, Odoo bill creation

**AFTER** the run:
- `demo-output/odoo/after_snapshot.png`: Vendor Bills list now showing **8 records** (3 old + 5 new from the bot)
  - 5 new bot-created bills, each clearly identifiable by `DEMO-*` reference
  - 5 different vendors (4 auto-created by the bot during the run)
  - 3 different currencies (USD, EUR, GBP)
  - Total new value ≈$5,500 equivalent
  - Each with 3–6 real line items
- `demo-output/odoo/by_vendor_summary.png` — direct JSON-RPC query to `account.move` grouped by `partner_id`, rendered as a summary table showing per-vendor totals and line item counts

### Demo video — real data, real visible work

Same two-panel layout as the last fixed demo, but with enterprise depth:

**LEFT (30 s)** — Orchestrator timeline polled live from the API:
- 0–3s: "Pending — package 1.0.X uploaded, queue seeded with 5 items, 2 assets ready, machine assigned"
- 3–6s: "Running — robot claimed job, installing nupkg"
- 6–15s: 5 per-item log lines pulled from the job's RobotLogs, e.g.
  - `[INFO] ProcessState: processing queue item 1/5 reference=DEMO-ACME-001`
  - `[INFO] DocumentUnderstandingClient: POST du.uipath.com/document/invoices, 5 fields, avg confidence=0.91`
  - `[INFO] BusinessRuleEngine: 4 rules → AutoProcess`
  - `[INFO] OdooClient: created account.move id=29 amount=374.00 lines=3`
  - (×5 invoices)
- 15–30s: "Successful — BatchMetrics {processed:5, rejected:0, flagged:0, total_value:$5527}"

**RIGHT (30 s)** — Odoo state, three phases:
- 0–10s: "Before" — 3 demo bills only
- 10–20s: "During" — hard cut to 8 bills (5 new highlighted in yellow)
- 20–30s: "After" — 8 bills total, banner: "5 created by UiPath bot · 3 currencies · $5,527 processed"

Produced by `proof/record_demo_video.py` with all frames from real DB queries + real Orchestrator API polls. Same recorder infrastructure, new data source.

## Execution plan — phases + TDD gates

Each phase ends with `pytest -q` green + a deploy-and-run proof on the real Community Cloud. No phase is "done" until the new code actually executes against the real cloud + real Odoo. Use `agent-endurance` iteration loop throughout.

### Phase IE-1 — Real invoice PDFs + Orchestrator storage buckets
- Verify `generate_invoices.py` produces 5 valid PDFs
- Add `tests/test_fixtures/test_invoice_pdfs.py`: assert vendor + currency + total in each PDF
- Add `sdk_client.upload_to_bucket()` live test
- `proof/seed_buckets.py` uploads the 5 PDFs to a new `InvoicePdfs` bucket at deploy time
- Live verification: GET bucket items, count = 5

### Phase IE-2 — `DocumentUnderstandingClient.cs`
- New generator: `src/rpa_architect/codegen/du_client_gen.py`
- POST PDF multipart → documentId → GET result → parse Fields
- Typed `InvoiceData` record
- Offline fallback extractor
- TDD: `test_du_client_gen.py` compiles a stub harness that uses a mocked httpclient
- Live verification: one real call to `du.uipath.com` with `invoice_acme_001.pdf`, assert `VendorName ≈ "ACME Industrial Supplies"` and confidence > 0.8

### Phase IE-3 — Business rule engine
- Generated by `src/rpa_architect/codegen/rules_gen.py`
- `IRule` interface + `RuleResult` + 4 rule implementations + chain evaluator
- TDD: unit-test each rule against mocked Odoo client

### Phase IE-4 — REFramework-pattern C# state machine
- New generator: `src/rpa_architect/codegen/reframework_csharp_gen.py` produces:
  - `Models/*.cs` (InvoiceData, ProcessConfig, RuleResult, BatchMetrics, ProcessContext)
  - `States/*.cs` (Init, GetTransactionData, Process, SetTransactionStatus, End)
  - `Services/*.cs` (OdooClient, OrchestratorQueueClient, DocumentUnderstandingClient, BusinessRuleEngine, MetricsCollector)
  - `ProcessInvoiceMain.cs` as state machine driver
- All compile into a single DLL via `uipcli pack`
- TDD: compilation test expanded to cover every generated `.cs`

### Phase IE-5 — Live deploy + 5-invoice run
- Update `proof/deploy_odoo.py` to upload PDFs, seed queue with 5 real items, invoke
- Poll until Successful; assert in Odoo that 5 new `account.move` records exist
- Assert: `amount_total` sum > $5,000 equivalent
- Assert: 4 new `res.partner` records auto-created
- Live artifact: `demo-output/odoo/enterprise_run_log.json`

### Phase IE-6 — Maestro design assets + deploy guide
- `_maestro/InvoiceProcessingFlow.bpmn` generated from an enriched `plan_maestro` call
- `_maestro/InvoiceProcessingRules.dmn` generated from the rule engine metadata
- `docs/maestro_studio_web_import.md` walkthrough
- TDD: BPMN/DMN valid XML, all expected elements present

### Phase IE-7 — Enterprise demo recording
- Rewrite `proof/record_demo_video.py` to:
  - Poll real Orchestrator logs (5 per-item entries visible in the timeline)
  - Odoo BEFORE/AFTER snapshots with 3 → 8 bills
  - Per-vendor summary pane
  - 45–60 s, 2560×720 stitched
- Output: `demo-output/odoo/enterprise_demo.mp4`

### Phase IE-8 — Docs + honest limitations
- `docs/enterprise_architecture.md` — diagram + explanation
- `docs/community_cloud_limitations.md` — all 6 brick walls + workarounds
- `docs/maestro_studio_web_import.md` — manual Maestro deploy
- `README.md` update — Enterprise edition section

## What I need from you before starting

Four decisions. With your answers I'll enter `agent-endurance` and iterate end-to-end.

1. **Should the bot spend your DU API quota?** ≤25 `du.uipath.com` calls total during dev. If no → offline fallback everywhere, no live DU proof.
2. **`manager approval required` flag — where should it go?** No Action Center in Community tier. Pick one:
   - **(a) Orchestrator Task** (closest substitute, visible in Orchestrator UI)
   - **(b) Odoo activity log on the bill** (visible in Odoo)
   - **(c) Email via SMTP** (needs an SMTP relay address)
3. **Maestro — design-only or attempt Studio Web reverse-engineering?** I recommend design-only (real BPMN/DMN + manual import docs). Reverse-engineering Studio Web's undocumented endpoints is another half-day of fragile work.
4. **Before/After baseline — wipe existing `DEMO-*` bills for a clean "before" snapshot, or leave them?**

## Total estimated effort

| Phase | Effort | Live cloud dependency |
|---|---|---|
| IE-1 PDFs + buckets | 0.5 day | Yes (storage bucket upload) |
| IE-2 DU client | 1 day | Yes (`du.uipath.com`) |
| IE-3 Rule engine | 0.5 day | No (offline) |
| IE-4 State machine | 1 day | No (offline) |
| IE-5 Live 5-invoice deploy | 0.5 day | Yes (job execution) |
| IE-6 Maestro assets | 0.5 day | No (offline) |
| IE-7 Demo recording | 0.5 day | Yes (logs + Odoo) |
| IE-8 Docs | 0.5 day | No |

Total: **≈5 person-days of focused work**. In practice, `agent-endurance` iteration compresses this to 3–5 hours of wall time given the existing pipeline.

## Risks

- **DU API schema drift** — the public endpoint might not match my spec notes. Mitigation: one live test call first, capture the real response shape, codify.
- **Odoo partner auto-creation** — `res.partner/create` might reject with missing fields. Mitigation: live-test against local Odoo first.
- **Cloudflared tunnel stability** — demo needs the tunnel up for the whole run. Mitigation: current deploy re-bakes the tunnel URL into the C# on every run.
- **uipcli multi-file C#** — the compiler might not handle subdirectories cleanly. Mitigation: if subdirs break, flatten to root with prefixed filenames (`States_InitState.cs`, etc.).
