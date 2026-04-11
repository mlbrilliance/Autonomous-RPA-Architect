---
description: Download the latest OdooInvoiceProcessing release from UiPath Community Cloud and run the 17-assertion package integrity check against it.
argument-hint: [version]
---

# uipath-verify-package

Wraps `proof/verify_package_contents.py`. Downloads the currently-live
release (or a specific version if `$ARGUMENTS` is a version string) from
Orchestrator, unzips the `.nupkg`, and runs the 17 structural assertions
that `demo-output/odoo/package_proof.txt` was built from.

## Assertions checked

1. `.nupkg` is a valid ZIP
2. Contains `[Content_Types].xml`, `_rels/`, `package/`
3. `content/project.json` is present + valid JSON
4. `project.json` has `"targetFramework": "Portable"`
5. `project.json` has `"projectProfile": 0` (numeric, not string)
6. `project.json` has `"main": "Main.xaml"`
7. `project.json` has `"requiresUserInteraction": false`
8. `lib/net8.0/OdooInvoiceProcessing.dll` exists
9. DLL is a valid PE file (MZ header)
10. DLL exports a `ProcessInvoiceMain` type
11. `ProcessInvoiceMain` is decorated with `[Workflow]`
12. `ProcessInvoiceMain` inherits from `CodedWorkflow`
13. `ProcessInvoiceMain.Execute` method exists and returns `Task`
14. `content/Main.xaml` is present and contains no expressions
15. 5 embedded invoices resolve in `EmbeddedInvoices.All` (via reflection)
16. `OdooClient` has the methods `EnsurePartnerAsync`, `CreateVendorBillAsync`, `CreateManagerApprovalTaskAsync`
17. Package version matches the Orchestrator release version

## When the user runs `/uipath-verify-package`

1. Load `.env`, exchange OAuth token
2. If `$ARGUMENTS` is empty: fetch the current release version via
   `/odata/Releases?$filter=Name eq 'OdooInvoiceProcessing'`
3. Download the `.nupkg` from `/odata/Processes(Key='...')/UiPath.Server.Configuration.OData.DownloadPackage`
4. Run `python proof/verify_package_contents.py --nupkg /tmp/...nupkg`
5. Print a PASS/FAIL report for each of the 17 assertions — don't summarize
6. Exit non-zero if anything failed, so this command is usable as a CI gate

## Don't do

- Don't fake the assertions — each one must read real bytes from the downloaded package
- Don't skip #8–#13 just because DLL introspection is harder — they're the whole point
