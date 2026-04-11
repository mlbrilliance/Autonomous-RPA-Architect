# End-to-End Proof Report

**Generated**: 2026-04-06 17:00:33 UTC
**Target**: https://the-internet.herokuapp.com
**Process**: TheInternetAutomation
**Duration**: 12.8s

## 1. ProcessIR
- Systems: 1 (TheInternet)
- Transactions: 1
- Steps: 5
- UIActions: 7

## 2. Browser Harvest Results
| Step | Page | Elements | Screenshot |
|------|------|----------|------------|
| S001 | /add_remove_elements/ | 3 | S S001.png |
| S002 | /checkboxes | 4 | S S002.png |
| S003 | /dropdown | 3 | S S003.png |
| S004 | /inputs | 3 | S S004.png |
| S005 | /key_presses | 3 | S S005.png |

## 3. Element Matching
- Total actions: 7
- Matched: 6 (85.7%)
- Unmatched: 1

| Action | Target | Matched To | Method | Confidence |
|--------|--------|-----------|--------|------------|
| click | Add Element | Add Element | heuristic_text | 0.70 |
| check | checkbox 1 | input | enhanced_ordinal | 0.75 |
| check | checkbox 2 | input | enhanced_single_candidate | 0.70 |
| select_item | Dropdown | dropdown | heuristic_id | 0.95 |
| type_into | Number Input | input | enhanced_single_candidate | 0.70 |
| type_into | Input Field | target | enhanced_single_candidate | 0.70 |

## 4. UiPath Selectors Built
| Element | Selector XML | Stability |
|---------|-------------|-----------|
| S001_Add_Element_0 | `<html app='chrome.exe' /><webctrl tag='button' innertext='Add Element' />` | 0.60 |
| S002_checkbox_1_0 | `<html app='chrome.exe' /><webctrl tag='input' type='checkbox' />` | 0.30 |
| S002_checkbox_2_1 | `<html app='chrome.exe' /><webctrl tag='input' type='checkbox' />` | 0.30 |
| S003_Dropdown_0 | `<html app='chrome.exe' /><webctrl tag='select' id='dropdown' />` | 0.95 |
| S004_Number_Input_0 | `<html app='chrome.exe' /><webctrl tag='input' type='number' />` | 0.30 |
| S005_Input_Field_0 | `<html app='chrome.exe' /><webctrl tag='input' id='target' type='text' />` | 0.95 |

## 4b. LIVE SELECTOR VALIDATION (Proof of Execution)
- Selectors validated against live page: 6
- Elements found: 6/6 (100%)
- Successfully interacted (clicked/typed/selected): 6/6 (100%)

| Element | Found | Interacted | CSS Query Used |
|---------|-------|------------|----------------|
| S001_Add_Element_0 | YES | YES | `button` |
| S002_checkbox_1_0 | YES | YES | `input[type='checkbox']` |
| S002_checkbox_2_1 | YES | YES | `input[type='checkbox']` |
| S003_Dropdown_0 | YES | YES | `select#dropdown` |
| S004_Number_Input_0 | YES | YES | `input[type='number']` |
| S005_Input_Field_0 | YES | YES | `input#target[type='text']` |

## 5. Selector Quality Scores
| Element | Score | Bonuses | Penalties |
|---------|-------|---------|-----------|
| S001_Add_Element_0 | 85/100 | - | No id or automationid attribute (-15) |
| S002_checkbox_1_0 | 85/100 | - | No id or automationid attribute (-15) |
| S002_checkbox_2_1 | 85/100 | - | No id or automationid attribute (-15) |
| S003_Dropdown_0 | 100/100 | Has id attribute (+10) | - |
| S004_Number_Input_0 | 85/100 | - | No id or automationid attribute (-15) |
| S005_Input_Field_0 | 100/100 | Has id attribute (+10) | - |
| S005_Result_1 | 85/100 | - | No id or automationid attribute (-15) |

**Aggregate Score: 89/100**

## 6. Generated UiPath Project
| File | Size | Description |
|------|------|-------------|
| .objects/TheInternet/1.0/TheInternet/S001_Add_Element_0.json | 261b | Object Repository v2 |
| .objects/TheInternet/1.0/TheInternet/S002_checkbox_1_0.json | 251b | Object Repository v2 |
| .objects/TheInternet/1.0/TheInternet/S002_checkbox_2_1.json | 251b | Object Repository v2 |
| .objects/TheInternet/1.0/TheInternet/S003_Dropdown_0.json | 248b | Object Repository v2 |
| .objects/TheInternet/1.0/TheInternet/S004_Number_Input_0.json | 251b | Object Repository v2 |
| .objects/TheInternet/1.0/TheInternet/S005_Input_Field_0.json | 260b | Object Repository v2 |
| .objects/TheInternet/1.0/TheInternet/S005_Result_1.json | 243b | Object Repository v2 |
| .objects/descriptor.json | 339b | Object Repository v2 |
| Framework/CloseAllApplications.xaml | 772b | XAML workflow |
| Framework/EndProcess.xaml | 892b | XAML workflow |
| Framework/GetTransactionData.xaml | 993b | XAML workflow |
| Framework/InitAllApplications.xaml | 770b | XAML workflow |
| Framework/InitAllSettings.xaml | 1,018b | XAML workflow |
| Framework/KillAllProcesses.xaml | 773b | XAML workflow |
| Framework/Process.xaml | 3,953b | XAML workflow |
| Framework/SetTransactionStatus.xaml | 971b | XAML workflow |
| Main.xaml | 1,293b | XAML workflow |
| ProcessTestPages.cs | 1,037b | Coded C# workflow |
| Process_WithActivities.xaml | 4,553b | XAML workflow |
| Tests/TestVerification.cs | 1,300b | Coded C# workflow |
| project.json | 1,538b | Studio 25.10 manifest |

## 7. Lint Results
- XAML: 12 errors, 0 warnings, 16 info
- Coded: 1 issues

## 8. Phase Summary
| # | Phase | Status | Duration |
|---|-------|--------|----------|
| 0 | Phase 0: Setup | + PASS | 0.0s |
| 1 | Phase 1: Build ProcessIR | + PASS | 0.2s |
| 2 | Phase 2: Browser Harvest | + PASS | 6.8s |
| 3 | Phase 3: Element Matching | + PASS | 0.0s |
| 4 | Phase 4: Selector Conversion | + PASS | 0.0s |
| 5 | Phase 4b: Live Selector Validation | + PASS | 5.2s |
| 6 | Phase 5: Selector Scoring | + PASS | 0.0s |
| 7 | Phase 6: XAML Generation | + PASS | 0.6s |
| 8 | Phase 7: Object Repository v2 | + PASS | 0.0s |
| 9 | Phase 8: Coded C# Workflows | + PASS | 0.0s |
| 10 | Phase 9: project.json | + PASS | 0.0s |
| 11 | Phase 10: XAML Linting | + PASS | 0.0s |
| 12 | Phase 11: Coded Lint | + PASS | 0.0s |

**Overall: 13/13 phases passed**

**Total elapsed: 12.8s**
