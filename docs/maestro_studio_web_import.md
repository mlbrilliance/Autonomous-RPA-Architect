# Importing the Maestro Design Assets into Studio Web

This walkthrough covers importing the `InvoiceProcessingFlow.bpmn` +
`InvoiceRulesDecision.dmn` artifacts that `proof/deploy_odoo.py`
generates as a sibling to the packaged project. After these steps,
you'll have a Maestro process at the orchestration layer that invokes
the already-deployed `OdooInvoiceProcessing` REFramework process, so
the bot pipeline has both **low-level execution** (the .nupkg running
on a serverless robot) and **high-level orchestration** (the BPMN
flow in Studio Web).

## Why manual?

UiPath Maestro has **no public deployment API** as of 2025.10 / 2026.
Every attempted path to deploy a BPMN via REST returned 403/404 or
wasn't documented. The ONLY supported way to get a BPMN into a
running Maestro process is the Studio Web designer. See
`docs/community_cloud_limitations.md` §4 for the full evidence.

## Prerequisites

- You have already run `python proof/deploy_odoo.py` at least once.
- The files exist at
  `demo-output/odoo_project_enterprise_maestro/InvoiceProcessingFlow.bpmn`
  and `…/InvoiceRulesDecision.dmn`.
- You're signed in at `cloud.uipath.com` with the same user that owns
  the `OdooInvoiceProcessing` release in Orchestrator.

## Step 1 — Open Studio Web Maestro

1. Go to `https://cloud.uipath.com/mlbrilliance/DefaultTenant/studio_/`
   (replace with your org+tenant).
2. In the top nav, click **Maestro** (the BPMN-styled icon). If you
   don't see it, check Admin → Services and ensure the Maestro
   service is enabled for your tenant.

## Step 2 — Create a new Maestro process

1. Click **New** → **Process** → **From BPMN**.
2. Name it `Invoice Processing Factory`.
3. When prompted for a source, choose **Upload BPMN file** and
   select `InvoiceProcessingFlow.bpmn` from the sibling folder.
4. Studio Web will parse the file and render the diagram. You
   should see:
   - Start event: "Invoice batch arrives"
   - Service task: "Receive Invoice Batch" (queue-bound)
   - Service task: "Document Understanding" (marked as an agent task)
   - Exclusive gateway: "Confidence ≥ 0.8?"
   - User task: "Human Validation" (Action Center)
   - Business rule task: "Evaluate Business Rules"
   - Exclusive gateway: "Rule verdict?"
   - Service tasks: "Create Vendor Bill in Odoo", "Send Confirmation
     Email", "Log Rejection", "Manager Approval"
   - End events: "Batch processed", "Batch rejected"

## Step 3 — Bind the service tasks to real implementations

Service tasks in BPMN are placeholders — you link each to a concrete
implementation. Click each task in order:

### Task_ReceiveBatch → Orchestrator queue
- Select **Queue** as the implementation type
- Queue: `OdooInvoices` (the one seeded by `proof/deploy_odoo.py`)
- Folder: `Shared`

### Task_DU → Agent
- Implementation: **Agent**
- Agent type: extraction
- Model: `du.uipath.com/invoices`
- Confidence threshold: 0.80
- *(This is a design-time marker — execution happens inside the C#
  CodedWorkflow, not here. The Maestro layer is a higher-level view.)*

### Task_Rules → DMN
- Implementation: **Decision**
- Click **Import DMN** and upload `InvoiceRulesDecision.dmn`
- Input bindings:
  - `Currency` ← `invoice.Currency`
  - `IsDuplicate` ← `odoo.search_count(ref, partner)` > 0
  - `IsNewVendor` ← `odoo.search_read(partner).length == 0`
  - `AmountUsd` ← `invoice.TotalAmount * fx[Currency]`
  - `Confidence` ← `invoice.AvgConfidence`
- Output binding: `verdict` → `rules.Verdict`

### Task_CreateBill → Invoke Process
- Implementation: **Orchestrator Process**
- Process: `OdooInvoiceProcessing` (the release the .nupkg is in)
- Arguments: pass the extracted fields as input

### Task_HumanValidation → Action Center
- Implementation: **Action** (Task Catalog → Form task)
- **⚠ Community tier users:** Action Center is Enterprise-only. Leave
  this task in the diagram as a design-time placeholder but do NOT
  try to publish it. In Community tier, manager approval happens via
  the `mail.activity` record the C# bot attaches to the created bill.

### Task_ManagerApproval → Odoo activity (or leave as design placeholder)
- Implementation: **Custom** or skip
- In Community tier, the C# bot already handles this via
  `OdooClient.CreateManagerApprovalTaskAsync`

### Task_Notify → Email
- Implementation: **Send Mail**
- To: `${input.vendor_contact}`
- Subject: `Invoice ${input.invoiceNumber} processed`

## Step 4 — Publish

1. Click **Publish** (top right).
2. Choose folder: `Shared`.
3. Confirm.

## Step 5 — Test run

1. Click **Test** → **Start**.
2. Provide a sample payload:
   ```json
   {
     "batchId": "TEST-001"
   }
   ```
3. Watch the execution path light up green/red through the gateways.
4. Cross-reference against the UiPath **Orchestrator Jobs** page —
   the `Task_CreateBill` service task should trigger a real job
   on the `OdooInvoiceProcessing` release, and that job should
   create real `account.move` records in Odoo just like the direct
   `proof/deploy_odoo.py` invocation does.

## Expected end state

Once published, you have:

- One **Maestro process** `Invoice Processing Factory` visible at
  `cloud.uipath.com/{org}/{tenant}/maestro_/processes`
- One **Orchestrator release** `OdooInvoiceProcessing` that the
  Maestro service task invokes for the actual compute
- The same real DMN rule set used by both the BPMN decision node AND
  the C# `BusinessRuleEngine` inside the compiled DLL (single source
  of truth for business logic)

## Troubleshooting

**"Cannot create unknown task type agent://du.extractor"** — Studio
Web doesn't recognize the `agent://` implementation URI. Change the
`Task_DU` task type from "Agent" to "Script" and note in the task
properties that execution happens inside the invoked REFramework
process.

**"Decision table references undefined variables"** — the DMN's input
entries (`Currency`, `IsDuplicate`, etc.) weren't bound. Re-open the
task and verify each input has a source expression pointing at the
previous task's output.

**"Publish failed — feature not available"** — your tenant doesn't
have the Maestro service enabled. Admin → Services → Enable Maestro.
If the button is disabled, Maestro isn't available in Community tier
for your account — you'll need a paid tier or an early-access
program invitation.

---

*Honest note:* I have not personally walked these steps end-to-end in
Studio Web because my external-app session doesn't have Maestro
designer access. The steps above are derived from the public Maestro
documentation and the same BPMN+DMN format that Camunda and other
BPMN engines use. If you hit a concrete blocker in Studio Web that
this doc doesn't cover, please file an issue with the error message
and I'll update it.
