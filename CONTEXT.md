# Project Context — autonomous-rpa-architect

This file pins concept names so future architecture passes don't re-suggest the same refactors. Add a term here once it appears in module names, public types, or routing logic.

## Architecture vocabulary

### FaultFixer
A pluggable adapter that remediates one kind of deployed-bot failure. Lives in `lifecycle/fault_fixer.py` as a `typing.Protocol`. Each adapter declares `can_handle(failure: FailureBundle) -> bool` and `fix(failure) -> FixOutcome`. The lifecycle layer iterates a `FixerRegistry` in priority order; first match wins. Any fan-out + arbitration (as in the self-healing swarm) is the adapter's private business.

Concrete adapters today:

- `SwarmFaultFixer` (`lifecycle/swarm_fault_fixer.py`) — wraps `SwarmOrchestrator.heal_bundle()`. Claims when the bundle carries `xaml_files` (the swarm needs XAML to patch). Maps `SwarmVerdict → FixOutcome`.
- `FixProposalFixer` (`lifecycle/fix_proposal_fixer.py`) — catch-all. `can_handle` always True. Synthesizes a `DiagnosisResult` from the bundle (substring-match on `exception_type`), invokes the older `fix_proposer.generate_fix_proposal`, and emits a `FixOutcome` with `requires_escalation=True` — never auto-merges.

Registry ordering convention: more-specific fixers first, `FixProposalFixer` last (it claims unconditionally).

### FixOutcome
Frozen dataclass returned by every `FaultFixer.fix()`. Carries `success`, `requires_escalation`, `delivery_url` (PR url, ticket, or empty), `diagnosis_category`, optional `proposal` (a `FixProposal` for the human-approval path — only `FixProposalFixer` populates it today), and adapter-specific `evidence`. Lifecycle nodes after the fix step read only this dataclass — they do not branch on which adapter ran.

### FailureBundle
The single input to fault remediation: one faulted UiPath job's exception, robot logs, deployed XAML files, and folder. Composed by `lifecycle/swarm/failure_bundle.py:FailureBundleFetcher` from three Orchestrator endpoints. Defined in `lifecycle/state.py`.

### FixOutputs
Typed sub-record on `LifecycleState` that owns everything the fix branch produces: `outcome` (most recent `FixOutcome`), `history` (chronological list of every outcome this run), `approval_status` (pending / approved / rejected). Lifecycle nodes read `state.fix.outcome`, `state.fix.history`, `state.fix.approval_status` — never as top-level state fields.

### MonitoringOutputs
Typed sub-record on `LifecycleState` that owns the observation phase's artefacts: `report` (MonitoringReport), `diagnosis` (DiagnosisResult), `drift_report` (DriftReport — populated by the future `DriftRemediator` work). Lifecycle nodes read `state.monitoring.report`, `state.monitoring.diagnosis`. Sibling to `FixOutputs` and `AuthoringOutputs`.

### AuthoringOutputs
Typed sub-record on `LifecycleState` that owns the authoring + codegen phase's artefacts: `ir` (lifted ProcessIR dict), `generation_result` (raw `generate_from_pdd` / `generate_from_ir` result), `project_dir` (local project root). Lifecycle nodes read `state.authoring.ir`, `state.authoring.project_dir`, `state.authoring.generation_result` — never as top-level state fields. Constructors (`cli.py`, `mcp_server/tools.py`) wrap caller-supplied `output_dir` as `AuthoringOutputs(project_dir=...)`. `fix_node`'s no-fetcher synthesis path reads `state.authoring.project_dir` and forwards it on `FailureBundle.project_dir`.

`LifecycleState` is now `request + authoring + monitoring + fix + deployment + scalars` — five typed top-level concerns down from sixteen flat fields.

### fix_node
The unified LangGraph node (`lifecycle/fix_node.py`) that runs the registry against the first faulted job in `state.monitoring_report.failed_jobs`. Records every attempt on `state.fix_history` and the most recent on `state.last_fix_outcome`. Lifecycle routing (`route_after_fix`) reads only `last_fix_outcome` — never adapter-specific fields. Replaces the older `lifecycle/swarm/node.py` (deleted).

### create_lifecycle_graph entrypoints
- `create_lifecycle_graph(swarm=…)` — legacy. Builds `[SwarmFaultFixer, FixProposalFixer]` automatically and reuses `swarm.fetcher`.
- `create_lifecycle_graph(fixer_registry=…, fetcher=…)` — caller controls the full pipeline.
- `create_lifecycle_graph()` — defaults to `[FixProposalFixer]` only; the fetcher is omitted and `fix_node` synthesizes a minimal `FailureBundle` from `state.monitoring_report.failed_jobs[0]`.

All three paths route the same way: `diagnose → fix → (success+delivery_url ⇒ END | requires_escalation ⇒ approval_gate → apply_fix → validate_gate | else ⇒ END)`. The old `propose_fix` node is gone; its work is now inside `FixProposalFixer.fix()`.

Mixing `swarm=` with `fixer_registry=` is rejected to keep wiring deterministic.

### Drift remediation (separate concern)
Behavioural-drift detection (`lifecycle/drift_detector.py` → `DriftReport`) is **not** a `FaultFixer`. Its trigger is a `MonitoringReport` aggregate, not a single failure, and its outputs are typically config-tuning suggestions rather than XAML patches. A future `DriftRemediator` protocol will be its own sibling — they do not share a base class.

### LintDocument
The seam every XAML lint rule depends on. Lives in `xaml_lint/lint_document.py`. Wraps a parsed input with three things rules previously had to invent themselves: a per-instance line-number map (`line_of(elem)`), traversal helpers (`activities()`, `iter_all()`), and tag classification (`local_name`, `is_structural`, `is_property_accessor`). Two flavours: `LintDocument.from_xaml(text)` and `LintDocument.from_coded(text)` — `kind: ContentKind` discriminates. Replaced the old module-global `_line_map` dict (now deleted) which was a hidden concurrency hazard.

### Rule (lint contract) + `@rule(...)` decorator + ContentKind
A registered lint rule is a function with the signature `(doc: LintDocument) -> list[LintIssue]`, decorated with `@rule(id=..., severity=..., category=..., applies_to=ContentKind.XAML | CODED)`. The decorator registers the rule in a module-level registry; the engine dispatches each rule only to documents whose `kind` matches. Defined in `xaml_lint/rule.py`.

`ContentKind` is the dispatch tag — XAML rules read the parsed tree, CODED rules read raw C# source. Single enum (a rule applies to exactly one kind today; YAGNI for sets).

### Lint engine
`LintEngine` (`xaml_lint/engine.py`) is a thin orchestrator: build a `LintDocument`, filter the registry by `applies_to`, run each rule with a per-rule try/except. Two construction shapes: `LintEngine()` starts empty (matches the historical contract — plugins call `register_rule(fn)` to add rules); `create_default_engine()` returns an engine wired to all decorator-registered rules. `register_rule(fn)` accepts the legacy `(root, ns) -> list[LintIssue]` callable shape — the engine wraps it in a `Rule` so plugins keep working. The duplicate `_default_engine` singleton in `__init__.py` was removed; `__init__.py` now delegates to `engine.get_default_engine()`.

XAML and coded-workflow rules now share one registry. Calling `lint_xaml()` runs only XAML rules; `lint_coded_file()` builds a CODED document and the engine dispatches only the four coded rules to it. Before this seam, coded rules lived outside the engine entirely and were never invoked by `lint_project()`.
