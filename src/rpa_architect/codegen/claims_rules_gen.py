"""C# generator for the medical-claims rule engine.

Emits ClaimsRules.cs containing:
  - IClaimRule interface
  - RuleResult record (Verdict + Reason)
  - 5 rule classes in cheap→expensive order
  - ClaimsRuleEngine that walks them, short-circuits on Deny, and
    accumulates FlagForReview reasons
"""

from __future__ import annotations

DEFAULT_NAMESPACE = "MedicalClaimsProcessing"


def generate_claims_rules_cs(namespace: str = DEFAULT_NAMESPACE) -> str:
    """Emit ClaimsRules.cs for the given namespace."""
    return f"""using System;
using System.Collections.Generic;
using System.Linq;
using System.Threading.Tasks;

namespace {namespace}
{{
    /// <summary>
    /// A single adjudication rule. Rules are stateless and may hit SuiteCRM
    /// for live data — they must throw <see cref="RpaSystemException"/> on
    /// infrastructure failure so the state machine retries them.
    /// </summary>
    public interface IClaimRule
    {{
        string Name {{ get; }}
        Task<RuleResult> EvaluateAsync(Case claim, ClaimsProcessContext ctx);
    }}

    /// <summary>A rule's verdict for a single claim.</summary>
    public class RuleResult
    {{
        public ClaimVerdict Verdict {{ get; set; }}
        public string Reason {{ get; set; }} = string.Empty;

        public static RuleResult Pass() =>
            new() {{ Verdict = ClaimVerdict.AutoApprove, Reason = "" }};

        public static RuleResult Flag(string reason) =>
            new() {{ Verdict = ClaimVerdict.FlagForReview, Reason = reason }};

        public static RuleResult DenyResult(string reason) =>
            new() {{ Verdict = ClaimVerdict.Deny, Reason = reason }};
    }}

    // ================================================================
    // Rule 1 — CoverageVerificationRule (cheap, in-memory)
    // ================================================================

    /// <summary>
    /// Uses the pre-fetched <see cref="ClaimsProcessContext.CurrentPolicy"/>
    /// to check whether the claim's submission date falls within the policy
    /// coverage window. No SuiteCRM round-trip — the policy is loaded once
    /// per transaction by the Performer's GetTransactionDataState.
    /// </summary>
    public class CoverageVerificationRule : IClaimRule
    {{
        public string Name => "CoverageVerification";

        public Task<RuleResult> EvaluateAsync(Case claim, ClaimsProcessContext ctx)
        {{
            if (ctx.CurrentPolicy == null)
                return Task.FromResult(RuleResult.DenyResult(
                    $"no policy loaded for {{claim.PolicyNumber}}"));

            if (!ctx.CurrentPolicy.IsActiveOn(claim.SubmittedAt))
                return Task.FromResult(RuleResult.DenyResult(
                    $"policy {{claim.PolicyNumber}} not active on {{claim.SubmittedAt:yyyy-MM-dd}} "
                    + $"(coverage {{ctx.CurrentPolicy.CoverageStart:yyyy-MM-dd}} "
                    + $"to {{ctx.CurrentPolicy.CoverageEnd:yyyy-MM-dd}})"));

            return Task.FromResult(RuleResult.Pass());
        }}
    }}

    // ================================================================
    // Rule 2 — AmountThresholdRule (cheap, in-memory)
    // ================================================================

    public class AmountThresholdRule : IClaimRule
    {{
        public string Name => "AmountThreshold";

        private const decimal ReviewThreshold = 10000m;  // $10,000 flags for review
        private const decimal HardCap = 100000m;         // $100,000 hard deny

        public Task<RuleResult> EvaluateAsync(Case claim, ClaimsProcessContext ctx)
        {{
            if (claim.TotalAmount > HardCap)
                return Task.FromResult(RuleResult.DenyResult(
                    $"amount ${{claim.TotalAmount:F2}} exceeds hard cap ${{HardCap:F0}}"));

            if (claim.TotalAmount > ReviewThreshold)
                return Task.FromResult(RuleResult.Flag(
                    $"amount ${{claim.TotalAmount:F2}} exceeds review threshold ${{ReviewThreshold:F0}}"));

            return Task.FromResult(RuleResult.Pass());
        }}
    }}

    // ================================================================
    // Rule 3 — DocumentationCompletenessRule (live SuiteCRM)
    // ================================================================

    /// <summary>
    /// Counts attached Notes (SuiteCRM document substitute — BW-07) and
    /// denies if insufficient documentation is present for high-complexity
    /// procedure codes (CPT E&M level 3+ starts with "992" and needs ≥2
    /// supporting documents).
    /// </summary>
    public class DocumentationCompletenessRule : IClaimRule
    {{
        public string Name => "DocumentationCompleteness";

        public async Task<RuleResult> EvaluateAsync(Case claim, ClaimsProcessContext ctx)
        {{
            if (string.IsNullOrEmpty(claim.SuiteCrmId))
                return RuleResult.Pass();  // skip when we can't look it up

            var notes = await ctx.SuiteCrm.GetCaseNotesAsync(claim.SuiteCrmId);
            int required = claim.ProcedureCode.StartsWith("992") ? 2 : 1;

            if (notes.Count < required)
                return RuleResult.DenyResult(
                    $"procedure {{claim.ProcedureCode}} requires {{required}} doc(s), "
                    + $"found {{notes.Count}}");

            return RuleResult.Pass();
        }}
    }}

    // ================================================================
    // Rule 4 — NetworkProviderRule (live SuiteCRM)
    // ================================================================

    public class NetworkProviderRule : IClaimRule
    {{
        public string Name => "NetworkProvider";

        public async Task<RuleResult> EvaluateAsync(Case claim, ClaimsProcessContext ctx)
        {{
            if (string.IsNullOrEmpty(claim.ProviderNpi))
                return RuleResult.Flag("no provider npi on claim");

            try
            {{
                var provider = await ctx.SuiteCrm.GetProviderByNpiAsync(claim.ProviderNpi);
                if (!provider.InNetwork)
                    return RuleResult.Flag(
                        $"provider {{provider.Name}} (npi={{provider.Npi}}) is out-of-network");
                return RuleResult.Pass();
            }}
            catch (BusinessException)
            {{
                return RuleResult.Flag($"unknown provider npi={{claim.ProviderNpi}}");
            }}
        }}
    }}

    // ================================================================
    // Rule 5 — FraudVelocityRule (live SuiteCRM, most expensive)
    // ================================================================

    /// <summary>
    /// Velocity-based fraud detection. Queries SuiteCRM for recent cases
    /// from the same claimant. ≥4 prior cases in 30 days → Deny. 2-3 prior
    /// cases → FlagForReview. Fewer → pass.
    /// </summary>
    public class FraudVelocityRule : IClaimRule
    {{
        public string Name => "FraudVelocity";

        private const int DenyThreshold = 4;
        private const int FlagThreshold = 2;
        private const int WindowDays = 30;

        public async Task<RuleResult> EvaluateAsync(Case claim, ClaimsProcessContext ctx)
        {{
            var recent = await ctx.SuiteCrm.ListRecentCasesByClaimantAsync(
                claim.ClaimantName, WindowDays);

            // Don't count the case we're currently adjudicating.
            var priorCount = recent.Count(c => c.ClaimId != claim.ClaimId);

            if (priorCount >= DenyThreshold)
                return RuleResult.DenyResult(
                    $"{{priorCount}} prior claims from {{claim.ClaimantName}} in {{WindowDays}}d "
                    + $"— fraud velocity threshold exceeded");

            if (priorCount >= FlagThreshold)
                return RuleResult.Flag(
                    $"{{priorCount}} prior claims from {{claim.ClaimantName}} in {{WindowDays}}d "
                    + $"— velocity review");

            return RuleResult.Pass();
        }}
    }}

    // ================================================================
    // ClaimsRuleEngine — walks the rule chain
    // ================================================================

    /// <summary>
    /// Evaluates each rule in order. Short-circuits on the first Deny
    /// verdict (no point running more rules if the claim is already
    /// rejected). FlagForReview reasons accumulate into <see
    /// cref="ClaimsProcessContext.FlagReasons"/> so the final verdict can
    /// include every reviewer-relevant note.
    /// </summary>
    public class ClaimsRuleEngine
    {{
        private readonly IReadOnlyList<IClaimRule> _rules;

        public ClaimsRuleEngine()
        {{
            // Ordered cheap → expensive. Deterministic rules first so a
            // hard Deny short-circuits before we hit SuiteCRM.
            _rules = new List<IClaimRule>
            {{
                new CoverageVerificationRule(),
                new AmountThresholdRule(),
                new DocumentationCompletenessRule(),
                new NetworkProviderRule(),
                new FraudVelocityRule(),
            }};
        }}

        /// <summary>Last rule that produced a non-pass verdict (for logging).</summary>
        public string LastRuleFired {{ get; private set; }} = string.Empty;

        public async Task<ClaimVerdict> EvaluateAsync(Case claim, ClaimsProcessContext ctx)
        {{
            ctx.FlagReasons.Clear();
            LastRuleFired = "";

            foreach (var rule in _rules)
            {{
                var result = await rule.EvaluateAsync(claim, ctx);

                if (result.Verdict == ClaimVerdict.Deny)
                {{
                    LastRuleFired = rule.Name;
                    ctx.FlagReasons.Add($"[{{rule.Name}}] {{result.Reason}}");
                    return ClaimVerdict.Deny;
                }}

                if (result.Verdict == ClaimVerdict.FlagForReview)
                {{
                    LastRuleFired = rule.Name;
                    ctx.FlagReasons.Add($"[{{rule.Name}}] {{result.Reason}}");
                    // Don't short-circuit — keep evaluating so we capture
                    // every reviewer-relevant reason.
                }}
            }}

            return ctx.FlagReasons.Count > 0
                ? ClaimVerdict.FlagForReview
                : ClaimVerdict.AutoApprove;
        }}
    }}
}}
"""
