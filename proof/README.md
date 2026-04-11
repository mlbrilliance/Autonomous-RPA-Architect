# Proof of v0.3.0 Features

This directory contains two types of proof:

1. **`e2e_live_demo.py`** — End-to-end live proof against a real website (the main proof)
2. **`demo_v030.py`** — Programmatic feature validation (53 internal checks)

---

## End-to-End Live Proof (THE PROOF)

Navigates to a real public website via Playwright, harvests real DOM elements, builds UiPath selectors, generates a complete REFramework project, and produces a comprehensive report.

### Running It

```bash
# Prerequisites (one-time)
pip install playwright
python3 -m playwright install chromium

# Run the proof
python3 proof/e2e_live_demo.py
```

### What It Does (13 phases, ~7s)

| Phase | What Happens | Result |
|-------|-------------|--------|
| 0 | Setup directories, check Playwright | Directories created |
| 1 | Build ProcessIR (5 pages, 7 actions) | `process_ir.json` |
| 2 | **Launch Playwright, navigate 5 pages, screenshot, harvest DOM** | 5 screenshots, 16 elements |
| 3 | Match actions to elements (heuristic + enhanced fallbacks) | **6/7 matched (86%)** |
| 4 | Convert to UiPath XML selectors with stability scoring | 7 selectors (6 real + 1 placeholder) |
| 5 | Score selector quality (0-100) | **89/100 aggregate** |
| 6 | Generate REFramework XAML + Process_WithActivities.xaml | 10 XAML files with real `ui:NClick`, `ui:NTypeInto` |
| 7 | Generate Object Repository v2 (hierarchical) | 8 files, schema v2.0 |
| 8 | Generate coded C# workflows with real selectors | 2 .cs files |
| 9 | Generate project.json (Studio 25.10) | `toolVersion: 25.10.0` |
| 10 | XAML lint (21+ rules) | 6 false-positive, 16 info |
| 11 | Coded workflow lint (4 rules) | 1 minor issue |
| 12 | Generate SUMMARY.md report | Full metrics |

### Target Website

**https://the-internet.herokuapp.com/** — no login required. Pages tested:

- `/add_remove_elements/` — button clicks
- `/checkboxes` — checkbox interactions
- `/dropdown` — dropdown selection
- `/inputs` — number input
- `/key_presses` — text input + text extraction

### Output Structure

```
proof/e2e_output/
├── SUMMARY.md                                # Human-readable full report
├── console.log                               # Complete run log
├── process_ir.json                           # The ProcessIR used
├── screenshots/TheInternet/
│   ├── S001.png                              # Add/Remove Elements page
│   ├── S002.png                              # Checkboxes page
│   ├── S003.png                              # Dropdown page
│   ├── S004.png                              # Inputs page
│   └── S005.png                              # Key Presses page
├── harvested_data/
│   ├── TheInternet_report.json               # Full BrowserHarvestReport
│   ├── S001_elements.json ... S005_elements.json  # Per-page elements
│   └── match_results.json                    # Match results + confidence
├── selectors/
│   ├── all_selectors.json                    # element_name → selector_xml
│   └── selector_details.json                 # With stability scores
├── uipath_project/
│   ├── project.json                          # Studio 25.10 manifest
│   ├── Main.xaml                             # REFramework state machine
│   ├── Process_WithActivities.xaml           # REAL XAML with harvested selectors
│   ├── ProcessTestPages.cs                   # Coded workflow with real selectors
│   ├── Framework/*.xaml                      # 8 REFramework files
│   ├── .objects/descriptor.json              # Object Repository v2
│   ├── .objects/TheInternet/1.0/TheInternet/ # Per-element definitions
│   └── Tests/TestVerification.cs             # Coded test case
└── reports/
    ├── selector_scores.json
    ├── xaml_lint_report.json
    └── coded_lint_report.json
```

### Key Artifacts

- **`Process_WithActivities.xaml`** — Real UiPath XAML with `ui:NClick`, `ui:NCheck`, `ui:NSelectItem`, `ui:NTypeInto` activities using live-harvested selectors
- **`ProcessTestPages.cs`** — Coded C# workflow calling `screen.Click()`, `screen.TypeInto()` with real element names
- **`.objects/descriptor.json`** — Object Repository v2 with hierarchical element definitions
- **Screenshots** — 5 real PNG screenshots from the live website

---

## Feature Validation (demo_v030.py)

This directory also contains a comprehensive programmatic demonstration that every v0.3.0 feature works correctly.

## Running the Demo

```bash
python3 proof/demo_v030.py
```

## What It Verifies (53 checks)

| Work Stream | Checks | What's Tested |
|-------------|--------|---------------|
| WS1: Studio 2025.10 | 9 | NuGet 25.10.x versions, UIAutomation rename, project.json schema, WaitScreenReady generator, XL-BP009 lint rule |
| WS2: Coded APIs | 11 | 16 C# API generators (system.*, uiAutomation.*), coded workflow .cs generation |
| WS3: Object Repo v2 | 7 | Hierarchical schema, descriptor.json, element files, variable extraction/resolution |
| WS4: Agent Scaffold | 8 | uipath.json, entry-points.json, pyproject.toml, main.py generation |
| WS5: Validation | 7 | 4 coded lint rules (XL-C001 to C004), selector quality scoring |
| WS6: MCP/CLI | 8 | 4 MCP tools, 4 CLI commands |
| Stats | 3 | 96 generators, 21+ XAML lint rules |

## Output Files

After running the demo, `proof/output/` contains:

```
output/
├── .objects/                          # Object Repository v2 (hierarchical)
│   ├── descriptor.json                # Schema v2.0 master index
│   └── InvoicePortal/2.1/           # App > Version > Screen > Element
│       ├── LoginScreen/
│       │   ├── Username_Field.json
│       │   ├── Password_Field.json
│       │   └── Login_Button.json
│       └── DashboardScreen/
│           └── Search_Box.json
├── ProcessInvoice.cs                  # Generated coded workflow
├── wait_screen_ready.xml              # New 25.10 activity
└── agent_scaffold/                    # UiPath Python SDK scaffold
    ├── uipath.json
    ├── entry-points.json
    ├── pyproject.toml
    └── main.py
```

## Test Suite

671 tests passing (up from 537 in v0.2.0):
- 537 original v0.2.0 tests (all passing, zero regressions)
- 40 WS1 Studio 2025.10 compatibility tests
- 25+ WS2 coded API generator tests
- 15+ WS3 Object Repository v2 tests
- 10+ WS4 agent scaffold tests
- 20+ WS5 validation tests (coded lint + selector scorer)
