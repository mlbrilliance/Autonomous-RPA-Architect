"""C# domain model generators for the medical claims adjudication factory.

Emits six source files used by all three processes (Dispatcher, Performer,
Reporter). Each process gets byte-identical copies of these files at
assembly time — there is no shared .NET class library because
UiPath Community Cloud's NuGet feed doesn't resolve cross-package references
at runtime (silently strips them during ``uipcli pack``).

Files produced:
  Case.cs                    — the claim record
  Policy.cs                  — insurance policy + IsActiveOn helper
  Provider.cs                — medical provider + InNetwork flag
  ClaimVerdict.cs            — enum of 4 possible adjudication outcomes
  ClaimMetrics.cs            — per-run counters
  ClaimsProcessContext.cs    — state machine context shared across transitions
"""

from __future__ import annotations

DEFAULT_NAMESPACE = "MedicalClaimsProcessing"


def generate_case_cs(namespace: str = DEFAULT_NAMESPACE) -> str:
    """Emit Case.cs — the medical claim record."""
    return f"""using System;
using System.Collections.Generic;

namespace {namespace}
{{
    /// <summary>
    /// A medical insurance claim record as stored in SuiteCRM's Cases module.
    /// Populated from the <c>description</c> field on fetch (we embed the
    /// structured metadata there because SuiteCRM Community doesn't expose
    /// custom fields on a free tenant).
    /// </summary>
    public class Case
    {{
        public string ClaimId {{ get; set; }} = string.Empty;
        public string PolicyNumber {{ get; set; }} = string.Empty;
        public string ClaimantName {{ get; set; }} = string.Empty;
        public string DiagnosisCode {{ get; set; }} = string.Empty;
        public string ProcedureCode {{ get; set; }} = string.Empty;
        public decimal TotalAmount {{ get; set; }}
        public string Currency {{ get; set; }} = "USD";
        public DateTime SubmittedAt {{ get; set; }}
        public string ProviderNpi {{ get; set; }} = string.Empty;
        public List<string> DocumentUrls {{ get; set; }} = new();
        public string Status {{ get; set; }} = "New";
        public ClaimVerdict Verdict {{ get; set; }} = ClaimVerdict.Pending;

        /// <summary>The SuiteCRM entity id — populated after fetch/create.</summary>
        public string? SuiteCrmId {{ get; set; }}
    }}
}}
"""


def generate_policy_cs(namespace: str = DEFAULT_NAMESPACE) -> str:
    """Emit Policy.cs with IsActiveOn helper used by CoverageVerificationRule."""
    return f"""using System;
using System.Collections.Generic;

namespace {namespace}
{{
    /// <summary>
    /// An insurance policy. Stored as a SuiteCRM Account with
    /// <c>account_type = "Policy"</c>. The Performer pre-fetches the policy
    /// during dispatch to keep the hot-path rule (<see cref="IsActiveOn"/>)
    /// local — no SuiteCRM round-trip at adjudication time.
    /// </summary>
    public class Policy
    {{
        public string PolicyNumber {{ get; set; }} = string.Empty;
        public string Holder {{ get; set; }} = string.Empty;
        public DateTime CoverageStart {{ get; set; }}
        public DateTime CoverageEnd {{ get; set; }}
        public decimal DeductibleRemaining {{ get; set; }}
        public decimal OutOfPocketMax {{ get; set; }}
        public List<string> NetworkProviderIds {{ get; set; }} = new();

        /// <summary>
        /// Deterministic coverage check — returns true iff <paramref name="at"/>
        /// is within [CoverageStart, CoverageEnd] inclusive.
        /// </summary>
        public bool IsActiveOn(DateTime at)
        {{
            return at >= CoverageStart && at <= CoverageEnd;
        }}
    }}
}}
"""


def generate_provider_cs(namespace: str = DEFAULT_NAMESPACE) -> str:
    """Emit Provider.cs — medical provider with NPI + in-network flag."""
    return f"""using System;

namespace {namespace}
{{
    /// <summary>
    /// A medical provider, identified by NPI (National Provider Identifier).
    /// Stored as a SuiteCRM Account with <c>account_type = "Provider"</c>.
    /// </summary>
    public class Provider
    {{
        public string Npi {{ get; set; }} = string.Empty;
        public string Name {{ get; set; }} = string.Empty;
        public bool InNetwork {{ get; set; }}
        public string SpecialtyCode {{ get; set; }} = string.Empty;
    }}
}}
"""


def generate_claim_verdict_cs(namespace: str = DEFAULT_NAMESPACE) -> str:
    """Emit the ClaimVerdict enum. Four states matching the rule engine."""
    return f"""namespace {namespace}
{{
    /// <summary>
    /// Possible adjudication outcomes. The rule engine short-circuits on
    /// <see cref="Deny"/> and accumulates <see cref="FlagForReview"/>
    /// reasons across multiple rules before returning.
    /// </summary>
    public enum ClaimVerdict
    {{
        /// <summary>Claim has not yet been adjudicated.</summary>
        Pending = 0,

        /// <summary>All rules passed — auto-approve for payment.</summary>
        AutoApprove = 1,

        /// <summary>One or more rules raised a soft flag — route to a human.</summary>
        FlagForReview = 2,

        /// <summary>A rule deterministically rejected — no payment, no review.</summary>
        Deny = 3,
    }}
}}
"""


def generate_claim_metrics_cs(namespace: str = DEFAULT_NAMESPACE) -> str:
    """Emit ClaimMetrics.cs — per-run counters for the batch summary."""
    return f"""using System;
using System.Collections.Generic;

namespace {namespace}
{{
    /// <summary>
    /// Mutable per-run aggregate. Each Performer invocation starts with a
    /// fresh instance and emits the final state from <c>EndState</c> into the
    /// robot's stdout — the Reporter aggregates these across runs to build
    /// the SLA HTML report.
    /// </summary>
    public class ClaimMetrics
    {{
        public int Processed {{ get; set; }}
        public int AutoApproved {{ get; set; }}
        public int Flagged {{ get; set; }}
        public int Denied {{ get; set; }}
        public int BusinessFailures {{ get; set; }}
        public int SystemFailures {{ get; set; }}
        public Dictionary<string, int> VerdictByClaimant {{ get; set; }} = new();
        public DateTime StartedAt {{ get; set; }} = DateTime.UtcNow;
        public DateTime? EndedAt {{ get; set; }}

        public void RecordVerdict(ClaimVerdict verdict, string claimant)
        {{
            Processed++;
            switch (verdict)
            {{
                case ClaimVerdict.AutoApprove: AutoApproved++; break;
                case ClaimVerdict.FlagForReview: Flagged++; break;
                case ClaimVerdict.Deny: Denied++; break;
            }}
            var key = $"{{claimant}}|{{verdict}}";
            VerdictByClaimant[key] = VerdictByClaimant.TryGetValue(key, out var n) ? n + 1 : 1;
        }}

        public override string ToString()
        {{
            var dur = (EndedAt ?? DateTime.UtcNow) - StartedAt;
            return $"processed={{Processed}} auto={{AutoApproved}} flagged={{Flagged}} "
                 + $"denied={{Denied}} biz_fail={{BusinessFailures}} sys_fail={{SystemFailures}} "
                 + $"duration={{dur.TotalSeconds:F1}}s";
        }}
    }}
}}
"""


def generate_claims_process_context_cs(namespace: str = DEFAULT_NAMESPACE) -> str:
    """Emit ClaimsProcessContext.cs — shared state across state-machine transitions."""
    return f"""using System.Collections.Generic;

namespace {namespace}
{{
    // Forward declarations — the real implementations live in
    // UiPathQueueClient.cs (Dispatcher) and PerformerQueueClient.cs
    // (Performer). We declare empty marker classes here so the context
    // compiles standalone; the real definitions override these via
    // C#'s single-class rule (last-defined wins within a namespace).
    public partial class UiPathQueueClient {{ }}
    public partial class PerformerQueueClient {{ }}

    /// <summary>
    /// Mutable state passed between <c>IState.ExecuteAsync</c> calls in the
    /// Performer state machine. Replaces v0.5's <c>ProcessContext</c> which
    /// is hard-wired to OdooClient + invoice fields.
    /// </summary>
    public class ClaimsProcessContext
    {{
        public SuiteCrmClient SuiteCrm {{ get; set; }} = null!;
        public ClaimsRuleEngine Rules {{ get; set; }} = null!;
        public UiPathQueueClient? UiPathQueue {{ get; set; }}
        public PerformerQueueClient? PerformerQueue {{ get; set; }}
        public ClaimMetrics Metrics {{ get; set; }} = new();

        /// <summary>The case currently being processed — refreshed each transition.</summary>
        public Case? CurrentCase {{ get; set; }}

        /// <summary>Pre-fetched policy for <see cref="CurrentCase"/>.</summary>
        public Policy? CurrentPolicy {{ get; set; }}

        /// <summary>The leased Orchestrator queue transaction id.</summary>
        public string? CurrentTransactionId {{ get; set; }}

        /// <summary>Accumulated review reasons when verdict=FlagForReview.</summary>
        public List<string> FlagReasons {{ get; set; }} = new();

        /// <summary>Retry counter for RpaSystemException handling.</summary>
        public int RetryCount {{ get; set; }}
    }}
}}
"""
