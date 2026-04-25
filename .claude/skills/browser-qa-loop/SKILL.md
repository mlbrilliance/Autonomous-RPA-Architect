---
name: browser-qa-loop
description: Build → headed test → find bug → fix → retest loop for migrator-emitted Python+Playwright projects. Load before running a migrated artifact against a live target, when designing a new FaultFixer for browser automation, or when adding a new env-toggle to the BrowserSession harness. Distils the YouTube Playwright-CLI workflow into the seams this repo actually exposes.
---

# Browser QA-Loop

Closes the loop the YouTube Playwright-CLI walkthrough opens: instead of
emitting a project, running it manually, watching it fail, and patching by
hand, the lifecycle pieces here drive the fix automatically against a real
browser and a real target.

## When to run the loop

| Situation | Use |
|---|---|
| You just ran `emit_project()` and want to verify the artifact behaves | `MigratorQALoop.run(project_dir)` |
| You're adding a new fixer for some new exception class | Implement `FaultFixer` Protocol; register **before** `FixProposalFixer` in `agent.py:_resolve_fixer_pipeline` |
| You need to log into a real app once and reuse the session | Set `RPA_USER_DATA_DIR=/some/persistent/path`; works end-to-end through `BrowserSession`, the migrator-emitted `main.py`, and the harvester |

## The four primitives

```
QALoopRunner ──run──> FailureBundle ──remediate──> FixOutcome ──retry──> QALoopRunner
   (subprocess)        (lifecycle/state.py)        (FaultFixer)
```

1. **`BrowserSession`** (`src/rpa_architect/selectors/browser_session.py`) — single async ctx mgr; ephemeral or `launch_persistent_context(user_data_dir)`. Headed by default, headless via `RPA_HEADLESS=1`.
2. **`QALoopRunner`** (`src/rpa_architect/lifecycle/qa_loop.py`) — runs `python main.py` from a project dir in a subprocess, classifies traceback into `exception_type`, returns a `FailureBundle`.
3. **`MigratorQAFixer`** (`src/rpa_architect/lifecycle/migrator_qa_fixer.py`) — `FaultFixer` for python+playwright artifacts. Today: bumps `timeout=N` kwargs +5 s (cap 30 s). Selector drift escalates.
4. **`MigratorQALoop`** (`src/rpa_architect/lifecycle/migrator_qa_orchestrator.py`) — drives runner → registry → runner with bounded iterations.

## Headed by default

Default is headed (`headless=False`). Watch the browser while iterating. Flip
to headless for CI and scheduled runs:

```bash
RPA_HEADLESS=1 python main.py                 # migrator-emitted project
python proof/demo_qa_loop.py --headless       # demo
```

The `RPA_HEADLESS` env var is the single source of truth — `BrowserSession`,
the migrator template's emitted `main.py`, and the parity test template all
read it. Don't add a new flag.

## Persistent profile recipe

Log in once, automate forever:

```bash
export RPA_USER_DATA_DIR=~/.cache/rpa_architect/profiles/odoo
python proof/harvest_odoo.py     # first run: log in manually, profile saved
python proof/harvest_odoo.py     # second run: already authenticated
```

Convention: `~/.cache/rpa_architect/profiles/<system_name>` per target. Each
profile is a real Chromium user-data dir — cookies, localStorage, IndexedDB,
service workers all persist. Put the dir on a tmpfs if you don't want it to
survive reboot.

## Failure-bundle conventions

`MigratorQAFixer` and `FixProposalFixer` route on `FailureBundle.exception_type`
substrings (the convention is pinned in `fix_proposal_fixer.py:_EXCEPTION_TYPE_MAP`):

| Substring | Category | Action |
|---|---|---|
| `Selector` | `selector_drift` | `update_selectors` |
| `Null` | `code_bug` | `fix_code` |
| `Timeout` | `system_timeout` | `escalate_to_human` (or auto-bump if migrator artifact) |
| `BusinessRule` | `business_rule_violation` | `update_config` |
| `Credential` | `credential_expiry` | `escalate_to_human` |
| `Schema` | `data_schema_change` | `update_config` |

When adding a new `FaultFixer`, classify your traceback into one of these
strings (or extend the map). `qa_loop.classify_traceback()` is the public
entry point if you need to reuse the parsing.

## Mutex with SwarmFaultFixer

`SwarmFaultFixer.can_handle` is true iff `failure.xaml_files` is non-empty —
i.e., the failure carries deployed XAML the swarm can patch.
`MigratorQAFixer.can_handle` is true iff `failure.project_dir/main.py` exists
**and** `xaml_files` is empty. Mutually exclusive by construction; safe to
register both. Order in `agent.py:_resolve_fixer_pipeline` is
`MigratorQAFixer → SwarmFaultFixer → FixProposalFixer (catch-all)`.

## What the loop does NOT do

- **No automatic re-harvesting on selector drift.** That needs a target URL
  the lifecycle agent doesn't currently thread through. `MigratorQAFixer`
  escalates with structured pointers; a human re-harvests, or a future
  fixer can.
- **No live login automation.** `_attempt_login` in `browser_harvester.py`
  guesses common selectors but is not a substitute for a persistent profile
  for SaaS targets that 2FA.
- **No graph-level integration.** The LangGraph lifecycle in `agent.py` does
  not yet call `MigratorQALoop`. `proof/demo_qa_loop.py` invokes it directly;
  to wire it into deploy, add a `qa_run` node before `deploy` that calls
  `MigratorQALoop.run(state.migrator_output_dir)`.

## Demo

```bash
python proof/demo_qa_loop.py            # headed (default)
python proof/demo_qa_loop.py --headless # CI-style
```

Mirrors the YouTube flow: stdlib HTTP server with a button that appears 4 s
after page load, migrator emits a project with a tight 1500 ms wait, QA loop
runs (fail), `MigratorQAFixer` bumps to 6500 ms, QA loop runs (pass).
