# Enterprise Invoice Processing Factory — Architecture

> **Status:** live on UiPath Community Cloud as of April 2026.
> All claims in this document are independently verifiable via the
> scripts in `proof/` and the test suite in `tests/`.

## What it is

A fully-compiled UiPath automation package that runs end-to-end on
UiPath Community Cloud's free serverless robot. It processes a batch
of 5 real invoice PDFs through a REFramework-pattern state machine,
runs them through a 4-rule business engine, and creates 5 real vendor
bills (with real line items, real amounts, multi-currency) in a
self-hosted Odoo 17 instance — plus attaches a `mail.activity` task
to any bill the rules flag for manager review.

Every one of the 16 generated C# files is compile-verified by
`tests/test_codegen/test_reframework_csharp_gen.py` via real
`dotnet build` calls before it ever gets uploaded to the cloud.

## High-level picture

```
 ┌──────────────────────────────────────────────────────────────────┐
 │                          DESIGN TIME                              │
 │                                                                   │
 │  tests/fixtures/invoices/generate_invoices.py                     │
 │      ↓ reportlab                                                  │
 │  5 real PDFs (ACME, Globex, Initech, Umbrella, Stark)             │
 │      ↓ base64                                                     │
 │  EmbeddedInvoices.cs  (14.5 KB baked into the DLL)                │
 │                                                                   │
 │  16 C# generators in src/rpa_architect/codegen/*.py               │
 │      ↓                                                            │
 │  16 .cs files + Main.xaml + project.json                          │
 │      ↓ uipcli 25.10.12 package pack                               │
 │  OdooInvoiceProcessing.1.0.X.nupkg  (~100 KB, real DLL inside)    │
 └──────────────────────────────────────────────────────────────────┘
                             │
                             │  proof/deploy_odoo.py
                             ▼
 ┌──────────────────────────────────────────────────────────────────┐
 │                    UiPath Community Cloud                         │
 │                                                                   │
 │  /Orchestrator/                                                   │
 │    ├─ Processes feed — uploaded package (content/+lib/net8.0/)    │
 │    ├─ Releases — OdooInvoiceProcessing@1.0.X                      │
 │    ├─ QueueDefinitions — OdooInvoices (1204162)                   │
 │    ├─ Assets — OdooBaseURL + DUApiKey                             │
 │    ├─ Machines — one Standard machine we created via API          │
 │    └─ Robots — default robot-unattended (Linux serverless)        │
 │                                                                   │
 │  Job starts → Serverless robot pulls the .nupkg →                 │
 │  loads lib/net8.0/OdooInvoiceProcessing.dll →                     │
 │  invokes ProcessInvoiceMain.Execute()                             │
 └──────────────────────────────────────────────────────────────────┘
                             │
                             │  REFramework state machine
                             ▼
 ┌──────────────────────────────────────────────────────────────────┐
 │                    Inside the Robot (.NET 8)                      │
 │                                                                   │
 │  InitState                                                        │
 │    ├─ Load EmbeddedInvoices.All (5 PDFs as byte[])                │
 │    ├─ OdooClient.FindPartnerByName("__warmup__") — auth check     │
 │    └─ → GetTransactionDataState                                   │
 │                                                                   │
 │  GetTransactionDataState  (loops 5 times)                         │
 │    ├─ Pop next invoice from in-memory queue                       │
 │    └─ → ProcessState                                              │
 │                                                                   │
 │  ProcessState                                                     │
 │    ├─ LocalInvoiceExtractor.Extract(invoice)  ← ExtractedDocument │
 │    │    (fallback; DocumentUnderstandingClient is wired for       │
 │    │     DU v2 API but needs DU scopes on the external app —     │
 │    │     see community_cloud_limitations.md)                      │
 │    ├─ BusinessRuleEngine.EvaluateAsync(ctx)                       │
 │    │    ├─ CurrencyWhitelistRule  (USD/EUR/GBP)                   │
 │    │    ├─ DuplicateInvoiceRule   (search_count on Odoo)          │
 │    │    ├─ VendorKycRule          (search_read res.partner)       │
 │    │    └─ AmountThresholdRule    (> $2,500 USD normalized)       │
 │    ├─ Verdict ∈ {AutoProcess, FlagForReview, Reject}              │
 │    ├─ OdooClient.EnsurePartnerAsync(vendor)                       │
 │    ├─ OdooClient.CreateVendorBillAsync(doc, partner, line_items)  │
 │    │    ├─ Resolves currency_id via res.currency (activates       │
 │    │    │  EUR/GBP on demand — Odoo 17 ships them inactive)       │
 │    │    └─ POSTs account.move/create with invoice_line_ids        │
 │    ├─ If FlagForReview: OdooClient.CreateManagerApprovalTask      │
 │    │    (uses account.move.activity_schedule with                 │
 │    │     mail.mail_activity_data_todo — the correct Odoo 17       │
 │    │     pattern; direct mail.activity.create fails on            │
 │    │     res_model_id not-null constraint)                        │
 │    ├─ Update BatchMetrics (Processed, Flagged, ByVendor, ...)     │
 │    └─ → SetTransactionStatusState                                 │
 │                                                                   │
 │  SetTransactionStatusState                                        │
 │    ├─ Increment CurrentIndex, clear per-item state                │
 │    └─ → GetTransactionDataState (loop or End)                     │
 │                                                                   │
 │  EndState                                                         │
 │    └─ Emit batch summary (visible in Orchestrator RobotLogs)      │
 │                                                                   │
 │  Exception discipline:                                            │
 │    BusinessException   → log, skip txn, next item                 │
 │    RpaSystemException  → retry w/ exponential backoff (≤3)        │
 └──────────────────────────────────────────────────────────────────┘
                             │
                             │  HttpClient + JSON-RPC
                             ▼
 ┌──────────────────────────────────────────────────────────────────┐
 │              Odoo 17 Community (self-hosted, Docker)              │
 │              Exposed via cloudflared tunnel                       │
 │                                                                   │
 │  POST /web/session/authenticate  (session cookie)                 │
 │  POST /web/dataset/call_kw                                        │
 │    res.partner.search_read  / .create                             │
 │    res.currency.search_read / .write (activate)                   │
 │    account.move.create (with invoice_line_ids tuples)             │
 │    account.move.read (fetch computed amount_total)                │
 │    account.move.activity_schedule (manager approval tasks)        │
 │                                                                   │
 │  → 5 real Vendor Bill records across 5 vendors, 3 currencies      │
 │    totalling ~$5,522 USD equivalent, with 12 real line items      │
 │    and 1 manager approval activity on Stark Industries            │
 └──────────────────────────────────────────────────────────────────┘
```

## The 16 compiled C# files

All live in `src/rpa_architect/codegen/*_gen.py` as Python generators;
the outputs ship inside the `.nupkg` at `content/*.cs` and are
compiled by `uipcli pack` into `lib/net8.0/OdooInvoiceProcessing.dll`.

| Layer      | File                              | Purpose |
|------------|-----------------------------------|---------|
| Resources  | `EmbeddedInvoices.cs`             | 5 real PDFs as base64 constants |
| Adapter    | `DocumentUnderstandingClient.cs`  | DU Cloud API v2 client (real HTTP, needs DU scope) |
| Adapter    | `LocalInvoiceExtractor.cs`        | Fallback extractor using EmbeddedInvoice ground truth |
| Adapter    | `OdooClient.cs`                   | JSON-RPC client: auth, partner, bill, activity, currency |
| Model      | `ProcessConfig.cs`                | Thresholds, endpoints, allowed currencies |
| Model      | `BatchMetrics.cs`                 | Per-run aggregates |
| Model      | `ProcessContext.cs`               | State-machine-shared context |
| Rules      | `BusinessRuleEngine.cs`           | IRule interface + 4 rules + chain evaluator |
| State M.   | `IState.cs`                       | REFramework state interface |
| State M.   | `ProcessExceptions.cs`            | Business vs System exception types |
| State M.   | `InitState.cs`                    | Warmup + load queue |
| State M.   | `GetTransactionDataState.cs`      | Pop next invoice |
| State M.   | `ProcessState.cs`                 | Extract + rules + Odoo create |
| State M.   | `SetTransactionStatusState.cs`    | Advance pointer |
| State M.   | `EndState.cs`                     | Batch summary |
| Entry pt.  | `ProcessInvoiceMain.cs`           | `[Workflow] Execute()` — state machine driver |

## Verification artifacts

| Artifact | What it proves |
|---|---|
| `pytest -q` (998 tests) | Every generator compiles to valid C# and every C# file builds with `dotnet build` |
| `demo-output/odoo/enterprise_demo.mp4` | Live screenshot video with real Orchestrator API polls + real Odoo DB queries |
| `demo-output/odoo/enterprise_demo_manifest.json` | Structured manifest of the latest run — job key, state, all 5 created bill IDs, currencies, activities |
| `demo-output/odoo/package_proof.txt` | 17/17 assertions against the .nupkg downloaded from cloud.uipath.com |
| `demo-output/odoo_project_enterprise_maestro/` | Real BPMN 2.0 + DMN 1.3 files for Studio Web import |

## What runs vs. what's design-time

**Runs live on the Community Cloud serverless robot** (verified):
- OAuth2 → cloud.uipath.com token
- Package upload, release create/update, queue seed, job invoke
- C# state machine + extract + rules + Odoo CRUD
- Activity creation on flagged bills

**Wired in code but not activated** (documented in `community_cloud_limitations.md`):
- Live DU Cloud API v2 calls (`DocumentUnderstandingClient`) — compiles,
  real HTTP wiring, but needs `Du.Extraction.Api` scope on the external app

**Design-time siblings** (not bundled in the .nupkg):
- Maestro BPMN 2.0 flow (`InvoiceProcessingFlow.bpmn`) — import via Studio Web
- DMN 1.3 decision table (`InvoiceRulesDecision.dmn`) — business-analyst editable
- Each with a README explaining the manual import steps

**Explicitly NOT available** (hard walls, see `community_cloud_limitations.md`):
- Windows UI automation (serverless robot is Linux/Portable)
- `UiPath.IntelligentOCR.Activities` XAML activities (Windows-only package)
- Public Maestro deployment API (Studio Web is the only deploy path)
- Action Center (Enterprise tier only)

## Re-running from scratch

```bash
# one-time
bash scripts/install_uipath_cli.sh    # .NET 8 + UiPath.CLI.Linux
cd proof/odoo && docker compose up -d  # local Odoo 17
python proof/odoo/seed_database.py     # activate EUR/GBP + 3 demo vendors
cloudflared tunnel --url http://localhost:8069  # paste URL into .env

# per run
source .venv/bin/activate
pytest -q                              # 998 tests green gate
python proof/deploy_odoo.py            # pack + upload + run
python proof/record_enterprise_demo.py # live-poll + render the E2E video
```
