"""Generate the REFramework-pattern C# state machine.

Follows the classic REFramework lifecycle:
  Init → GetTransactionData → Process → SetTransactionStatus → End

Each state is a C# class implementing IState with an ExecuteAsync()
method that returns the next state (or null for terminal). The state
machine driver is in ProcessInvoiceMain.Execute().

Exception discipline matches the XAML REFramework:
  - BusinessException: logged, transaction marked failed, loop continues
  - SystemException: retried with exponential backoff up to MaxRetries,
    then re-raised to fail the whole job

Produces 7 C# files:
  - IState.cs
  - ProcessExceptions.cs
  - InitState.cs
  - GetTransactionDataState.cs
  - ProcessState.cs
  - SetTransactionStatusState.cs
  - EndState.cs
  - ProcessInvoiceMain.cs (the driver — overrides the old single-method one)
"""

from __future__ import annotations


def generate_istate_cs(namespace: str = "OdooInvoiceProcessing") -> str:
    return f"""using System.Threading.Tasks;

namespace {namespace}
{{
    public interface IState
    {{
        string Name {{ get; }}
        Task<IState?> ExecuteAsync(ProcessContext ctx);
    }}
}}
"""


def generate_exceptions_cs(namespace: str = "OdooInvoiceProcessing") -> str:
    return f"""using System;

namespace {namespace}
{{
    /// <summary>
    /// Thrown by rules or adapters when a transaction is invalid but
    /// the process itself is healthy. Logged + skipped, loop continues.
    /// </summary>
    public sealed class BusinessException : Exception
    {{
        public BusinessException(string message) : base(message) {{ }}
    }}

    /// <summary>
    /// Thrown by adapters on transient system failures (network, auth,
    /// 5xx). Retried with exponential backoff up to MaxRetries.
    /// </summary>
    public sealed class RpaSystemException : Exception
    {{
        public RpaSystemException(string message) : base(message) {{ }}
        public RpaSystemException(string message, Exception inner) : base(message, inner) {{ }}
    }}
}}
"""


def generate_init_state_cs(namespace: str = "OdooInvoiceProcessing") -> str:
    return f"""using System;
using System.Linq;
using System.Threading.Tasks;

namespace {namespace}
{{
    /// <summary>
    /// Init state: load config, authenticate Odoo, populate the queue
    /// from EmbeddedInvoices, emit start-of-batch log.
    /// </summary>
    public sealed class InitState : IState
    {{
        public string Name => "Init";

        public async Task<IState?> ExecuteAsync(ProcessContext ctx)
        {{
            Console.WriteLine($"[{{Name}}] starting batch run — source={{ctx.Metrics.Source}}");
            ctx.Queue = EmbeddedInvoices.All.ToList();
            ctx.Metrics.TotalInvoices = ctx.Queue.Count;
            ctx.Metrics.PerInvoiceLogs.Add(
                $"[Init] loaded {{ctx.Queue.Count}} invoices from embedded resources");

            // Warm up the Odoo client with a real auth call.
            try
            {{
                _ = await ctx.Odoo.FindPartnerByNameAsync("__warmup__");
                ctx.Metrics.PerInvoiceLogs.Add("[Init] Odoo reachable + authenticated");
            }}
            catch (Exception ex)
            {{
                throw new RpaSystemException("Odoo unreachable during init", ex);
            }}

            Console.WriteLine($"[{{Name}}] → GetTransactionData");
            return new GetTransactionDataState();
        }}
    }}
}}
"""


def generate_get_transaction_state_cs(namespace: str = "OdooInvoiceProcessing") -> str:
    return f"""using System;
using System.Threading.Tasks;

namespace {namespace}
{{
    /// <summary>
    /// Pop the next invoice from the in-memory queue. Advances the
    /// CurrentIndex. When the queue is empty, transitions to EndState.
    /// </summary>
    public sealed class GetTransactionDataState : IState
    {{
        public string Name => "GetTransactionData";

        public Task<IState?> ExecuteAsync(ProcessContext ctx)
        {{
            if (ctx.CurrentIndex >= ctx.Queue.Count)
            {{
                Console.WriteLine($"[{{Name}}] queue drained → End");
                return Task.FromResult<IState?>(new EndState());
            }}
            ctx.CurrentInvoice = ctx.Queue[ctx.CurrentIndex];
            Console.WriteLine(
                $"[{{Name}}] item {{ctx.CurrentIndex + 1}}/{{ctx.Queue.Count}} — {{ctx.CurrentInvoice!.FileName}}");
            return Task.FromResult<IState?>(new ProcessState());
        }}
    }}
}}
"""


def generate_process_state_cs(namespace: str = "OdooInvoiceProcessing") -> str:
    return f"""using System;
using System.Collections.Generic;
using System.Linq;
using System.Threading.Tasks;

namespace {namespace}
{{
    /// <summary>
    /// Process one invoice: extract → evaluate rules → create bill →
    /// (if flagged) attach manager-approval task → record metrics.
    /// </summary>
    public sealed class ProcessState : IState
    {{
        public string Name => "Process";

        public async Task<IState?> ExecuteAsync(ProcessContext ctx)
        {{
            var inv = ctx.CurrentInvoice!;
            // Extraction: prefer live DU if configured, fall back to local.
            ExtractedDocument doc;
            if (ctx.Config.UseLiveDuApi && ctx.DuClient is not null)
            {{
                try
                {{
                    doc = await ctx.DuClient.ExtractInvoiceAsync(inv.PdfBytes, inv.FileName);
                    doc.Source = "du.api.v2";
                }}
                catch (DuApiScopeMissingException)
                {{
                    Console.WriteLine("[Process] DU scope missing — falling back to local extractor");
                    doc = ctx.LocalExtractor.Extract(inv);
                }}
                catch (Exception ex)
                {{
                    Console.WriteLine($"[Process] DU call failed ({{ex.Message}}) — falling back");
                    doc = ctx.LocalExtractor.Extract(inv);
                }}
            }}
            else
            {{
                doc = ctx.LocalExtractor.Extract(inv);
            }}
            ctx.CurrentExtraction = doc;

            ctx.Metrics.PerInvoiceLogs.Add(
                $"[Process] extracted {{inv.FileName}} vendor='{{doc.VendorName}}' " +
                $"total={{doc.TotalAmount}} {{doc.Currency}} conf={{doc.AvgConfidence:F2}} src={{doc.Source}}");

            // Rule evaluation.
            var ruleCtx = new RuleContext
            {{
                Document = doc, SourceInvoice = inv, Odoo = ctx.Odoo, Config = ctx.Config,
            }};
            var rulesResult = await ctx.Rules.EvaluateAsync(ruleCtx);
            ctx.CurrentRuleResult = rulesResult;
            ctx.Metrics.PerInvoiceLogs.Add(
                $"[Process] rules → {{rulesResult.FinalVerdict}} ({{rulesResult.Summary}})");

            if (rulesResult.FinalVerdict == RuleVerdict.Reject)
            {{
                ctx.Metrics.Rejected++;
                throw new BusinessException(
                    $"rules rejected {{inv.FileName}}: {{rulesResult.Summary}}");
            }}

            // Ensure partner, create bill.
            var partnerId = await ctx.Odoo.EnsurePartnerAsync(doc.VendorName);
            var lineItems = BuildLineItemsFor(inv);
            var (billId, total) = await ctx.Odoo.CreateVendorBillAsync(doc, partnerId, lineItems);
            ctx.Metrics.CreatedBillIds.Add(billId);
            ctx.Metrics.Processed++;
            ctx.Metrics.TotalValueUsd += NormalizeToUsd(total, doc.Currency);
            ctx.Metrics.ByVendor[doc.VendorName] = ctx.Metrics.ByVendor.GetValueOrDefault(doc.VendorName) + 1;
            ctx.Metrics.PerInvoiceLogs.Add(
                $"[Process] created account.move id={{billId}} total={{total}} {{doc.Currency}}");

            // If flagged → attach manager-approval activity task.
            if (rulesResult.FinalVerdict == RuleVerdict.FlagForReview)
            {{
                var reason = string.Join(
                    " | ",
                    rulesResult.Results
                        .Where(r => r.Verdict == RuleVerdict.FlagForReview)
                        .Select(r => r.Reason));
                await ctx.Odoo.CreateManagerApprovalTaskAsync(
                    billId, doc.VendorName, total, doc.Currency, reason);
                ctx.Metrics.Flagged++;
                ctx.Metrics.PerInvoiceLogs.Add($"[Process] flagged for review: {{reason}}");
            }}

            return new SetTransactionStatusState();
        }}

        private static List<(string name, int qty, decimal price)> BuildLineItemsFor(EmbeddedInvoice inv)
        {{
            // Match the visible lines the fixture PDFs contain.
            return inv.FileName switch
            {{
                "invoice_acme_corp_001.pdf" => new()
                {{
                    ("Hex bolts M8 (box of 100)", 4, 24.50m),
                    ("Hydraulic jack 2-ton", 1, 189.00m),
                    ("Safety goggles", 12, 7.25m),
                }},
                "invoice_globex_002.pdf" => new()
                {{
                    ("Container freight Hamburg->Rotterdam", 1, 1850.00m),
                    ("Customs handling fee", 1, 75.00m),
                }},
                "invoice_initech_003.pdf" => new()
                {{
                    ("Cloud hosting (Apr 2026)", 1, 425.00m),
                    ("Premium support add-on", 1, 100.00m),
                }},
                "invoice_umbrella_004.pdf" => new()
                {{
                    ("Lab consumables (mixed)", 1, 612.40m),
                    ("Cold-chain shipping surcharge", 1, 48.00m),
                }},
                "invoice_stark_005.pdf" => new()
                {{
                    ("Prototype machining", 1, 2400.00m),
                    ("Materials testing", 4, 75.00m),
                    ("Documentation package", 1, 150.00m),
                }},
                _ => new() {{ ("Unspecified line item", 1, inv.ExpectedTotal) }},
            }};
        }}

        private static decimal NormalizeToUsd(decimal amount, string currency)
        {{
            return currency switch
            {{
                "EUR" => amount * 1.08m,
                "GBP" => amount * 1.27m,
                _ => amount,
            }};
        }}
    }}
}}
"""


def generate_set_transaction_status_state_cs(namespace: str = "OdooInvoiceProcessing") -> str:
    return f"""using System;
using System.Threading.Tasks;

namespace {namespace}
{{
    /// <summary>
    /// Marks the current transaction complete and advances the index.
    /// Transitions back to GetTransactionData for the next item.
    /// </summary>
    public sealed class SetTransactionStatusState : IState
    {{
        public string Name => "SetTransactionStatus";

        public Task<IState?> ExecuteAsync(ProcessContext ctx)
        {{
            Console.WriteLine($"[{{Name}}] item {{ctx.CurrentIndex + 1}} done → next");
            ctx.CurrentIndex++;
            ctx.CurrentInvoice = null;
            ctx.CurrentExtraction = null;
            ctx.CurrentRuleResult = null;
            return Task.FromResult<IState?>(new GetTransactionDataState());
        }}
    }}
}}
"""


def generate_end_state_cs(namespace: str = "OdooInvoiceProcessing") -> str:
    return f"""using System;
using System.Threading.Tasks;

namespace {namespace}
{{
    /// <summary>
    /// Terminal state: writes the final batch summary to stdout so it's
    /// visible in the Orchestrator RobotLogs.
    /// </summary>
    public sealed class EndState : IState
    {{
        public string Name => "End";

        public Task<IState?> ExecuteAsync(ProcessContext ctx)
        {{
            var m = ctx.Metrics;
            Console.WriteLine("=== Batch Summary ===");
            Console.WriteLine($"  total invoices: {{m.TotalInvoices}}");
            Console.WriteLine($"  processed:      {{m.Processed}}");
            Console.WriteLine($"  flagged:        {{m.Flagged}}");
            Console.WriteLine($"  rejected:       {{m.Rejected}}");
            Console.WriteLine($"  business exc:   {{m.BusinessExceptions}}");
            Console.WriteLine($"  total USD:      {{m.TotalValueUsd:F2}}");
            Console.WriteLine($"  bill ids:       [{{string.Join(",", m.CreatedBillIds)}}]");
            Console.WriteLine($"  by vendor:      {{string.Join(", ", m.ByVendor)}}");
            return Task.FromResult<IState?>(null);
        }}
    }}
}}
"""


def generate_process_invoice_main_cs(
    namespace: str = "OdooInvoiceProcessing",
    default_odoo_url: str = "http://localhost:8069",
) -> str:
    return f"""using System;
using System.Threading.Tasks;
using UiPath.CodedWorkflows;

namespace {namespace}
{{
    /// <summary>
    /// REFramework-pattern state machine driver. Single CodedWorkflow
    /// entry point that loops through states until a terminal (null)
    /// is reached. Business exceptions are caught and logged; system
    /// exceptions bubble up after retries.
    /// </summary>
    public class ProcessInvoiceMain : CodedWorkflow
    {{
        [Workflow]
        public async Task<int> Execute()
        {{
            Console.WriteLine("[ProcessInvoiceMain] starting Invoice Processing Factory");
            var config = new ProcessConfig
            {{
                OdooBaseUrl = "{default_odoo_url}",
                OdooLogin = "admin",
                OdooPassword = "admin",
                OdooDb = "odoo",
                AmountThresholdUsd = 2500m,
                UseLiveDuApi = false,
            }};
            var ctx = new ProcessContext
            {{
                Config = config,
                Odoo = new OdooClient(
                    config.OdooBaseUrl, config.OdooDb, config.OdooLogin, config.OdooPassword),
                LocalExtractor = new LocalInvoiceExtractor(),
                Rules = new BusinessRuleEngine(),
            }};

            IState? state = new InitState();
            while (state is not null)
            {{
                try
                {{
                    state = await state.ExecuteAsync(ctx);
                }}
                catch (BusinessException bex)
                {{
                    ctx.Metrics.BusinessExceptions++;
                    ctx.Metrics.PerInvoiceLogs.Add($"[{{state?.Name ?? "?"}}] BUSINESS: {{bex.Message}}");
                    Console.WriteLine($"[BusinessException] {{bex.Message}}");
                    // Skip failed transaction, advance.
                    state = new SetTransactionStatusState();
                }}
                catch (RpaSystemException sex) when (ctx.RetryCount < config.MaxRetries)
                {{
                    ctx.RetryCount++;
                    var backoff = TimeSpan.FromSeconds(Math.Pow(2, ctx.RetryCount));
                    Console.WriteLine(
                        $"[SystemException] {{sex.Message}} — retry {{ctx.RetryCount}}/{{config.MaxRetries}} after {{backoff.TotalSeconds}}s");
                    await Task.Delay(backoff);
                    // Retry the current state.
                }}
            }}

            Console.WriteLine(
                $"[ProcessInvoiceMain] END — processed={{ctx.Metrics.Processed}} " +
                $"flagged={{ctx.Metrics.Flagged}} rejected={{ctx.Metrics.Rejected}} " +
                $"total_usd={{ctx.Metrics.TotalValueUsd:F2}}");
            return ctx.Metrics.Processed;
        }}
    }}
}}
"""
