## Deep research plan with added coded automation focus

### Scope alignment and assumptions handling
I will treat the following as **unspecified unless you provide them** and keep them explicitly labeled “unspecified” in the final report where relevant: target Studio/Robot version, deployment model (Automation Cloud vs Automation Suite vs Standalone), Orchestrator tenancy/folder model, PDD template format, and whether the solution must run fully offline / on-prem (LLMs, CV).  

### Workstream A: UiPath project anatomy and REFramework compilation target
I will extract the “ground truth” constraints for generating a runnable project:
- REFramework structure, expected workflow decomposition, and configuration conventions.
- Project folder structure, entry point behavior, and what must be present for publish/run.
- `project.json` schema fields that affect generation (entry point, dependencies, runtime options, templates, expression language).
- Dependency management and packaging constraints that influence code generation and reproducibility.

Primary sources: Studio REFramework + `project.json` docs, official REFramework repo/docs, Studio templates docs.

### Workstream B: Coded automations deep dive
I will focus on how coded projects actually behave in tooling, CI, and mixed-mode solutions:
- Coded workflows/test cases/source files: structure, namespaces, entry points, and how they integrate with low-code workflows.
- The `UiPath.CodedWorkflows` model (services container, auto-import behavior, Resolve patterns) and implications for generating code reliably.
- Publishing/runtime constraints specific to coded automations (e.g., supported robot/framework versions; limitations like remote debugging).
- CI/CD and source control pitfalls unique to coded automations (including any required generated/“.local” artifacts and CLI version interactions).

Primary sources: Studio coded automations docs (Introduction, Coded Workflow, Working with coded automations), plus Studio version control docs.

### Workstream C: Programmatic generation strategies for “automation as code”
I will compare and then recommend a generation strategy (or hybrid) across three “codegen backends,” including failure modes and guardrails:
- **Template patching (golden-template strategy)**: cloning a vetted template and patching bounded extension points.
- **WF object-model generation + XAML serialization**: building WF activity trees programmatically and emitting XAML; mapping UiPath activity types and expressions; managing namespaces/references.
- **C# coded automation generation**: emitting C# coded workflows (and optionally invoking them from REFramework XAML), including idempotent formatting and code review friendliness.

Primary sources: entity["company","Microsoft","workflow foundation docs"] WF docs on XAML serialization/imperative authoring, Studio docs on templates and coded automations.

### Workstream D: UI targeting subsystem research
I will treat selector generation as its own subsystem with measurable quality:
- Selector primitives: strict selectors, wildcarding, fuzzy/anchor configuration, and how UiPath expects these to be combined.
- UI element inference architecture options: DOM/UIA extraction, screenshots + CV grounding, and hybrid heuristics.
- Failure handling and “repair loop” design (how the tool detects selector drift, captures evidence, proposes fixes).

Primary sources: official selector docs, fuzzy/advanced descriptor docs, CV scope/docs, and recent GUI grounding research papers/benchmarks.

### Workstream E: Orchestrator integration and operational plumbing
I will research the full set of runtime “contracts” the generated project must satisfy:
- Queues/transactions behavior and constraints (including payload limits and schema implications).
- Assets/credentials retrieval and encryption expectations; credential store integrations.
- Orchestrator APIs and auth patterns for automated provisioning and CI/CD deployment.

Primary sources: Orchestrator docs (queues, assets, API/Swagger/OAuth), activity docs for queue/asset/credential activities.

### Workstream F: Testing, CI/CD, and quality gates designed for generated code
I will design an evaluation framework that can be automated:
- Static quality gates: Workflow Analyzer, policy enforcement hooks, and code-style constraints for coded automation.
- Dynamic tests: generated test cases, functional regression runs, and CI-driven execution using CLI.
- Metrics: selector robustness, execution reliability, maintainability (diff noise), and governance compliance.

Primary sources: Studio testing docs, CI/CD integrations docs, Workflow Analyzer docs.

### Workstream G: LLM pipeline design (bounded, verifiable)
I will design the LLM component as a constrained transformer into IR + code fragments:
- Prompt templates for PDD → IR, IR → activity plan, activity plan → bounded XAML or coded C# fragments.
- Structured output enforcement (JSON schema), determinism controls, and evaluation metrics.
- Fine-tuning versus retrieval + in-context learning decision criteria (what would justify fine-tuning).

Primary sources: UiPath Autopilot/Recorder docs (capabilities and boundaries), plus recent workflow/agent papers and GUI grounding papers.

### Workstream H: Legal, compliance, and cost model
I will compile requirements and risks with concrete mitigations:
- IP/licensing considerations for templates, SDKs, and generated code.
- Privacy implications for screenshots and CV/LLM use; GDPR baseline; include entity["organization","NIST","ai risk management framework"] AI RMF framing for model risk.
- Cost model: licensing (UiPath), infra (CI runners, sandbox machines), LLM/CV costs (cloud vs on-prem), and human effort estimates.

Primary sources: UiPath trust/security + product data usage docs (AI CV / AI Center), GDPR text, NIST AI RMF.

### Assembly of final deliverables
After completing the workstreams, I will produce (as requested in the final report):
- A recommended end-to-end architecture diagram (Mermaid).
- A PDD-section → artifacts/activities mapping table.
- A prioritized roadmap (MVP / v1 / v2) emphasizing coded automation, with effort bands and risks.
- Sample LLM prompts/templates for PDD→activity sequences and activity sequences→XAML/coded workflow snippets, explicitly bounded and verifiable.