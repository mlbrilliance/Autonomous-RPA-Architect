"""Generate the C# business rule engine (IRule, 4 rules, chain evaluator).

The rules run against an ``ExtractedDocument`` (output of
DocumentUnderstandingClient / LocalInvoiceExtractor) and can consult
the ``OdooClient`` for stateful checks like duplicate detection.

Rules:
  1. DuplicateInvoiceRule   — queries Odoo account.move.search_count
  2. AmountThresholdRule    — flags totals above configured limit
  3. CurrencyWhitelistRule  — rejects unsupported currencies
  4. VendorKycRule          — flags new vendors for KYC (still processes)

The chain evaluator runs every rule, collects results, and returns a
final verdict (AutoProcess, FlagForReview, Reject) plus a list of
human-readable reasons. All verdicts are logged with the rule that
produced them.
"""

from __future__ import annotations


def generate_rules_engine_cs(namespace: str = "OdooInvoiceProcessing") -> str:
    return f"""using System;
using System.Collections.Generic;
using System.Linq;
using System.Threading.Tasks;

namespace {namespace}
{{
    public enum RuleVerdict
    {{
        AutoProcess,
        FlagForReview,
        Reject,
    }}

    public sealed class RuleResult
    {{
        public string RuleName {{ get; set; }} = "";
        public RuleVerdict Verdict {{ get; set; }}
        public string Reason {{ get; set; }} = "";

        public static RuleResult Pass(string rule) => new() {{ RuleName = rule, Verdict = RuleVerdict.AutoProcess, Reason = "pass" }};
        public static RuleResult Flag(string rule, string reason) => new() {{ RuleName = rule, Verdict = RuleVerdict.FlagForReview, Reason = reason }};
        public static RuleResult Reject(string rule, string reason) => new() {{ RuleName = rule, Verdict = RuleVerdict.Reject, Reason = reason }};
    }}

    public sealed class RuleContext
    {{
        public ExtractedDocument Document {{ get; set; }} = new();
        public EmbeddedInvoice SourceInvoice {{ get; set; }} = null!;
        public OdooClient Odoo {{ get; set; }} = null!;
        public ProcessConfig Config {{ get; set; }} = null!;
    }}

    public interface IRule
    {{
        string Name {{ get; }}
        Task<RuleResult> EvaluateAsync(RuleContext ctx);
    }}

    public sealed class DuplicateInvoiceRule : IRule
    {{
        public string Name => "DuplicateInvoiceRule";
        public async Task<RuleResult> EvaluateAsync(RuleContext ctx)
        {{
            // Look up existing account.move by ref + partner.
            var count = await ctx.Odoo.CountExistingBillsAsync(
                ctx.Document.InvoiceNumber, ctx.Document.VendorName);
            if (count > 0)
                return RuleResult.Reject(Name, $"duplicate invoice: ref={{ctx.Document.InvoiceNumber}} count={{count}}");
            return RuleResult.Pass(Name);
        }}
    }}

    public sealed class AmountThresholdRule : IRule
    {{
        public string Name => "AmountThresholdRule";
        public Task<RuleResult> EvaluateAsync(RuleContext ctx)
        {{
            var normalizedUsd = NormalizeToUsd(ctx.Document.TotalAmount, ctx.Document.Currency);
            if (normalizedUsd > ctx.Config.AmountThresholdUsd)
                return Task.FromResult(RuleResult.Flag(Name,
                    $"amount {{normalizedUsd:F2}} USD exceeds threshold {{ctx.Config.AmountThresholdUsd:F2}} — manager approval required"));
            return Task.FromResult(RuleResult.Pass(Name));
        }}

        private static decimal NormalizeToUsd(decimal amount, string currency)
        {{
            // Fixed demo rates; in production this would hit an FX API.
            return currency switch
            {{
                "EUR" => amount * 1.08m,
                "GBP" => amount * 1.27m,
                _ => amount,
            }};
        }}
    }}

    public sealed class CurrencyWhitelistRule : IRule
    {{
        public string Name => "CurrencyWhitelistRule";
        public Task<RuleResult> EvaluateAsync(RuleContext ctx)
        {{
            if (ctx.Config.AllowedCurrencies.Contains(ctx.Document.Currency))
                return Task.FromResult(RuleResult.Pass(Name));
            return Task.FromResult(RuleResult.Reject(Name,
                $"currency {{ctx.Document.Currency}} not in allowed set [{{string.Join(",", ctx.Config.AllowedCurrencies)}}]"));
        }}
    }}

    public sealed class VendorKycRule : IRule
    {{
        public string Name => "VendorKycRule";
        public async Task<RuleResult> EvaluateAsync(RuleContext ctx)
        {{
            var existing = await ctx.Odoo.FindPartnerByNameAsync(ctx.Document.VendorName);
            if (existing <= 0)
            {{
                // New vendor — still process but flag for KYC.
                return RuleResult.Flag(Name,
                    $"new vendor '{{ctx.Document.VendorName}}' — KYC check required");
            }}
            return RuleResult.Pass(Name);
        }}
    }}

    public sealed class RuleChainResult
    {{
        public RuleVerdict FinalVerdict {{ get; set; }}
        public List<RuleResult> Results {{ get; set; }} = new();
        public string Summary => string.Join("; ", Results.Select(r => $"{{r.RuleName}}={{r.Verdict}}"));
    }}

    public sealed class BusinessRuleEngine
    {{
        private readonly List<IRule> _rules;

        public BusinessRuleEngine(IEnumerable<IRule>? rules = null)
        {{
            _rules = rules?.ToList() ?? new List<IRule>
            {{
                new CurrencyWhitelistRule(),
                new DuplicateInvoiceRule(),
                new VendorKycRule(),
                new AmountThresholdRule(),
            }};
        }}

        public async Task<RuleChainResult> EvaluateAsync(RuleContext ctx)
        {{
            var chainResult = new RuleChainResult();
            // Default verdict is AutoProcess; a single Reject stops it,
            // any FlagForReview downgrades without stopping.
            var finalVerdict = RuleVerdict.AutoProcess;
            foreach (var rule in _rules)
            {{
                RuleResult result;
                try
                {{
                    result = await rule.EvaluateAsync(ctx);
                }}
                catch (Exception ex)
                {{
                    result = RuleResult.Flag(rule.Name, $"rule error: {{ex.Message}}");
                }}
                chainResult.Results.Add(result);
                if (result.Verdict == RuleVerdict.Reject)
                {{
                    finalVerdict = RuleVerdict.Reject;
                    break;  // stop on reject
                }}
                if (result.Verdict == RuleVerdict.FlagForReview &&
                    finalVerdict == RuleVerdict.AutoProcess)
                {{
                    finalVerdict = RuleVerdict.FlagForReview;
                }}
            }}
            chainResult.FinalVerdict = finalVerdict;
            return chainResult;
        }}
    }}
}}
"""
