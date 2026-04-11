---
name: reframework-coded-workflow
description: Translating the UiPath REFramework state machine (Init → GetTransactionData → Process → SetTransactionStatus → End) into a C# Coded Workflow (.NET 8 / Portable) so it runs on the Community Cloud Linux serverless robot. Load when generating REFramework automation targeted at the Linux runtime, or when the user asks for "REFramework but coded" / "enterprise invoice processing pattern".
---

# REFramework as a C# Coded Workflow

Classic REFramework ships as a ~20-file XAML project. It won't run on the
Portable / Linux serverless runtime (see `uipath-community-cloud-gotchas` §1).
This skill captures the equivalent **compiled C#** shape that does.

Reference implementation: `src/rpa_architect/codegen/reframework_csharp_gen.py`
generates all 16 C# files from a Python IR. `tests/test_codegen/test_reframework_csharp_gen.py`
compile-verifies them with `dotnet build` on every run.

## File layout (16 files, compiled into one DLL)

```
ProcessInvoiceMain.cs     [Workflow] Execute() driver — the state machine loop
IState.cs                 interface IState { Task<IState?> ExecuteAsync(ProcessContext ctx); }
InitState.cs              load config, warm-up auth, build queue
GetTransactionDataState.cs pop next item from ctx.Queue
ProcessState.cs           the real business work (extract → rules → ERP write)
SetTransactionStatusState.cs advance index, clear per-item state
EndState.cs               emit batch summary
ProcessExceptions.cs      BusinessException vs RpaSystemException
ProcessContext.cs         shared mutable state across transitions
ProcessConfig.cs          thresholds, endpoints, whitelists
BatchMetrics.cs           per-run aggregates
BusinessRuleEngine.cs     IRule + chain evaluator + 4 rules
DocumentUnderstandingClient.cs DU Cloud API v2 client (with scope-missing fallback)
LocalInvoiceExtractor.cs  fallback extractor using embedded ground truth
OdooClient.cs             JSON-RPC ERP adapter
EmbeddedInvoices.cs       base64 constants — ships the test PDFs inside the DLL
```

## The state machine driver

```csharp
[Workflow]
public class ProcessInvoiceMain : CodedWorkflow
{
    public async Task Execute()
    {
        var config = new ProcessConfig();
        var ctx = new ProcessContext { Config = config };

        IState? state = new InitState();
        while (state is not null)
        {
            try
            {
                state = await state.ExecuteAsync(ctx);
            }
            catch (BusinessException bex)
            {
                // Log, mark item failed, move on to next
                ctx.Metrics.BusinessFailures++;
                state = new SetTransactionStatusState();
            }
            catch (RpaSystemException rex) when (ctx.RetryCount < 3)
            {
                // Exponential backoff retry on same state
                await Task.Delay(TimeSpan.FromSeconds(Math.Pow(2, ctx.RetryCount)));
                ctx.RetryCount++;
                // state stays the same — retry
            }
        }
    }
}
```

## Exception discipline (critical for audit)

Two exception types, very different handling:

- **`BusinessException`** — business rule violation or expected "this item
  isn't processable" condition (duplicate invoice, missing vendor,
  unsupported currency). Log, **skip** the item, advance to next.
- **`RpaSystemException`** — infrastructure failure (network timeout, HTTP
  500, JSON parse failure). **Retry** the same state up to 3 times with
  exponential backoff before giving up and faulting the job.

Never catch `Exception` at the top level — let unknown exceptions fault
the job loudly so Orchestrator flags them.

## The four states that do real work

### InitState
```csharp
public async Task<IState?> ExecuteAsync(ProcessContext ctx) {
    // Warm up auth — fail fast if creds are wrong
    await ctx.Odoo.FindPartnerByNameAsync("__warmup__");
    // Load queue from embedded or external source
    ctx.Queue = new Queue<EmbeddedInvoice>(EmbeddedInvoices.All);
    return new GetTransactionDataState();
}
```

### GetTransactionDataState
```csharp
public async Task<IState?> ExecuteAsync(ProcessContext ctx) {
    if (ctx.Queue.Count == 0) return new EndState();
    ctx.Current = ctx.Queue.Dequeue();
    return new ProcessState();
}
```

### ProcessState
```csharp
public async Task<IState?> ExecuteAsync(ProcessContext ctx) {
    // 1. Extract
    var doc = ctx.Config.UseLiveDuApi
        ? await ctx.Du.ExtractAsync(ctx.Current)
        : LocalInvoiceExtractor.Extract(ctx.Current);

    // 2. Evaluate rules
    var verdict = await ctx.Rules.EvaluateAsync(doc, ctx);
    if (verdict == RuleVerdict.Reject)
        throw new BusinessException($"Rules rejected: {ctx.Rules.LastReason}");

    // 3. Ensure partner and create bill
    var partnerId = await ctx.Odoo.EnsurePartnerAsync(doc.VendorName);
    var billId = await ctx.Odoo.CreateVendorBillAsync(doc, partnerId, doc.LineItems);

    // 4. Flag for review if needed
    if (verdict == RuleVerdict.FlagForReview)
        await ctx.Odoo.CreateManagerApprovalTaskAsync(billId, ctx.Rules.LastReason);

    ctx.Metrics.BillsCreated++;
    ctx.Metrics.RecordVendor(doc.VendorName);
    return new SetTransactionStatusState();
}
```

### EndState
```csharp
public Task<IState?> ExecuteAsync(ProcessContext ctx) {
    Console.WriteLine($"Batch summary: {ctx.Metrics}");
    return Task.FromResult<IState?>(null);  // null = loop exits
}
```

## The rule engine pattern

```csharp
public interface IRule {
    Task<RuleResult> EvaluateAsync(ExtractedDocument doc, ProcessContext ctx);
}

public class BusinessRuleEngine {
    private readonly IReadOnlyList<IRule> _rules;
    public async Task<RuleVerdict> EvaluateAsync(ExtractedDocument doc, ProcessContext ctx) {
        foreach (var rule in _rules) {
            var result = await rule.EvaluateAsync(doc, ctx);
            if (result.Verdict != RuleVerdict.AutoProcess) {
                LastReason = result.Reason;
                return result.Verdict;
            }
        }
        return RuleVerdict.AutoProcess;
    }
}
```

Rules fail fast on the first non-AutoProcess verdict. Ordering matters —
put cheap deterministic checks (currency whitelist) before expensive ones
(Odoo lookups). Deterministic beats non-deterministic for audit.

## Main.xaml — the one-line wrapper

Because Portable disables JIT, `Main.xaml` can't contain any expressions.
It's literally just:

```xml
<Activity x:Class="Main" xmlns:ui="http://...">
  <Sequence>
    <ui:InvokeWorkflowFile WorkflowFileName="ProcessInvoiceMain.cs" />
  </Sequence>
</Activity>
```

The `InvokeWorkflowFile` loads the compiled DLL and calls the
`[Workflow] Execute()` method. No arguments — everything flows through the
`ProcessContext` built inside `Execute()`.

## project.json essentials

```json
{
  "main": "Main.xaml",
  "targetFramework": "Portable",
  "projectProfile": 0,
  "requiresUserInteraction": false,
  "entryPoints": [
    {"filePath": "Main.xaml", "uniqueId": "...", "input": [], "output": []}
  ],
  "dependencies": {
    "UiPath.System.Activities": "[25.10.0]",
    "UiPath.Testing.Activities": "[25.10.0]"
  }
}
```

See `uipath-community-cloud-gotchas` §10–§12 for why each of those fields
has the exact value they do.
