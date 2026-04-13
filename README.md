<div align="center">

# 🤖 Autonomous RPA Architect

### _From Process Design Document to Deployable UiPath Project — Autonomously_

[![Python 3.12+](https://img.shields.io/badge/Python-3.12+-3776AB?style=for-the-badge&logo=python&logoColor=white)](https://python.org)
[![UiPath](https://img.shields.io/badge/UiPath-REFramework-FA4616?style=for-the-badge&logo=uipath&logoColor=white)](https://uipath.com)
[![LangGraph](https://img.shields.io/badge/LangGraph-Multi--Agent-1C3C3C?style=for-the-badge&logo=langgraph&logoColor=white)](https://langchain-ai.github.io/langgraph/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow?style=for-the-badge)](LICENSE)
[![Playwright](https://img.shields.io/badge/Playwright-Harvesting-2EAD33?style=for-the-badge&logo=playwright&logoColor=white)](https://playwright.dev/)
[![Tests](https://img.shields.io/badge/Tests-1119%20Passing-brightgreen?style=for-the-badge&logo=pytest&logoColor=white)](tests/)
[![UiPath Studio](https://img.shields.io/badge/UiPath-Studio%2025.10-FA4616?style=for-the-badge&logo=uipath&logoColor=white)](https://docs.uipath.com)
[![Generators](https://img.shields.io/badge/Generators-96-blue?style=for-the-badge)](src/rpa_architect/generators/)
[![Lint Rules](https://img.shields.io/badge/Lint%20Rules-25-orange?style=for-the-badge)](src/rpa_architect/xaml_lint/)

<br/>

**Coding agents that build automations, not just run them.**
<br/>
Natural language to production-ready UiPath project — then deploy, monitor, diagnose, and fix autonomously.
<br/>
_Author → Deploy → Monitor → Diagnose → Fix — the full lifecycle, in a loop._

<br/>

[Quick Start](#-quick-start) · [Lifecycle Agent](#-autonomous-lifecycle-agent) · [Browser Harvesting](#-live-browser-selector-harvesting) · [Maestro Workflows](#-uipath-maestro-workflow-generation) · [Domain Packs](#-vertical-domain-packs) · [Architecture](#-architecture) · [Configuration](#%EF%B8%8F-configuration)

</div>

---

## What's New in v0.6.0 — Claims Adjudication Factory (Dispatcher + Performer + Reporter)

The v0.5 Invoice Factory was a single-process REFramework state machine. v0.6 is the next tier: **three separately-packaged UiPath processes** coordinating through an Orchestrator queue, targeting medical insurance claims adjudication in SuiteCRM 8. Built to stress the Community Cloud free tier — 1 unattended robot slot, no schedule trigger API, .NET 8 Portable runtime — with a 2-hour SLA target of 50 claims/hour.

<table>
<tr>
<td width="50%">

**Dispatcher + Performer + Reporter pattern** — Three `.nupkg`s (each a standalone Portable project) coordinating via a shared Orchestrator queue (`MedicalClaims`). Dispatcher pulls new-status Cases from SuiteCRM and pushes queue items. Performer reads Queued cases directly from SuiteCRM (BW-19: `StartTransaction` requires robot-session context, external-app tokens get 204), runs the 5-rule adjudication engine, writes verdicts + audit notes back. Reporter aggregates queue history, renders an HTML SLA report. Each process has byte-identical copies of the shared C# sources — enforced by a test — because UiPath Community Cloud's NuGet feed silently strips cross-package references at pack time. **Live-validated: 100 claims adjudicated on Community Cloud in 5 minutes.**

</td>
<td width="50%">

**5-rule medical claims adjudication engine** — `CoverageVerificationRule` (in-memory against pre-fetched Policy), `AmountThresholdRule` (>$10k flag, >$100k deny), `DocumentationCompletenessRule` (counts Notes, denies insufficient docs for E&M procedures), `NetworkProviderRule` (live SuiteCRM lookup, flags out-of-network), `FraudVelocityRule` (≥4 claims same claimant 30d → deny, 2-3 → flag). Rules ordered cheap→expensive so deterministic denies short-circuit before SuiteCRM round-trips. FlagForReview reasons accumulate across rules.

</td>
</tr>
<tr>
<td width="50%">

**SuiteCRM 8 OAuth2 REST adapter** — `SuiteCrmClient.cs` generator emits a complete client with OAuth2 password grant, token caching, **401 refresh-retry (BW-15 mitigation)** for Laravel Passport's aggressive token eviction at ~50 min idle, and seven API methods including the **Notes-as-documents substitute (BW-13)** — SuiteCRM 8's Documents REST endpoint is broken upstream (GitHub Issue #10794, open since 2020, reopened April 2026). The client routes around it by storing claim documents as Notes with `parent_type="Cases"`.

</td>
<td width="50%">

**Verdict-distribution drift detection** — `MetricsStore` schema migrated non-destructively to add `verdicts_by_category` column. `detect_drift()` gains a fourth drift type (`verdict_distribution_shift`) firing when any categorical outcome (auto_approve / flag_for_review / deny) shifts >10% relative to the rolling baseline. Requires baseline count ≥ 5 to avoid first-run false positives. Wired into `lifecycle.diagnosis` so a rule-verdict cluster short-circuits to `business_rule_violation` category with confidence 0.9.

</td>
</tr>
<tr>
<td width="50%">

**9 new brick walls documented** — BW-13 through BW-26, discovered during live deployment to Community Cloud + SuiteCRM 8. Highlights: SuiteCRM Documents REST broken (BW-13, use Notes), StartTransaction needs robot session context (BW-19, Performer reads SuiteCRM directly), all SuiteCRM filters require `[eq]` operator (BW-20), uipcli namespace mismatch for CodedWorkflow (BW-18, Main class in project namespace + `[Workflow]` on method), project.json `main` must point to `.cs` file not `Main.xaml` (BW-22). Every wall documented with live error messages + workaround in `docs/brick_walls/`.

</td>
<td width="50%">

**2-hour SLA stress proof** — `proof/run_sla_claims.py` orchestrates: (1) seed 100 Cases to SuiteCRM via the seed client (95 clean + 5 deterministic faults, one per rule), (2) external cron ticks every 2 min invoking Dispatcher then Performer with BW-14 collision-skip logic, (3) Reporter aggregation + HTML render, (4) drift + diagnosis verification, (5) final self-contained HTML SLA report. Target: 50 claims/hour × 2 hours with ≥95% success rate and p50 latency ≤72s. Fault injection deliberately triggers every rule so drift detector validates live.

</td>
</tr>
</table>

### What's actually running live on Community Cloud

| Capability | v0.5 (Invoice) | v0.6 (Claims) |
|---|---|---|
| Queue-coordinated multi-process pipeline (Dispatcher + Performer + Reporter) | — | ✅ live (100 claims) |
| OAuth2 REST against a second ERP (SuiteCRM 8) with 401-refresh-retry | — | ✅ live |
| 5-rule medical claims engine with cheap→expensive short-circuit + FlagForReview accumulation | — | ✅ live |
| Performer reads Queued cases from SuiteCRM directly (BW-19 pivot from StartTransaction) | — | ✅ live |
| Verdict-distribution drift detection (categorical outcome shift) | — | ✅ offline-tested |
| Byte-identical shared C# sources across 3 projects (enforced by test) | — | ✅ live |
| uipcli 25.10.12 compiles all 3 projects to DLL with real UiPath SDK | — | ✅ live |
| Real `dotnet build` compile verification per process (test gate) | ✅ | ✅ |
| Every C# generator round-trips to compiled .NET 8 DLL | ✅ | ✅ |

Full architecture: `docs/claims_factory_live_evidence.md` (live run evidence + timeline), `docs/brick_walls/19_start_transaction_robot_context.md` (BW-19 root cause), `docs/community_cloud_limitations.md` (§13–§17 for v0.6 walls), `tests/fixtures/pdds/medical_claims.md` (PDD source), `src/rpa_architect/assembler/claims_factory_assembler.py` (multi-process assembler), `proof/deploy_claims.py` (three-package live deploy), `proof/run_sla_claims.py` (SLA stress orchestrator).

---

## What's New in v0.5.0 — Enterprise Invoice Processing Factory

A full end-to-end build targeting **UiPath Community Cloud's Linux serverless robot**, compile-verified and live-deployed against a self-hosted Odoo 17 ERP. Every claim below is backed by runnable scripts in `proof/` and structural tests in `tests/`.

<table>
<tr>
<td width="50%">

**16-file REFramework-as-C#-CodedWorkflow** — The classic Init → GetTransactionData → Process → SetTransactionStatus → End state machine translated into compiled C# (`src/rpa_architect/codegen/reframework_csharp_gen.py`). Runs inside a `[Workflow] CodedWorkflow` class on .NET 8 / Portable so it loads on the Linux serverless robot where `ui:*` activities silently fail. Compile-verified on every test run via real `dotnet build`.

</td>
<td width="50%">

**Real Odoo 17 JSON-RPC adapter** — `OdooClient.cs` handles cookie session auth, idempotent vendor lookup/create, multi-currency `account.move` creation with `invoice_line_ids` ORM command tuples, inactive-currency activation (EUR/GBP ship inactive in Odoo 17), and manager-approval tasks via `mail.activity.activity_schedule` (the Community-tier substitute for Action Center).

</td>
</tr>
<tr>
<td width="50%">

**Document Understanding Cloud API v2 client** — `DocumentUnderstandingClient.cs` calls the DU v2 REST endpoints directly (`cloud.uipath.com/{org}/{tenant}/du_/api/framework/...`) because `UiPath.IntelligentOCR.Activities` is Windows-only and won't load in Portable. Includes a graceful `DuApiScopeMissingException` fallback to `LocalInvoiceExtractor` so the pipeline runs end-to-end even without DU scopes on the external app.

</td>
<td width="50%">

**4-rule BusinessRuleEngine** — `IRule` interface + chain evaluator + 4 real rules: `CurrencyWhitelistRule` (USD/EUR/GBP), `DuplicateInvoiceRule` (`search_count` on Odoo), `VendorKycRule` (`search_read` on `res.partner`), `AmountThresholdRule` (>$2,500 USD normalized). Deterministic ordering, fail-fast on first non-`AutoProcess` verdict, explicit `BusinessException` vs `RpaSystemException` discipline.

</td>
</tr>
<tr>
<td width="50%">

**Honest Community Cloud limitations doc** — `docs/community_cloud_limitations.md` catalogues 12 brick walls hit live during the April 2026 build with stack traces, error codes (2818, 1015, `invalid_scope`, `ArgumentNullException path2`), and the workaround for each. No "it should work" guesses — only what was verified against the live tenant.

</td>
<td width="50%">

**Maestro design assets as siblings** — BPMN 2.0 + DMN 1.3 files emitted next to the `.nupkg` (not bundled inside — Orchestrator silently ignores extras). Manual Studio Web import guide at `docs/maestro_studio_web_import.md`. Because as of 2025.10 / 2026 Maestro has **no public deployment API** — verified across OData `$metadata`, docs.uipath.com, and cross-model research.

</td>
</tr>
<tr>
<td width="50%">

**Real vendor-name agent (`agent_scaffold_gen.py`)** — Deployable UiPath Python SDK scaffold generating a real vendor-name normalizer + invoice classifier: regex-based corporate-suffix stripping across 18 formats, 5 known-alias patterns, 5 category rules, and an optional Anthropic LLM supplement with rule-wins-ties audit discipline. Ships with 25 parameterized pytest tests that execute on the generated code.

</td>
<td width="50%">

**Claude Code skills / commands / subagent / MCP tools** — `.claude/skills/` packs the 3 hardest-earned knowledge sets (Community Cloud gotchas, Odoo JSON-RPC patterns, REFramework-as-CodedWorkflow template) as invocable skills. `/uipath-deploy` and `/uipath-verify-package` slash commands wrap the live deploy + 17-assertion package verification. `uipath-rpa-architect` subagent (Opus) for architecture-level tasks. 3 new MCP tools: `generate_enterprise_reframework`, `verify_package_contents`, `get_community_cloud_gotchas`.

</td>
</tr>
</table>

### What actually runs vs. what's design-time

| Capability | Status on Community Cloud serverless |
|---|---|
| OAuth → package upload → release create → queue seed → job invoke | ✅ live |
| C# state machine compile + execution on serverless Linux robot | ✅ live |
| Odoo JSON-RPC auth + partner create + multi-currency bill create with line items | ✅ live |
| Manager approval via `mail.activity.activity_schedule` | ✅ live |
| Document Understanding via DU Cloud API v2 | ⚠️ wired + compile-verified; needs `Du.*.Api` scopes on external app |
| Maestro BPMN deploy via public API | ❌ no API exists — Studio Web manual import only (design asset ships) |
| Action Center human tasks | ❌ Enterprise tier only — using `mail.activity` as substitute |
| Windows UI automation (`ui:Click`, `ui:TypeInto`) | ❌ serverless robot is Linux — HTTP-only code path |

Full details: `docs/enterprise_architecture.md`, `docs/community_cloud_limitations.md`.

---

## What's New in v0.4.0

<table>
<tr>
<td width="50%">

**Autonomous Lifecycle Agent** — LangGraph state machine that wraps the codegen pipeline in a continuous loop: author from PDD/NL, validate, deploy to Orchestrator, monitor execution, diagnose failures, propose fixes, and redeploy — with human approval gates via Action Center.

</td>
<td width="50%">

**Execution Monitoring & Diagnosis** — Polls Orchestrator for job status, aggregates metrics (success rate, duration, error distribution), then runs LLM-powered root cause analysis with heuristic fallback across 8 failure categories (selector drift, code bug, credential expiry, etc.).

</td>
</tr>
<tr>
<td width="50%">

**Drift Detection** — SQLite-backed metrics store tracks execution trends over time. Statistical drift detection flags success rate declines, duration increases, and new error types with configurable thresholds and severity levels.

</td>
<td width="50%">

**Agent-in-Workflow (Hybrid Pattern)** — Embed AI agent nodes within deterministic Maestro BPMN workflows. Agent tasks handle classification, extraction, generation, and research with guardrails, confidence thresholds, and human fallback.

</td>
</tr>
<tr>
<td width="50%">

**Vertical Domain Packs** — Pre-configured industry templates for Finance (invoice processing, bank reconciliation, loan QA), Healthcare (claims, patient intake), and Insurance (policy issuance, claims adjudication) with compliance requirements and business rule patterns.

</td>
<td width="50%">

**Observability & Testing Gate** — Structured agent reasoning traces with nested spans and JSON export. UiPath test runner as first-class deployment gate. Dashboard data aggregation across metrics, trends, drift alerts, and traces. 4 new MCP tools + 2 new CLI commands.

</td>
</tr>
</table>

---

## What's New in v0.3.0

<table>
<tr>
<td width="50%">

**Studio 2025.10 Compatibility** — Generated projects target UiPath Studio 25.10 with updated NuGet packages (25.10.x), `UIAutomation` rename, `net6.0-windows` target framework, and new `WaitScreenReady` activity.

</td>
<td width="50%">

**Coded Automations API Generators** — 16 new C# generators for UiPath's Coded Automations APIs: `system.GetAsset()`, `system.GetCredential()`, `uiAutomation.Open()`, `screen.Click()`, plus complete `.cs` coded workflow file generation.

</td>
</tr>
<tr>
<td width="50%">

**Object Repository v2** — Hierarchical Application > Version > Screen > Element schema matching UiPath 2025.10. Variable support in descriptors (`{{Config_AppUrl}}`). UI Library project generation.

</td>
<td width="50%">

**UiPath Python SDK Agent Scaffold** — Generate `uipath.json`, `entry-points.json`, `pyproject.toml`, and `main.py` for deploying agents via `uipath pack` / `uipath publish`.

</td>
</tr>
<tr>
<td width="50%">

**Enhanced Validation** — 4 coded workflow lint rules (XL-C001 to XL-C004), deprecated classic activity detection (XL-BP009), selector quality scoring (0-100).

</td>
<td width="50%">

**4 New CLI Commands** — `upgrade`, `lint-coded`, `score-selectors`, `scaffold-agent`. Plus 4 new MCP server tools for IDE integration.

</td>
</tr>
</table>

---

## ✨ Highlights

<table>
<tr>
<td width="50%">

### 🏗️ Full Project Generation
Generate complete UiPath Studio projects from PDDs — project.json, Config.xlsx, REFramework XAML, coded C# workflows, Object Repository, and more.

</td>
<td width="50%">

### 🎭 Maestro + REFramework
Auto-detect whether to generate REFramework bots, Maestro BPMN orchestrations, or hybrid combinations — based on process complexity.

</td>
</tr>
<tr>
<td width="50%">

### 🎯 Live Browser Selector Harvesting
4-tier selector strategy: Playwright-based live browser harvesting from real UIs, Object Repository for known apps, Claude Vision inference from screenshots, and TODO placeholders as fallback.

</td>
<td width="50%">

### 🔄 Self-Healing Code Generation
LangGraph multi-agent pipeline with LLMLOOP feedback — Roslyn compilation errors are fed back to the coder agent for automatic correction (up to 3 iterations).

</td>
</tr>
<tr>
<td width="50%">

### 📚 RAG-Powered
25+ knowledge base documents with UiPath API definitions, coded automation examples, selector patterns, and prompt templates via ChromaDB.

</td>
<td width="50%">

### 🔌 MCP Server
Expose all capabilities as an MCP server for seamless integration with Claude Code, Cursor, and other AI-assisted IDEs.

</td>
</tr>
</table>

---

## 🔄 Autonomous Lifecycle Agent

> **Coding agents at design time, deterministic infrastructure at execution time.** The lifecycle agent wraps the existing codegen pipeline in a continuous build-deploy-monitor-fix loop — the architecture UiPath describes for the future of enterprise automation.

### Lifecycle Graph

```
📝 Natural Language / PDD
 │
 ▼
┌────────┐    ┌──────────┐    ┌────────┐    ┌─────────┐
│ AUTHOR │───►│ VALIDATE │───►│ DEPLOY │───►│ MONITOR │
│        │    │   GATE   │    │        │    │         │
│ PDD →  │    │ Roslyn + │    │ Pack + │    │ Poll    │
│ IR →   │◄──│ XAML Lint │    │ Prov + │    │ Jobs +  │──── Healthy ──► END
│ Code   │    │ + Tests  │    │ Release│    │ Logs    │
└────────┘    └──────────┘    └────────┘    └────┬────┘
     ▲                                          │ Faulted
     │         ┌──────────┐    ┌──────────┐     ▼
     │         │ APPROVAL │◄───│ PROPOSE  │◄── DIAGNOSE
     │         │   GATE   │    │   FIX    │    (LLM + heuristic)
     │         └────┬─────┘    └──────────┘
     │              │ Approved
     └──── APPLY ◄──┘
            FIX
```

### Usage

```bash
# Full lifecycle: generate, validate, deploy, and monitor
rpa-architect lifecycle ./pdd.pdf --deploy --monitor --auto-fix

# Deploy and monitor with human approval for fixes
rpa-architect lifecycle ./pdd.pdf --deploy --monitor --approval

# Check monitoring status of a deployed process
rpa-architect lifecycle-status my_process_key --hours 24

# Dry run (preview what would happen)
rpa-architect lifecycle ./pdd.pdf --deploy --monitor --dry-run
```

### Diagnosis Categories

| Category | Detection Signal | Auto-Fix Strategy |
|----------|-----------------|-------------------|
| `selector_drift` | SelectorNotFoundException, UiElement errors | Re-harvest selectors |
| `code_bug` | InvalidOperation, null reference | Feed into codegen feedback loop |
| `data_schema_change` | Field missing, type mismatch | Update Config.xlsx |
| `system_timeout` | TimeoutException | Retry / escalate |
| `credential_expiry` | Auth failures, login errors | Escalate to human |
| `business_rule_violation` | BusinessRuleException | Update DMN rules / escalate |
| `infrastructure` | Network, IO, connectivity | Retry / escalate |

### Drift Detection

The metrics store tracks execution trends over time and flags:

- **Success rate decline** — Moving average drops below configurable threshold
- **Duration increase** — Execution time exceeds 2x historical baseline
- **New error types** — Error patterns not seen in baseline period
- **Throughput decline** — Items processed per hour drops

### MCP Tools (Lifecycle)

| Tool | Description |
|------|-------------|
| `tool_lifecycle_run` | Full lifecycle from PDD to deployed + monitored |
| `tool_deploy_project` | Deploy a generated project to Orchestrator |
| `tool_get_execution_logs` | Fetch monitoring report for a process |
| `tool_diagnose_failures` | Analyze execution logs and diagnose root causes |

---

## 📦 Vertical Domain Packs

> **Pre-configured industry templates** with compliance requirements, business rule patterns, and process outlines.

| Industry | Templates | Key Compliance |
|----------|-----------|----------------|
| **Finance** | Invoice Processing, Bank Reconciliation, Loan Origination QA | SOX, PCI-DSS, KYC/AML |
| **Healthcare** | Claims Processing, Patient Intake | HIPAA, HL7/FHIR |
| **Insurance** | Policy Issuance, Claims Adjudication | State regulations, NAIC |

Domain packs auto-match based on process description keywords and pre-load relevant knowledge into the RAG context.

---

## 🚀 Quick Start

### 1️⃣ Install

```bash
git clone https://github.com/mlbrilliance/Autonomous-RPA-Architect.git
cd autonomous-rpa-architect
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"

# Optional: install Playwright for live browser selector harvesting
pip install -e ".[harvest]"
playwright install chromium

# Configure environment
cp .env.example .env
# Edit .env with your API keys (ANTHROPIC_API_KEY at minimum)
```

### 2️⃣ Run Tests

```bash
make test          # Run all 811 tests
make test-cov      # Run with coverage report
```

### 3️⃣ Generate a UiPath Project

```bash
# 🔄 Auto-detect mode (REFramework vs Maestro vs Hybrid)
rpa-architect generate ./my-process-pdd.pdf --output ./output

# 🏗️ Force a specific mode
rpa-architect generate ./pdd.pdf -o ./output --mode reframework
rpa-architect generate ./pdd.pdf -o ./output --mode maestro
rpa-architect generate ./pdd.pdf -o ./output --mode hybrid

# 🌐 Generate with live browser selector harvesting
rpa-architect generate ./pdd.pdf -o ./output --harvest-selectors
rpa-architect generate ./pdd.pdf -o ./output --harvest-selectors --harvest-headed

# ✅ Generate with validation and packaging
rpa-architect generate ./pdd.docx -o ./output --validate --package
```

### 4️⃣ Try It Without API Keys

A sample IR fixture is included for instant testing:

```bash
rpa-architect generate-from-ir tests/fixtures/sample_irs/simple_queue_performer.json -o ./demo-output
```

<details>
<summary>📂 <b>View generated project structure</b></summary>

```
demo-output/
├── project.json                    # UiPath project manifest
├── Main.xaml                       # REFramework state machine
├── Data/
│   └── Config.xlsx                 # Settings, Constants, Assets sheets
├── Framework/
│   ├── InitAllSettings.xaml
│   ├── InitAllApplications.xaml
│   ├── GetTransactionData.xaml
│   ├── Process.xaml
│   ├── SetTransactionStatus.xaml
│   ├── EndProcess.xaml
│   ├── CloseAllApplications.xaml
│   └── KillAllProcesses.xaml
├── .objects/                       # Object Repository
│   ├── descriptor.json
│   ├── InvoicePortal.json
│   └── ERPSystem.json
└── .local/
    └── project.local.json
```

</details>

### 5️⃣ More Commands

| Command | Description |
|---------|-------------|
| `rpa-architect parse-pdd ./pdd.pdf -o ./ir.json` | 📄 Parse PDD to IR (inspect/edit before generating) |
| `rpa-architect generate-from-ir ./ir.json -o ./output` | ⚙️ Generate from pre-edited IR |
| `rpa-architect generate-from-ir ./ir.json -o ./output --harvest-selectors` | 🌐 Generate with live browser harvesting |
| `rpa-architect validate ./my-uipath-project/` | ✅ Validate an existing UiPath project |
| `rpa-architect build-knowledge` | 📚 Build/rebuild RAG knowledge index |
| `rpa-architect serve-mcp` | 🔌 Start MCP server for IDE integration |
| `rpa-architect lifecycle ./pdd.pdf --deploy --monitor` | 🔄 Full lifecycle: author, deploy, monitor, fix |
| `rpa-architect lifecycle-status my_process --hours 24` | 📊 Check monitoring status of a deployed process |

---

## 🌐 Live Browser Selector Harvesting

> **Production-ready UiPath selectors from real UIs** — Playwright navigates to actual application URLs found in the PDD, discovers interactive elements via DOM + accessibility tree, and generates stable UiPath selectors automatically.

### How It Works

```
📄 ProcessIR                    🌐 Playwright Browser
 │                               │
 ├─ systems[].url ──────────────►│ 1. Navigate to URL
 ├─ systems[].login_required ───►│ 2. Attempt login (env-var credentials)
 │                               │ 3. Discover interactive elements
 │                               │    ├─ DOM: query_selector_all(inputs, buttons, ...)
 │                               │    └─ A11y: accessibility.snapshot()
 │                               │ 4. Take per-step screenshots
 │                               │
 ├─ steps[].actions ────────────►│ 5. Match UIActions to DOM elements
 │                               │    ├─ Tier 1: Heuristic (Jaccard token overlap)
 │                               │    └─ Tier 2: LLM fallback (unmatched actions)
 │                               │
 │                               │ 6. Convert to UiPath selectors
 │                               │    ├─ id (0.95) > name (0.90) > data-testid (0.90)
 │                               │    ├─ aria-label (0.85) > class (0.70)
 │                               │    └─ innertext (0.60) > positional (0.30)
 │                               ▼
 │                          🎯 Selector Merge
 │                           ├─ Harvested (highest priority)
 │                           ├─ Known app library
 │                           └─ TODO placeholders (fallback)
 ▼
📦 .objects/ (production-ready selectors)
```

### Usage

```bash
# Generate with live browser harvesting (headless)
rpa-architect generate ./pdd.pdf -o ./output --harvest-selectors

# Generate from IR with visible browser (for debugging)
rpa-architect generate-from-ir ./ir.json -o ./output --harvest-selectors --harvest-headed

# Install Playwright (one-time setup)
pip install -e ".[harvest]"
playwright install chromium
```

### Credential Configuration

For systems requiring login, set environment variables per system:

```bash
# Format: HARVEST_CRED_{SYSTEM_NAME}_USER / HARVEST_CRED_{SYSTEM_NAME}_PASS
export HARVEST_CRED_INVOICEPORTAL_USER=admin@company.com
export HARVEST_CRED_INVOICEPORTAL_PASS=secretpass
export HARVEST_CRED_ERPSYSTEM_USER=svc_account
export HARVEST_CRED_ERPSYSTEM_PASS=erp_password
```

System names are uppercased with non-alphanumeric characters replaced by underscores (e.g., `SAP GUI` becomes `SAP_GUI`).

### Fallback Chain

The harvesting system is designed to never block project generation:

| Scenario | Behavior |
|----------|----------|
| Element matched in browser | Production-ready UiPath selector |
| Element not matched | Falls back to TODO placeholder |
| Step navigation fails | Warning logged; step gets placeholders |
| Login fails | Harvests pre-login page only |
| Browser launch fails | Entire system falls back to placeholders |
| Playwright not installed | All placeholders (current default behavior) |

Each system gets its own browser context — one system failure doesn't affect others.

### MCP Tool

The harvest is also available as a standalone MCP tool:

```python
# Harvest selectors for all web systems
tool_harvest_selectors_live(ir_json="...", headless=True)

# Harvest for a specific system only
tool_harvest_selectors_live(ir_json="...", system_name="InvoicePortal")
```

### Settings

| Variable | Default | Description |
|----------|---------|-------------|
| `HARVEST_ENABLED` | `false` | Enable harvesting globally |
| `HARVEST_HEADLESS` | `true` | Run browser in headless mode |
| `HARVEST_TIMEOUT_MS` | `30000` | Navigation timeout (ms) |
| `HARVEST_MAX_ELEMENTS_PER_PAGE` | `200` | Max elements to discover per page |

### Testing the Feature

```bash
# Run all 83 harvest-related tests
pytest tests/test_selectors/ -v

# Run specific test modules
pytest tests/test_selectors/test_uipath_converter.py -v    # 27 tests: selector conversion
pytest tests/test_selectors/test_element_matcher.py -v      # 22 tests: heuristic + LLM matching
pytest tests/test_selectors/test_browser_harvester.py -v    # 16 tests: Playwright orchestration
pytest tests/test_selectors/test_harvest_pipeline.py -v     # 11 tests: pipeline + merge logic
```

### 📁 Harvest Module

```
src/rpa_architect/selectors/
├── browser_harvester.py   # 🌐 Playwright-based element discovery and harvesting
├── element_matcher.py     # 🔍 Two-tier action-to-element matching (heuristic + LLM)
├── uipath_converter.py    # 🎯 HarvestedElement → UiPath XML selector conversion
├── harvest_pipeline.py    # 🔗 Pipeline glue + selector merge logic
├── object_repository.py   # 🗂️ Generate .objects/ directory with descriptor JSON
├── placeholder_gen.py     # 📝 Generate TODO-marked placeholder selectors
├── vision_inference.py    # 👁️ Claude Vision API selector inference
└── known_apps.py          # 📦 Pre-built selector libraries (Salesforce, SAP GUI)
```

---

## 🎭 UiPath Maestro Workflow Generation

> **Full support for UiPath Maestro** — the cloud-native orchestration platform for coordinating RPA bots, AI agents, APIs, and humans in a single workflow.

### What Gets Generated

| Artifact | Format | Description |
|----------|--------|-------------|
| 📋 **Process Workflows** | `.bpmn` | BPMN 2.0 definitions with start/end events, service tasks, user tasks, gateways, and sequence flows |
| 📊 **Decision Tables** | `.dmn` | DMN 1.3 business rules extracted from the PDD, evaluated at runtime |
| 🔗 **Service Bindings** | XML | Each BPMN service task bound to a generated REFramework bot, AI agent, or API workflow |
| 👤 **User Tasks** | BPMN | Human-in-the-loop steps routed to UiPath Action Center for approvals and reviews |
| ⚡ **Expressions** | JavaScript | Data transformations and variable mappings between tasks |

### 🔍 Auto-Detection: REFramework vs Maestro vs Hybrid

The tool analyzes the IR and **automatically selects** the best output mode:

```
                        ┌─────────────────────┐
                        │   Analyze Process    │
                        │     from IR          │
                        └──────────┬──────────┘
                                   │
                    ┌──────────────┼──────────────┐
                    ▼              ▼              ▼
            ┌──────────┐  ┌──────────────┐  ┌─────────┐
            │ Single   │  │ Multi-actor   │  │ Hybrid  │
            │ bot,     │  │ human-in-the- │  │ complex │
            │ queue    │  │ loop, DMN     │  │ both    │
            └────┬─────┘  └──────┬───────┘  └────┬────┘
                 ▼               ▼               ▼
           REFramework       Maestro          Hybrid
          (XAML + C#)     (BPMN + DMN)    (Maestro + REF)
```

| Scenario | Detection Signal | Output |
|----------|-----------------|--------|
| Single-bot transactional processing | Queue-based, single system | **REFramework** |
| Multi-actor orchestration | Multiple actor types, external APIs | **Maestro** |
| Long-running with human approvals | Approval/review steps detected | **Maestro** |
| Processes with business rules | Complex routing/escalation rules | **Maestro + DMN** |
| Complex hybrid orchestration | Mix of above signals | **Maestro** orchestrating **REFramework** bots |

Override with `--mode maestro|reframework|hybrid`.

### 🔀 Hybrid Mode

In hybrid mode, the tool generates **both** Maestro and REFramework artifacts working together:

```
🎭 Maestro BPMN (top-level orchestrator)
 │
 ├─── ⚙️ Service Task ──► "Extract Invoice"    → REFramework bot (generated)
 ├─── 📊 Business Rule ──► "Validate Amount"   → DMN decision table (generated)
 ├─── 👤 User Task ──────► "Manager Approval"  → Action Center app
 ├─── 🌐 Service Task ──► "Post to ERP"        → API workflow (generated)
 └─── 🤖 Service Task ──► "Send Notification"  → Coded agent (generated)
```

### 📁 Maestro Module

```
src/rpa_architect/maestro/
├── maestro_planner.py        # 🔍 Auto-detect mode from IR; plan BPMN structure
├── bpmn_generator.py         # 📋 Generate BPMN 2.0 XML with proper namespaces
├── dmn_generator.py          # 📊 Generate DMN 1.3 decision tables
├── service_task_binder.py    # 🔗 Bind service tasks to RPA/agent/API workflows
├── user_task_gen.py          # 👤 Generate user tasks for Action Center
└── expression_gen.py         # ⚡ JavaScript expression generation
```

---

## 🎯 Intelligent Selector Generation

> **4-tier strategy** for generating UiPath UI selectors — from live browser-harvested production selectors to AI-inferred selectors from screenshots.

### Tier 0: 🌐 Live Browser Harvesting (NEW)

Playwright navigates to actual application URLs, discovers real DOM elements, and generates production-ready selectors. See [Live Browser Selector Harvesting](#-live-browser-selector-harvesting) for full details.

### Tier 1: 🗂️ Object Repository Generation

Generates `.objects/` directory with structured JSON descriptors for each target application:

```json
{
  "schemaVersion": "1.0",
  "name": "InvoicePortal",
  "screens": [
    {
      "name": "LoginPage",
      "elements": [
        {
          "name": "UsernameField",
          "selector": "<html app='chrome.exe' /><webctrl tag='input' id='username' />",
          "action": "type_into"
        }
      ]
    }
  ]
}
```

### Tier 2: 📝 Placeholder Selectors with TODO Markers

For unknown applications, generates well-structured placeholder selectors with clear TODO markers:

```xml
<!-- TODO: Capture actual selector for InvoicePortal.LoginPage.UsernameField -->
<html app='chrome.exe' title='*Invoice*' />
  <webctrl tag='input' aaname='username' />
```

Each placeholder includes the semantic element name, expected action type, and suggested attributes based on the element's role in the process.

### Tier 3: 👁️ Vision-Based Selector Inference

Uses **Claude Vision API** to analyze PDD screenshots and infer selectors:

```
📸 Screenshot Input ──► 🧠 Claude Vision ──► 🎯 Selector Candidates
                                                   │
                                            ┌──────┴──────┐
                                            ▼             ▼
                                      High Confidence  Low Confidence
                                      (auto-applied)   (flagged for
                                                        human review)
```

- Identifies UI elements (buttons, text fields, dropdowns, tables) from screenshots
- Maps elements to process steps in the IR
- Generates candidate selectors with confidence scores
- Flags low-confidence selectors for human review

### 📦 Pre-Built Selector Libraries

Includes selector libraries for common enterprise applications:

| Application | Coverage |
|-------------|----------|
| ☁️ **Salesforce Lightning** | Login, navigation, list views, record forms, related lists, reports |
| 🏭 **SAP GUI** | Login, transaction codes, table controls, tree views, status bar |

> 💡 Add custom libraries in `knowledge/selectors/known_apps/` as JSON files.

### 📁 Selector Module

```
src/rpa_architect/selectors/
├── browser_harvester.py   # 🌐 Playwright-based live browser harvesting
├── element_matcher.py     # 🔍 Two-tier action-to-element matching
├── uipath_converter.py    # 🎯 HarvestedElement → UiPath XML selector
├── harvest_pipeline.py    # 🔗 Pipeline glue + selector merge logic
├── object_repository.py   # 🗂️ Generate .objects/ directory with descriptor JSON
├── placeholder_gen.py     # 📝 Generate TODO-marked placeholder selectors
├── vision_inference.py    # 👁️ Claude Vision API selector inference
└── known_apps.py          # 📦 Pre-built selector libraries (Salesforce, SAP GUI)
```

---

## 🏛️ Architecture

### 5-Stage Codegen Pipeline (wrapped by Lifecycle Agent)

```
📄 PDD (PDF/DOCX)
 │
 ▼
┌─────────┐    ┌─────────┐    ┌─────────────┐    ┌──────────┐    ┌──────────┐
│ 1.PARSE │───►│ 2.PLAN  │───►│ 3.GENERATE  │───►│4.VALIDATE│───►│5.ASSEMBLE│
│         │    │         │    │             │    │          │    │          │
│ PDF     │    │ LLM     │    │ LangGraph   │    │ Roslyn   │    │ project  │
│ DOCX    │    │ decom-  │    │ multi-agent │◄───│ selector │    │ .json    │
│ text    │    │ pose    │    │ Coder +     │    │ structure│    │ Config   │
│ images  │    │ IR →    │    │ Reviewer    │    │          │    │ XAML     │
│         │    │ tasks   │    │             │    │ feedback │    │ .nupkg   │
└─────────┘    └─────────┘    └─────────────┘    │ loop x3  │    └──────────┘
                                                 └──────────┘         │
                                                      🔄              │
                                                                      ▼
                                              ┌──── Lifecycle Agent Loop ────┐
                                              │  Deploy → Monitor → Diagnose │
                                              │  → Fix → Redeploy → Monitor  │
                                              └──────────────────────────────┘
```

### 🧠 Key Design Decisions

| Decision | Rationale |
|----------|-----------|
| **Hybrid REFramework** | XAML state machine shell + coded C# business logic — best of both worlds |
| **RAG over fine-tuning** | 25+ knowledge base docs with API definitions, code examples, and patterns |
| **Roslyn as primary validator** | C# type system catches API hallucinations at compile time |
| **Pydantic IR as single source of truth** | Both XAML and C# generation consume the same IR |
| **4-tier selector strategy** | Live browser harvesting → Object Repository → Vision inference → TODO placeholders |
| **Lifecycle as LangGraph** | Same framework for codegen and lifecycle — checkpointing, resumption, streaming for free |
| **Hybrid = permanent** | Deterministic workflows + agent nodes where ambiguity exists — not transitional, equilibrium |
| **Testing as gate** | Validation is part of the deployment control mechanism, not downstream QA |

---

## 📁 Project Structure

```
src/rpa_architect/
├── 🖥️  cli.py                # Typer CLI (6 commands)
├── ⚙️  config.py              # pydantic-settings configuration
├── 📐 ir/                     # Intermediate Representation (Pydantic v2 models)
├── 📄 parser/                 # PDD ingestion (PDF, DOCX, screenshots, LLM)
├── 🤖 codegen/                # LangGraph multi-agent code generation
│   └── 📚 rag/                # ChromaDB RAG knowledge base
├── 🔄 lifecycle/              # Autonomous lifecycle agent (author→deploy→monitor→fix)
│   ├── agent.py               # LangGraph lifecycle state machine
│   ├── deployer.py            # Package + provision + deploy to Orchestrator
│   ├── monitor.py             # Execution monitoring + metrics collection
│   ├── diagnosis.py           # LLM + heuristic root cause analysis
│   ├── fix_proposer.py        # Category-specific fix generation + application
│   ├── metrics_store.py       # SQLite time-series metrics + drift detection
│   └── drift_detector.py      # Statistical drift detection
├── ✅ validation/             # Roslyn, selector, structure validators + LLMLOOP
├── 🎯 selectors/              # Browser harvesting, Object Repository, vision inference
├── 🧪 testing/                # UiPath [TestCase] generation + test runner gate
├── 📦 assembler/              # Project assembly, packaging, Orchestrator provisioning
├── 🎭 maestro/                # BPMN 2.0 / DMN 1.3 + agent-in-workflow nodes
├── 🏢 domains/                # Vertical domain packs (finance, healthcare, insurance)
├── 📊 observability/          # Agent tracing + dashboard data aggregation
├── ☁️  platform/              # UiPath SDK, LLM Gateway, Action Center integration
├── 🔌 mcp_server/             # MCP server (11 tools via FastMCP)
└── 🔧 utils/                  # LLM client, file utils, structured logging

📄 templates/                  # 18 Jinja2 templates (XAML, C#, BPMN, DMN)
📚 knowledge/                  # 25 RAG docs (API definitions, examples, prompts)
🧪 tests/                      # 811 pytest tests across all modules
```

---

## ⚙️ Configuration

### Environment Variables

Copy `.env.example` to `.env` and set:

| Variable | Required | Default | Description |
|----------|:--------:|---------|-------------|
| `ANTHROPIC_API_KEY` | ✅* | — | Anthropic API key for Claude |
| `OPENAI_API_KEY` | — | — | OpenAI API key (alternative LLM) |
| `LLM_PROVIDER` | — | `anthropic` | `anthropic`, `openai`, `uipath_gateway` |
| `LLM_MODEL` | — | `claude-sonnet-4-20250514` | Model name |
| `UIPATH_URL` | — | `https://cloud.uipath.com` | UiPath Cloud URL |
| `UIPATH_TENANT_ID` | — | — | UiPath tenant ID |
| `UIPATH_CLIENT_ID` | — | — | UiPath OAuth client ID |
| `UIPATH_CLIENT_SECRET` | — | — | UiPath OAuth client secret |
| `HARVEST_ENABLED` | — | `false` | Enable live browser selector harvesting |
| `HARVEST_HEADLESS` | — | `true` | Run harvest browser headlessly |
| `HARVEST_CRED_{SYSTEM}_USER` | — | — | Login username for a system |
| `HARVEST_CRED_{SYSTEM}_PASS` | — | — | Login password for a system |
| `LIFECYCLE_MONITOR_INTERVAL_SECONDS` | — | `300` | Seconds between monitoring polls |
| `LIFECYCLE_MAX_AUTO_FIX_ITERATIONS` | — | `3` | Max automatic fix-redeploy loops |
| `LIFECYCLE_REQUIRE_APPROVAL` | — | `true` | Require human approval for fixes |
| `LIFECYCLE_DEPLOYMENT_FOLDER` | — | `Default` | Default Orchestrator folder |

> \* Not required for `generate-from-ir` with pre-built IR files.

### ☁️ UiPath Platform Integration (Optional)

For cloud deployment as a coded agent:

```bash
pip install ".[uipath]"
uipath auth
uipath init
uipath pack && uipath publish --my-workspace
```

---

## 📐 IR Schema

The **Intermediate Representation** is the core data model. See [`src/rpa_architect/ir/schema.py`](src/rpa_architect/ir/schema.py) for the full Pydantic v2 schema.

| Model | Description |
|-------|-------------|
| `ProcessIR` | 🏠 Root model — process name, type, systems, credentials, transactions, config |
| `Transaction` | 💼 Input/output contracts, ordered steps, business rules |
| `Step` | 🔧 Atomic process step (12 types: `ui_flow`, `api_call`, `decision`, `loop`, etc.) |
| `UIAction` | 🖱️ UI interaction (12 actions: `click`, `type_into`, `get_text`, etc.) |
| `BusinessRule` | 📏 Exception/decision rule (6 outcomes: `business_exception`, `retry`, `route`, etc.) |

---

## 🛠️ Development

```bash
make lint          # 🔍 Lint with ruff
make format        # ✨ Format with ruff
make typecheck     # 🔎 Type check with mypy
make test-cov      # 🧪 Test with coverage
make test          # ✅ Run all 201 tests
```

---

## 🧰 Technology Stack

| Layer | Technology | Purpose |
|-------|:----------:|---------|
| **Language** | ![Python](https://img.shields.io/badge/-Python%203.12+-3776AB?style=flat-square&logo=python&logoColor=white) | Core runtime |
| **CLI** | ![Typer](https://img.shields.io/badge/-Typer-000?style=flat-square) | Command-line interface |
| **Data Models** | ![Pydantic](https://img.shields.io/badge/-Pydantic%20v2-E92063?style=flat-square&logo=pydantic&logoColor=white) | IR schema, validation |
| **LLM Orchestration** | ![LangGraph](https://img.shields.io/badge/-LangGraph-1C3C3C?style=flat-square) | Multi-agent pipeline |
| **LLM Clients** | ![Anthropic](https://img.shields.io/badge/-Anthropic-191919?style=flat-square&logo=anthropic&logoColor=white) ![OpenAI](https://img.shields.io/badge/-OpenAI-412991?style=flat-square&logo=openai&logoColor=white) | Claude, GPT, UiPath Gateway |
| **RAG** | ![ChromaDB](https://img.shields.io/badge/-ChromaDB-FF6F61?style=flat-square) | Vector knowledge base |
| **Doc Parsing** | ![PDF](https://img.shields.io/badge/-pdfplumber-red?style=flat-square) ![DOCX](https://img.shields.io/badge/-python--docx-blue?style=flat-square) | PDD ingestion |
| **Templates** | ![Jinja2](https://img.shields.io/badge/-Jinja2-B41717?style=flat-square&logo=jinja&logoColor=white) | XAML, C#, BPMN, DMN |
| **Excel** | ![openpyxl](https://img.shields.io/badge/-openpyxl-217346?style=flat-square&logo=microsoftexcel&logoColor=white) | Config.xlsx generation |
| **C# Validation** | ![.NET](https://img.shields.io/badge/-Roslyn-512BD4?style=flat-square&logo=dotnet&logoColor=white) | Compilation checking |
| **Browser Harvesting** | ![Playwright](https://img.shields.io/badge/-Playwright-2EAD33?style=flat-square&logo=playwright&logoColor=white) | Live selector harvesting |
| **Metrics** | ![SQLite](https://img.shields.io/badge/-SQLite-003B57?style=flat-square&logo=sqlite&logoColor=white) | Drift detection time-series |
| **Testing** | ![pytest](https://img.shields.io/badge/-pytest-0A9EDC?style=flat-square&logo=pytest&logoColor=white) | 811 tests |
| **Linting** | ![ruff](https://img.shields.io/badge/-ruff-D7FF64?style=flat-square&logo=ruff&logoColor=black) ![mypy](https://img.shields.io/badge/-mypy-1674B1?style=flat-square) | Code quality |

---

<div align="center">

### 📄 License

[MIT](LICENSE) — see [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md) for full attribution of all open-source dependencies.

---

Built with 🤖 by [ML Brilliance](https://github.com/mlbrilliance)

</div>
