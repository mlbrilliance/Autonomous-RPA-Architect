# Building an LLM-powered UiPath code generator: landscape and architecture

**No tool today can take a process document and produce a deployable UiPath automation.** This gap represents the single largest opportunity in the RPA development tooling space. While UiPath Autopilot, Power Automate Copilot, and Automation Anywhere's AI tools can scaffold basic workflows from natural language, none generates production-ready code with proper error handling, selectors, or REFramework compliance. The technical path to building such a system runs through UiPath's coded automations (.cs format) — standard C# files that are dramatically easier to generate programmatically than XAML — combined with a RAG-augmented LLM, a Roslyn compilation validation loop, and a phased approach that defers the hardest problem (selector generation) while delivering immediate value on business logic, data processing, and orchestration code.

---

## The current AI-assisted RPA landscape has significant gaps

### UiPath Autopilot: scaffolding, not production code

UiPath Autopilot (powered by **Google Gemini 2.5 Flash/Pro**) is the most advanced AI development assistant in the RPA space. It generates workflows from natural language descriptions in both Studio Desktop (2024.10+) and Studio Web, supports both XAML and coded automation output, and generates C#/VB expressions from natural language. UiPath reports a **70%+ acceptance rate** on generated workflow steps.

However, Autopilot's actual capabilities are narrower than the marketing suggests. Community developers report that **selector generation is unreliable** — "Sometimes Autopilot is able to generate a selector based on the given prompt, but most of the time it doesn't work at all." The consensus is to use Autopilot for creating a skeleton and expect fine-tuning at every stage. Critically, **Autopilot cannot generate REFramework-compliant workflows**, the standard template used in enterprise UiPath deployments. It also has a hard limit of **5 Autopilot actions per day** under Flex licensing, making it impractical for iterative generation workflows.

The Autopilot chat in Studio Desktop is more powerful — an agentic system with tools for web search, documentation search, file reading, and (optionally) direct workflow editing. But it remains a developer assistant, not a code generator that can be called programmatically or integrated into a pipeline.

### Power Automate Copilot and competitors

**Microsoft Power Automate Copilot** can generate basic cloud flows from natural language and recently added desktop flow generation (preview), but supports only a **subset of connectors**, explicitly **cannot help fix flow errors**, and cannot edit flows with comments, certain triggers, or older connection formats. It's useful for simple flows, not enterprise automation.

**Automation Anywhere** offers the most direct PDD-to-automation pipeline: its Autopilot can **transform BPMN files or process documentation into ready-to-edit workflows**, with a "generative recorder" claiming 60% greater accuracy and self-healing workflows that reduce execution failures by 60%+. However, this is proprietary to the AA platform.

**Pega GenAI Blueprint** is the most ambitious system, accepting BPMN diagrams, PDFs, screenshots, videos, DDL schemas, and OpenAPI specs to generate complete application blueprints. Over **150,000 blueprints created** since April 2024. But it produces only Pega-specific applications.

**SS&C Blue Prism** focuses on runtime AI agents and governance rather than development-time code generation, and **SAP Build Process Automation's Joule** is powerful but SAP-ecosystem-specific.

### The open-source and research void

**No open-source project exists** that uses LLMs to generate UiPath workflows (XAML or coded). This is the most striking gap in the research. GitHub repositories tagged with UiPath and RPA contain traditional sample projects and utility libraries, not generative tools.

The closest academic work is **FlowMind** (JP Morgan, ICAIF 2023), which achieves 99.5% accuracy generating Python workflow code from natural language by "lecturing" an LLM on available APIs — but it targets Python, not UiPath. **LLM4Workflow** (ASE 2024) generates generic workflow models. The paper "Are LLM Agents the New RPA?" (Průcha et al., 2025) found that traditional RPA outperforms LLM agents in speed and reliability for repetitive tasks, but LLM agents significantly reduce development time. This validates the hybrid approach: use LLMs to generate the automation code, then run it via traditional RPA infrastructure.

---

## UiPath coded automations are the right generation target

### Structure and class hierarchy

Coded automations are standard C# files with a predictable, formulaic structure that LLMs can learn from a handful of examples. Every coded automation follows this pattern:

```csharp
namespace ProjectName
{
    public class AutomationName : CodedWorkflow
    {
        [Workflow]
        public void Execute()
        {
            // Automation logic using service APIs
            Log("Processing started", LogLevel.Info);
        }
    }
}
```

The inheritance chain is `CodedWorkflowBase` → `CodedWorkflow` (partial class) → your automation class. The `CodedWorkflow` class is partial, meaning you can extend it in a separate Code Source File to add shared methods available to all automations — critical for implementing cross-cutting concerns like logging and configuration.

Input/output arguments map directly to method parameters and return values. The `Execute()` method can be async, return values, and accept complex types. Three file types exist: **Coded Workflows** (`[Workflow]` attribute), **Coded Test Cases** (`[TestCase]`), and **Code Source Files** (no attribute, utility code).

### The service-API calling pattern

Activity packages become **services**, and activities become **API methods**. The three core services are:

| Service | Package | Key APIs |
|---------|---------|----------|
| `system` | UiPath.System.Activities | `GetAsset()`, `GetCredential()`, `AddQueueItem()`, `GetQueueItem()` |
| `uiAutomation` | UiPath.UIAutomation.Activities | `Open()`, `Attach()`, `Click()`, `TypeInto()`, `GetText()`, `ExtractData()` |
| `testing` | UiPath.Testing.Activities | `VerifyAreEqual()`, `GenerateTestData()` |

UI automation follows a two-step pattern: open/attach to an application, then interact with elements. Selectors can be specified two ways — via **Object Repository descriptors** (strongly typed: `ObjectRepository.Descriptors.AppName.ScreenName.ElementName`) or via **native selector strings** (`Target.FromSelector("<webctrl tag='BUTTON' name='Submit'/>")`). Options objects control interaction details like click type, mouse button, and interaction mode (hardware events vs. simulate).

### What coded automations cannot do

Several XAML capabilities lack coded equivalents: **State Machines** and **Flowcharts** (must be implemented with C# control flow), **Excel Process Scope** and scoped container activities (developers use ClosedXML instead), **Forms** activities, remote debugging, and some specialized SAP/Citrix activities. Not all activity packages expose coded APIs — the core set (UI Automation, System, Testing) is well-covered, but niche packages may require invoking XAML wrappers.

The critical advantage: **coded and XAML files fully interoperate**. The `workflows` object lets coded automations invoke XAML workflows and vice versa, and mixed projects are fully supported. This means a generated coded automation can call existing XAML REFramework templates.

---

## REFramework requires a hybrid generation strategy

**No official coded REFramework template exists.** The REFramework (Robotic Enterprise Framework) is a XAML State Machine with four states — Init, Get Transaction Data, Process Transaction, End Process — plus configuration files, retry logic, and Orchestrator integration. It's the standard template for enterprise UiPath deployments, and any serious generation tool must support it.

The practical strategy is a **hybrid approach**: use the standard XAML REFramework template as the orchestrator (Main.xaml with the state machine), but generate the business logic as coded workflows invoked from within the framework. Specifically:

- **InitAllApplications.cs**: Open browsers, log into systems — generated from PDD application descriptions
- **GetTransactionData.cs**: Retrieve queue items or data rows — generated from data source specifications
- **ProcessTransaction.cs**: Core business logic — the primary generation target
- **CloseAllApplications.cs**: Cleanup logic

For fully coded REFramework, the pattern translates to a while loop with try/catch, retry counters, and state-like methods — but the XAML template is battle-tested and the hybrid approach avoids reinventing its proven error handling.

---

## Project structure and the CI/CD pipeline

### What constitutes a valid UiPath project

A valid project requires a **`project.json`** manifest (there is no `.uiproj` file) plus workflow files. The critical `project.json` fields for coded automation projects are:

```json
{
  "name": "MyAutomation",
  "main": "Main.xaml",
  "dependencies": {
    "UiPath.System.Activities": "[24.10.6]",
    "UiPath.UIAutomation.Activities": "[24.10.8]",
    "UiPath.CodedWorkflows": "[24.10.x]"
  },
  "targetFramework": "Windows",
  "expressionLanguage": "CSharp",
  "schemaVersion": "4.0",
  "designOptions": { "outputType": "Process", "modernBehavior": true }
}
```

The `UiPath.CodedWorkflows` package is **required** for coded automations. Dependencies use NuGet bracket version notation. The `targetFramework` must be `"Windows"` or `"Portable"` (not `"Legacy"`). The Object Repository lives in a `.objects/` folder with a hierarchy of Application → Version → Screen → Element, storing UI descriptors (supersets of selectors including fuzzy matching, anchors, and image context).

### UiPath CLI for validation and deployment

Two CLI variants exist: **UiPath.CLI.Windows** (builds all project types) and **UiPath.CLI** (cross-platform, only cross-platform projects). Key commands for a generation pipeline:

- **`uipcli package analyze`**: Runs Workflow Analyzer rules against both XAML and CS files
- **`uipcli package pack`**: Builds the project into a `.nupkg` package
- **`uipcli package deploy`**: Uploads to Orchestrator with OAuth/client credentials

A newer open-source CLI at `github.com/UiPath/uipathcli` provides `uipath studio package pack`, `publish`, and `analyze` commands with OAuth and PAT authentication. The Orchestrator REST API (OData v4.0) enables programmatic deployment via `UploadPackage`, `CreateRelease`, and `StartJobs` endpoints.

**Critical limitation**: the CLI does not perform full compilation validation of coded automations — it only applies Workflow Analyzer rules. True compilation validation requires a separate Roslyn/MSBuild step against UiPath NuGet packages.

---

## Selector generation is the hardest unsolved problem

Selectors are XML-fragment strings identifying UI elements: `<html app='chrome.exe'/><webctrl tag='INPUT' id='email'/>`. An LLM **cannot generate valid selectors from natural language alone** because selectors depend on the actual DOM/UI structure of the target application. This is the single biggest technical challenge.

Four mitigation strategies exist, in order of practicality:

**Pre-built selector libraries via Object Repository.** For known target applications (SAP, Salesforce, ServiceNow, internal systems), maintain a curated Object Repository that the LLM references through RAG. Generated code uses `ObjectRepository.Descriptors.AppName.Screen.Element` — strongly typed and validated at compile time. This works for the **80% of enterprise automations** that target a finite set of applications.

**Placeholder generation with human-in-the-loop.** For unknown applications, generate structurally valid code with clearly marked placeholder selectors: `Target.FromSelector("<webctrl id='TODO:login_button' tag='BUTTON'/>")`. A developer fills in actual selectors using UI Explorer or the recorder. This is realistic — even UiPath Autopilot requires manual selector recapture.

**Screenshot-based inference using vision models.** Emerging approaches (AskUI, Anthropic Computer Use) use vision models to identify UI elements from screenshots. UiPath's own Computer Vision uses Vision Transformer architecture (v24.10) for element detection without traditional selectors. Generated code could target the `ComputerVision` API as a fallback.

**Application metadata ingestion.** For web applications, accessibility trees, HTML snapshots, or Selenium page objects could provide enough structural information for selector inference. This requires application-specific tooling but is feasible for well-instrumented targets.

---

## Architecture for a general-purpose generation tool

### Why RAG beats fine-tuning for this problem

Research on LLM code generation for specialized frameworks shows that **API hallucination is the dominant failure mode**, accounting for 20%+ of errors. UiPath coded automation APIs are definitively low-frequency in LLM training corpora (introduced ~2023, niche platform), making hallucination near-certain without mitigation.

**RAG is the primary approach** because: UiPath APIs evolve across versions and RAG can point to current docs; the API surface is finite and fits within modern context windows (**~30K tokens minimum**, ~60-80K optimal for comprehensive coverage); fine-tuning requires labeled input-output pairs that don't exist in sufficient quantity; and RAG preserves the base model's general C# coding ability.

A lightweight **fine-tune (LoRA)** may supplement RAG to teach structural patterns — the `CodedWorkflow` class hierarchy, `[Workflow]` attribute usage, `service.API()` calling convention, and selector string formatting. Together.ai's research showed RAG fine-tuning on Mistral 7B matched GPT-4o performance for specific codebases.

Simon Willison's practical insight applies directly: "If an LLM doesn't know a particular library you can often fix this by dumping in a few dozen lines of example code." Providing **20-50 working coded automation examples** in context dramatically improves output quality.

### The compilation-validated generation loop

The proven architecture combines multi-agent planning with **compiler-in-the-loop validation**, based on the LLMLOOP framework (ICSME 2025) which improved pass rates from 76% to **90%+** with iterative compilation feedback:

```
[Process Document / Natural Language]
        ↓
[Planner Agent] → Decompose into automation steps,
                  identify required services, applications, data sources
        ↓
[RAG Retrieval] → Fetch relevant API docs, type definitions,
                  code examples, Object Repository descriptors
        ↓
[Code Generator] → Produce C# coded automation using
                   Claude/GPT-4 with RAG context
        ↓
[Roslyn Compilation] → Validate against UiPath NuGet packages
    ↓ errors? → Feed back to Code Generator (up to 3 iterations)
        ↓
[Structural Validator] → Check CodedWorkflow inheritance,
                         [Workflow] attribute, selector syntax
    ↓ issues? → Feed back to Code Generator
        ↓
[project.json Generator] → Create manifest with correct
                           dependencies and configuration
        ↓
[uipcli pack] → Package into .nupkg
        ↓
[Output] → Valid UiPath project ready for deployment
```

The compilation step is critical because C#'s type system catches most API hallucinations — incorrect method names, wrong parameter types, missing namespaces all produce compiler errors that the LLM can interpret and fix. Research on static analysis feedback loops shows security issues drop from **40% to 13%** and reliability warnings from **50% to 11%** within 10 iterations.

### The RAG knowledge base

The context store must contain, at minimum:

- **Type definitions** for `IUIAutomationService`, `ISystemService`, `ITestingService` — extractable via `Go to Definition` (F12) in UiPath Studio or from NuGet package decompilation
- **Complete method signatures** for all service APIs with overloads (both `IElementDescriptor` and `TargetAnchorableModel` variants)
- **20-50 working examples** covering common patterns: web automation, Excel processing, queue operations, API calls, error handling, credential management
- **Selector syntax reference** with examples of `<html>`, `<webctrl>`, `<wnd>`, `<ctrl>`, `<sap>` tags and their attributes
- **Project.json templates** for different project types
- **REFramework integration patterns** showing how coded workflows plug into the XAML state machine

UiPath's official GitHub repository (`github.com/UiPath/codedautomations-samples`) provides working examples including cross-XAML interoperability, browser testing, and Excel demos. The UiPath documentation at `docs.uipath.com` covers API contracts in the `UiPath.UIAutomationNext.API.Contracts` namespace.

### Three-phase build plan

**Phase 1 — Non-UI automation generation (3-4 months).** Target the subset of automations that don't require selectors: Orchestrator queue processing, API integrations, data transformation, Excel manipulation (via ClosedXML), email processing, and database operations. These use `system` service APIs and standard C# libraries. Build the RAG pipeline, compilation loop, and project.json generator. Expected accuracy: **85-90%** compilable code after validation loop, based on LLMLOOP benchmarks for typed languages.

**Phase 2 — UI automation with known applications (2-3 months).** Add Object Repository integration for target applications. Build selector libraries for common enterprise apps (SAP GUI, Salesforce, ServiceNow web, common banking portals). Generate code using `ObjectRepository.Descriptors` references. Add screenshot-based selector suggestion using vision models for gap-filling. Expected outcome: **60-70%** of selectors correct for known apps, remainder flagged for human review.

**Phase 3 — End-to-end PDD ingestion (3-4 months).** Build the document parsing pipeline: extract process steps, decision points, application references, data fields, and exception scenarios from PDDs/BRDs. Map extracted steps to UiPath service API calls. Implement the full Planner → Generator → Validator → Reviewer multi-agent architecture. Integrate with REFramework template generation. Target: generate a **complete project scaffold** from a standard PDD that requires 40-60% less developer effort to make production-ready.

---

## Likely failure modes and how to mitigate them

**API hallucination** is the top risk. LLMs will invent methods like `uiAutomation.ClickButton()` or `system.ReadExcel()` that don't exist. Mitigation: Roslyn compilation against actual UiPath packages catches these immediately. The error message "CS0117: 'IUIAutomationService' does not contain a definition for 'ClickButton'" provides enough context for the LLM to self-correct.

**Selector syntax errors** will be common — malformed XML, incorrect attribute names, impossible tag combinations. Mitigation: a custom XML validator for UiPath selector grammar, run before compilation, with clear error messages fed back to the generator.

**REFramework structural violations** — missing exception handling, incorrect transaction status updates, configuration mismatches. Mitigation: template-based generation where the REFramework structure is pre-built and only the business logic methods are generated.

**Over-simplified error handling** is an inherent LLM tendency. Generated code will typically implement the happy path and skip retry logic, business rule exceptions, system exception recovery, and logging. Mitigation: explicit prompting for error handling patterns, plus post-generation analysis that flags methods lacking try/catch blocks or missing `SetTransactionStatus` calls.

**Version drift** between UiPath packages will cause compilation failures as APIs change. Mitigation: version-pinned RAG indices that match the target project's `project.json` dependencies, updated when UiPath releases new package versions.

## Conclusion

The architecture is feasible today. Coded automations' C# foundation makes them a natural LLM generation target — orders of magnitude simpler than XAML. The compilation validation loop solves the API hallucination problem that would otherwise make generation unreliable. The hybrid REFramework approach (XAML orchestrator + coded business logic) avoids reinventing a proven pattern. And the phased strategy — non-UI first, then known-app UI, then full PDD ingestion — delivers value incrementally while deferring the hardest problem (selector generation for unknown applications).

The competitive landscape validates the timing: no open-source tool, no existing product, and no published research addresses this specific problem — generating valid UiPath coded automations from process documentation. FlowMind (JPMorgan) proved the "lecture-then-generate" RAG approach works at 99.5% accuracy for API-based workflow code. The delta is applying that architecture to UiPath's specific API surface, building the compilation feedback loop, and solving selector generation through Object Repository integration rather than pure inference.

The key insight from this research: **the bottleneck isn't code generation quality — it's context engineering.** The LLM needs to see the right API definitions, the right examples, and the right selector libraries at generation time. The system that wins will be the one that curates and serves that context most effectively.