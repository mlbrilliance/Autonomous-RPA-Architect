# Agentic RPA Development for UiPath

## 1. Goals and Scope

This document captures a deep research and design plan for automating UiPath RPA development end‑to‑end, starting from a Process Design Document (PDD) and generating a ready‑to‑run UiPath solution (REFramework, selectors, activity configurations, and optionally coded automations in C#).

The focus is on:
- UiPath Studio / Studio Web and Orchestrator.
- REFramework‑based transactional automations.
- Web and common desktop apps first, expanding to DU/ML and legacy systems later.
- Leveraging both low‑code (XAML) and coded automations (C#) as targets.

---

## 2. Problem Statement

RPA development in UiPath is bottlenecked by manual canvas work: dragging activities, wiring arguments, configuring selectors, and integrating ML/DOCU components all require repetitive, low‑leverage effort.

Conventional coding now benefits from agentic engineering (LLM‑assisted planning, codegen, refactoring, tests), but RPA workflows remain largely manual because their primary representation is XAML with designer‑driven configuration.

The thesis: given a sufficiently rich PDD and access to the runtime environment, most of this work can be automated by compiling a structured process model into UiPath artifacts and iterating with an agentic loop.

---

## 3. High‑Level Vision

We treat “PDD → bot” as a compilation pipeline:

1. PDD → **Structured Process Model** (an intermediate representation, IR).
2. IR → **UiPath Solution Skeleton** (REFramework project, config, assets).
3. Skeleton → **Concrete Implementations** (XAML workflows and/or C# coded automations, selectors, DU blocks, integration activities).
4. **Runtime Calibration & Validation** (selector harvesting, uncertainty flags, simulation, test generation).

The output is not just a draft; it aims for 70–90% completeness, leaving only ambiguous or environment‑specific edges to a human developer.

---

## 4. Research Tracks Overview

### Track 1 – PDD → Process IR

Questions:
- How to robustly extract a structured process description from real‑world PDDs (often incomplete, inconsistent, and narrative)?
- What IR schema is expressive enough to capture business rules, data, UI steps, and exception flows while remaining compilable?

Work items:
- Design an IR (JSON/DSL) that captures:
  - Global metadata (process name, systems, environments, credentials, SLAs).
  - Transaction model (queue‑based, file‑based, API‑driven, single‑shot).
  - Steps with preconditions, actions, post‑conditions, and exception categories.
  - Data contracts (input/output schemas for transactions, config keys).
- Build LLM‑based extractors that map free‑form PDD text into this IR, with explicit uncertainty annotations (e.g., missing details, ambiguous conditions).
- Evaluate against a corpus of real PDDs and refine the schema until it can represent >90% of common enterprise flows.

Deliverables:
- IR schema specification.
- PDD→IR extraction guidelines and prompt templates.
- Metrics and evaluation harness for extraction quality.

---

### Track 2 – IR → REFramework (Low‑Code Focus)

Questions:
- How to map IR to a standard UiPath REFramework project reliably?
- How much of a REFramework solution can be generated deterministically (dispatcher/performer split, config, queues, assets, workflows)?

Work items:
- Analyze official REFramework templates and variations (2021.10+ features, queue‑centric patterns, settings/config flows). [web:2][web:5][web:11][web:14]
- Define mapping rules from IR to REFramework concepts:
  - When to generate dispatcher vs performer projects.
  - How to populate Config.xlsx (URLs, queue names, assets, timeouts).
  - How to wire Main.xaml, InitAllSettings.xaml, InitAllApplications.xaml, GetTransactionData.xaml, Process.xaml, and End Process.xaml.
- Implement a generator that:
  - Clones a stock REFramework template.
  - Programmatically injects a generated Process.xaml body based on IR steps.
  - Adjusts GetTransactionData based on transaction source (queue, datatable, file, API).
  - Updates project.json and dependencies as needed. [web:6][web:9]

Deliverables:
- Formal mapping spec IR→REFramework.
- Prototype generator that outputs a zipped UiPath project folder from IR.

---

### Track 3 – Selector Automation & “Design Robot”

Selectors are a major bottleneck and require a live environment.

Questions:
- How to automatically derive stable selectors or Object Repository entries for UI steps described in the IR?
- How to incorporate computer vision and anchors when DOM/controls are hostile or dynamic? [web:15]

Work items:
- Implement a “design robot” that runs in a VM with the target apps and:
  - Navigates through the process according to generated navigation steps.
  - Captures UI trees and visual snapshots.
  - Heuristically chooses stable selectors (favoring non‑volatile attributes over dynamic IDs and indexes). [web:15]
  - Stores selectors in a selector repository / Object Repository.
- Integrate selector harvesting into the generation pipeline:
  - First pass: generate navigation and rough activity skeletons without selectors.
  - Second pass: run design robot to populate selectors.
  - Third pass: patch XAML and/or coded workflows with harvested selectors.
- Add uncertainty scoring and human‑in‑the‑loop:
  - Flag low‑confidence elements.
  - Generate a review queue for a developer to confirm or fix.

Deliverables:
- Selector harvesting engine and heuristics doc.
- UI element repository format and mapping to UiPath.

---

### Track 4 – DU/ML Integration

Questions:
- How to treat Document Understanding (DU) and ML models as first‑class patterns in the IR and generator?

Work items:
- Catalog common DU use cases (invoice extraction, receipts, forms) and map them to UiPath DU building blocks (Digitize Document, Classify Document Scope, Data Extraction Scope, validation, training). [web:7][web:13]
- Extend IR with DU primitives:
  - Document types, classifiers, extractors, fields, confidence thresholds, validation rules.
- Implement generation patterns:
  - Create DU sub‑workflows and call them from Process.xaml.
  - Configure ML Skills / endpoints via Config and Orchestrator assets.
  - Generate validation station calls and post‑processing (to queues, Excel, DB).

Deliverables:
- DU pattern catalog and IR extensions.
- DU workflow templates and generator support.

---

### Track 5 – Agentic Engineering Layer (Planning & Validation)

Questions:
- Beyond one‑shot generation, how do we run iterative agent loops to refine the solution?

Work items:
- Design agents for:
  - Plan synthesis: break PDD into sub‑flows and map to IR components.
  - Codegen: emit XAML/C# from IR segments.
  - Critique: run static checks, best practice checks, and style checks.
  - Test generation: derive test cases and sample data from PDD/IR.
- Define feedback signals:
  - Execution logs.
  - Selector failures and retries.
  - DU confidence scores.
  - Human review annotations.
- Implement closed‑loop improvement:
  - Use logs and annotations to update IR, selectors, and implementation.

Deliverables:
- Agent role definitions and orchestration flows.
- MVP of a “regenerate & repair” loop for a subset of flows.

---

## 5. Track 6 – Coded Automation Deep Dive

UiPath now supports coded automations: C#‑based workflows (coded workflows and coded test cases) that live alongside low‑code workflows in Studio. They rely on the `UiPath.CodedWorkflows` package and are available in recent Studio versions (e.g., 2024.10.x). [web:18][web:20][web:23][web:26]

### 5.1 Capabilities and Constraints

Key aspects to document:
- Coded workflows are C# classes generated by Studio that inherit from a base type (e.g., `CodedWorkflow`) and use injected services corresponding to activity packages (UIAutomation, System, Excel, Mail, etc.). [web:20][web:27]
- They can call low‑code workflows (XAML) and be invoked from them, enabling hybrid designs where REFramework remains XAML‑based while inner logic is coded. [web:18][web:20][web:29]
- They support use of external .NET libraries and custom code more naturally than complex Invoke Code blocks. [web:18][web:20][web:21]

Research tasks:
- Enumerate supported project types and constraints (what activities/services exist in coded form, any missing capabilities vs XAML).
- Document patterns for using Orchestrator, queues, assets, and Config from coded workflows.
- Analyze how coded workflows are created, edited, debugged, and versioned in Studio. [web:18][web:20][web:26][web:27]

Deliverables:
- Capability matrix: coded vs low‑code vs hybrid.
- Best‑practices doc for when to choose each.

---

### 5.2 IR as the Single Source of Truth

The same IR designed for low‑code generation can also target coded automations:
- Each transaction type and its steps map naturally to methods and helper classes.
- Global configuration maps to strongly‑typed config objects instead of untyped dictionaries.
- Exception categories map to custom exception types or error‑handling policies.

Design decision:
- Prefer a **hybrid** default:
  - REFramework shell (Main.xaml, Init, GetTransactionData, End) remains XAML, so it integrates with existing tooling and templates. [web:2][web:5][web:11][web:14]
  - Business logic and integration code are generated as C# coded workflows and helper classes.

Alternative modes:
- Pure coded projects for greenfield scenarios.
- XAML‑only projects when customers are not ready for coded automation.

---

## 6. IR Schema Draft

A first‑cut IR might look like this (sketch only):

```json
{
  "process_name": "LoanApplicationProcessing",
  "process_type": "queue_performer",
  "systems": [
    {"name": "CoreBankingWeb", "type": "web", "base_url": "https://bank/app"},
    {"name": "Outlook", "type": "desktop_app"}
  ],
  "transactions": [
    {
      "name": "ProcessLoanApplication",
      "input_contract": {
        "source": "queue",
        "queue_name": "LoanAppsQueue",
        "fields": [
          {"name": "ApplicantId", "type": "string"},
          {"name": "FirstName", "type": "string"},
          {"name": "LastName", "type": "string"}
        ]
      },
      "steps": [
        {
          "id": "open_app",
          "type": "open_application",
          "system": "CoreBankingWeb",
          "parameters": {"start_url": "${config.CoreBankingUrl}"}
        },
        {
          "id": "login",
          "type": "login_sequence",
          "system": "CoreBankingWeb",
          "parameters": {"username_asset": "BankUser", "password_asset": "BankPass"}
        },
        {
          "id": "search_applicant",
          "type": "ui_flow",
          "system": "CoreBankingWeb",
          "actions": [
            {"action": "click", "target": "SearchTab"},
            {"action": "type_into", "target": "ApplicantIdField", "value": "${tx.ApplicantId}"},
            {"action": "click", "target": "SearchButton"}
          ]
        }
      ],
      "business_rules": [
        {
          "id": "reject_missing_data",
          "condition": "tx.FirstName == null || tx.LastName == null",
          "outcome": "business_exception",
          "reason": "Incomplete applicant name"
        }
      ]
    }
  ],
  "config": {
    "CoreBankingUrl": "https://bank/app",
    "Timeouts": {"UiDefault": 30000}
  }
}
```

This IR is intentionally technology‑agnostic; the mapping to UiPath artifacts happens in later stages.

---

## 7. IR → REFramework Mapping (Low‑Code)

Given the IR, the generator performs:

1. **Project creation**
   - Clone a stock REFramework template.
   - Update project.json (name, description, dependencies) based on IR metadata. [web:6][web:9]

2. **Config population**
   - Generate Config.xlsx rows from `config` and `systems` sections.
   - Map queue names and asset names from `input_contract` and parameters.

3. **Workflow wiring**
   - Main.xaml:
     - Use standard REFramework main but set `ProcessName` and log messages based on IR.
   - InitAllSettings.xaml:
     - Load the generated Config.xlsx.
   - InitAllApplications.xaml:
     - For each system needing initialization, generate or call an Init workflow.
   - GetTransactionData.xaml:
     - Implement queue pulling logic when `process_type` is `queue_performer`.
   - Process.xaml:
     - Generate a Sequence or Flowchart implementing `transactions[*].steps`.

4. **Error handling**
   - Map `business_rules` with `outcome: business_exception` to business rule exception throws in Process.xaml.
   - Map system/technical failures to system exception branches.

5. **Assets and Orchestrator artifacts**
   - (Optionally) generate Orchestrator configuration scripts (e.g., using API) for queues and assets described in IR.

---

## 8. IR → CodedWorkflow Mapping (C#)

### 8.1 Coded Workflow Structure

From UiPath documentation, coded workflows are C# classes that are generated and managed by Studio and use a base type from the `UiPath.CodedWorkflows` package. [web:18][web:20][web:23][web:27]

A generated coded workflow for a transaction might conceptually look like:

```csharp
using UiPath.CodedWorkflows;
using UiPath.CodedWorkflows.UiAutomation;

namespace LoanAutomation.Coded
{
    public class ProcessLoanApplication : CodedWorkflow
    {
        private readonly IUiAutomationService ui;
        private readonly IConfigService config;
        private readonly IQueueService queue;

        public ProcessLoanApplication(
            IUiAutomationService ui,
            IConfigService config,
            IQueueService queue)
        {
            this.ui = ui;
            this.config = config;
            this.queue = queue;
        }

        public override void Run()
        {
            var tx = queue.GetCurrentTransaction<LoanApplication>();

            OpenCoreBanking();
            Login();
            SearchApplicant(tx);
            ApplyBusinessRules(tx);
        }

        private void OpenCoreBanking()
        {
            var url = config["CoreBankingUrl"];
            ui.UseBrowser(url, browser =>
            {
                browser.Maximize();
            });
        }

        private void Login() { /* login steps */ }

        private void SearchApplicant(LoanApplication tx) { /* search steps */ }

        private void ApplyBusinessRules(LoanApplication tx) { /* rules */ }
    }
}
```

Notes:
- Names and service interfaces above are illustrative; exact types and usage must follow UiPath’s coded automation APIs. [web:20][web:27]
- The generator’s responsibility is to:
  - Create one or more coded workflows per transaction.
  - Generate strongly‑typed models (`LoanApplication`), helpers, and configuration accessors.

---

### 8.2 Mapping Rules from IR

Given the IR schema, mapping to coded workflows proceeds as follows:

1. **Namespace and project layout**
   - Use IR `process_name` to define the root namespace.
   - Create folders/namespaces for:
     - `Coded` (coded workflows).
     - `Models` (transaction and DTO classes).
     - `Config` (typed config wrappers).

2. **Models from `input_contract`**
   - For each transaction, generate a DTO that mirrors `input_contract.fields`.
   - If a queue is used, ensure the queue item serialization/deserialization matches this DTO.

3. **Config wrapper from `config`**
   - Generate a class that exposes config keys as properties (e.g., `CoreBankingUrl`), internally mapping to UiPath’s Config dictionary or Orchestrator assets.

4. **Workflow classes from `transactions`**
   - For each transaction, generate a coded workflow class with:
     - A `Run()` entry point that orchestrates step methods in order.
     - Private methods for each IR step (`OpenCoreBanking`, `Login`, `SearchApplicant`, etc.).

5. **Step → method mapping**
   - `open_application` → method that calls browser/desktop service with URLs and window settings.
   - `login_sequence` → method that calls UI services, using selectors/OR entries mapped by semantic names.
   - `ui_flow.actions[]` → sequences of `Click`, `TypeInto`, `GetText`, etc., via UI services.
   - `business_rules` → conditional blocks throwing custom exceptions or marking transaction as business exception.

6. **Integration with REFramework**
   - Expose coded workflows as invokable units from Process.xaml, or let REFramework remain in XAML and call coded workflows using the supported invocation mechanisms. [web:18][web:20][web:28][web:29]

---

## 9. Selector & Object Repository Strategy for Coded Automation

For coded workflows, selectors are still required but can be abstracted:

- Prefer storing selectors and UI element definitions in UiPath’s Object Repository, with semantic keys (e.g., `CoreBanking.SearchTab`, `CoreBanking.ApplicantIdField`). [web:20][web:24]
- Generated coded workflows reference these semantic keys, not raw selectors.
- The selector harvesting robot (Track 3) populates or updates Object Repository entries programmatically, where possible, or by invoking Studio APIs.

Research tasks:
- Validate how coded workflows and Object Repository integrate in current Studio versions (APIs, attribute usage).
- Determine whether OR entries can be managed from code or external tools.

Deliverables:
- Selector abstraction pattern for coded automations.

---

## 10. MVP Scope

A pragmatic MVP to prove value:

1. **Scope constraints**
   - Web apps only (Chromium‑based browsers).
   - Queue‑based REFramework performers (dispatcher optional later).
   - Subset of activities: navigation, click, type, get text, Excel basics.

2. **Pipeline**
   - PDD → IR via LLM+schema.
   - IR → REFramework skeleton (XAML) + coded workflow classes for one transaction.
   - Selector harvesting robot for critical screens.
   - Manual review UI in Studio (or external) for low‑confidence selectors and missing mappings.

3. **Success metrics**
   - Percentage of activities/selectors generated without manual edits.
   - Time saved compared to greenfield manual development.
   - Number of bugs/defects attributable to generation.

---

## 11. Open Questions and Risks

- PDD quality: many PDDs are incomplete; how much can the system infer vs escalate as questions?
- UI hostility: some apps have non‑standard controls; how reliable can automated selector generation be?
- Organizational standards: logging, naming, auditing, and security conventions vary; the generator must be configurable per tenant.
- Version drift: UiPath’s coded automation and Autopilot features are evolving; design must accommodate future APIs and capabilities. [web:18][web:19][web:20][web:23]

This document should be iteratively refined as you prototype the IR, generators, and design‑robot components, and as you validate assumptions against real UiPath projects.
