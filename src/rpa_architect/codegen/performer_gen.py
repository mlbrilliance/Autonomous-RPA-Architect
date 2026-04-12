"""C# generator for the Performer UiPath process.

The Performer is the queue-consuming analog to v0.5's ProcessInvoiceMain.
Flow per invocation:

  1. InitState          — connect to SuiteCRM + PerformerQueueClient
  2. GetTransactionData — StartTransaction, decode payload or re-fetch
  3. ProcessState       — 5-rule adjudication, write verdict + note back
  4. SetTransactionStatus — SetTransactionResult(Successful / BusinessFail)
  5. back to GetTransactionData (loop) until queue drained
  6. EndState           — emit summary

Business vs System discipline mirrors v0.5: BusinessException skips the
item with a SetTransactionResult(IsSuccessful=false, ...);
RpaSystemException propagates to the outer retry loop in PerformerMain.
"""

from __future__ import annotations

DEFAULT_NAMESPACE = "MedicalClaimsProcessing"


def generate_performer_queue_client_cs(namespace: str = DEFAULT_NAMESPACE) -> str:
    """Emit PerformerQueueClient.cs — C# client for queue transaction ops.

    Declared partial to coexist with the forward decl in
    ClaimsProcessContext.cs.
    """
    return f"""using System;
using System.Collections.Generic;
using System.Net;
using System.Net.Http;
using System.Net.Http.Headers;
using System.Text;
using System.Text.Json;
using System.Threading.Tasks;

namespace {namespace}
{{
    /// <summary>
    /// Leased queue item as returned by StartTransaction.
    /// </summary>
    public class LeasedQueueItem
    {{
        public string Id {{ get; set; }} = string.Empty;
        public string Reference {{ get; set; }} = string.Empty;
        public Dictionary<string, object> SpecificContent {{ get; set; }} = new();
    }}

    /// <summary>
    /// Performer-side Orchestrator client. Leases items via
    /// <c>UiPathODataSvc.StartTransaction</c> and finalises them via
    /// <c>UiPathODataSvc.SetTransactionResult</c>.
    ///
    /// Declared ``partial`` so the forward-declared stub in
    /// ClaimsProcessContext.cs doesn't collide.
    /// </summary>
    public partial class PerformerQueueClient
    {{
        private readonly HttpClient _http;
        private readonly string _identityUrl;
        private readonly string _orchestratorUrl;
        private readonly string _clientId;
        private readonly string _clientSecret;
        private readonly string _folderId;

        private string? _token;
        private DateTime _expiresAt = DateTime.MinValue;

        public PerformerQueueClient(
            string identityUrl,
            string orchestratorUrl,
            string clientId,
            string clientSecret,
            string folderId)
        {{
            _identityUrl = identityUrl.TrimEnd('/');
            _orchestratorUrl = orchestratorUrl.TrimEnd('/');
            _clientId = clientId;
            _clientSecret = clientSecret;
            _folderId = folderId;
            _http = new HttpClient {{ Timeout = TimeSpan.FromSeconds(30) }};
        }}

        private async Task EnsureTokenAsync()
        {{
            if (_token != null && DateTime.UtcNow < _expiresAt) return;

            var payload = new Dictionary<string, string>
            {{
                ["grant_type"] = "client_credentials",
                ["client_id"] = _clientId,
                ["client_secret"] = _clientSecret,
                ["scope"] = "OR.Queues",
            }};
            using var body = new FormUrlEncodedContent(payload);
            var resp = await _http.PostAsync($"{{_identityUrl}}/identity_/connect/token", body);
            resp.EnsureSuccessStatusCode();
            var json = await resp.Content.ReadAsStringAsync();
            using var doc = JsonDocument.Parse(json);
            _token = doc.RootElement.GetProperty("access_token").GetString();
            var ttl = doc.RootElement.TryGetProperty("expires_in", out var exp) ? exp.GetInt32() : 3600;
            _expiresAt = DateTime.UtcNow.AddSeconds(ttl - 60);
        }}

        private void AddAuthHeaders(HttpRequestMessage req)
        {{
            req.Headers.Authorization = new AuthenticationHeaderValue("Bearer", _token);
            req.Headers.Add("X-UIPATH-OrganizationUnitId", _folderId);
        }}

        /// <summary>
        /// Lease the next queue item. Returns null when queue empty (204).
        /// </summary>
        public async Task<LeasedQueueItem?> StartTransactionAsync(
            string queueName,
            string robotIdentifier = "")
        {{
            await EnsureTokenAsync();

            // OData $metadata: QueuesStartTransactionRequest has a
            // "transactionData" field of type TransactionDataDto with
            // property "Name". The "RobotIdentifier" is not in the
            // metadata schema — it's auto-populated from the robot
            // context when called from inside a UiPath job.
            var envelope = new
            {{
                transactionData = new
                {{
                    Name = queueName,
                }},
            }};
            var content = new StringContent(
                JsonSerializer.Serialize(envelope),
                Encoding.UTF8,
                "application/json");

            var req = new HttpRequestMessage(
                HttpMethod.Post,
                $"{{_orchestratorUrl}}/Queues/UiPathODataSvc.StartTransaction");
            AddAuthHeaders(req);
            req.Content = content;

            var resp = await _http.SendAsync(req);
            if (resp.StatusCode == HttpStatusCode.NoContent || resp.StatusCode == (HttpStatusCode)204)
                return null;
            if (!resp.IsSuccessStatusCode)
            {{
                var text = await resp.Content.ReadAsStringAsync();
                throw new RpaSystemException(
                    $"StartTransaction returned {{(int)resp.StatusCode}}: {{text}}");
            }}

            var json = await resp.Content.ReadAsStringAsync();
            if (string.IsNullOrWhiteSpace(json)) return null;

            using var doc = JsonDocument.Parse(json);
            var item = new LeasedQueueItem
            {{
                Id = doc.RootElement.GetProperty("Id").GetRawText().Trim('"'),
                Reference = doc.RootElement.TryGetProperty("Reference", out var r)
                    ? r.GetString() ?? "" : "",
            }};
            if (doc.RootElement.TryGetProperty("SpecificContent", out var sc))
            {{
                foreach (var prop in sc.EnumerateObject())
                {{
                    item.SpecificContent[prop.Name] = prop.Value.ValueKind == JsonValueKind.String
                        ? (object)(prop.Value.GetString() ?? "")
                        : prop.Value.GetRawText();
                }}
            }}
            return item;
        }}

        /// <summary>
        /// Finalise a leased transaction. Use <c>isSuccessful=false</c>
        /// with a non-null <c>businessError</c> to record a
        /// BusinessException; omit for system errors (they should be
        /// rethrown by the caller so the state machine retries).
        /// </summary>
        public async Task SetTransactionResultAsync(
            string transactionId,
            bool isSuccessful,
            object? output = null,
            string? businessError = null)
        {{
            await EnsureTokenAsync();

            object result;
            if (!isSuccessful && businessError != null)
            {{
                result = new
                {{
                    IsSuccessful = false,
                    Output = output ?? new {{}},
                    ProcessingException = new
                    {{
                        Reason = businessError,
                        Type = "BusinessException",
                        Details = businessError,
                    }},
                }};
            }}
            else
            {{
                result = new
                {{
                    IsSuccessful = isSuccessful,
                    Output = output ?? new {{}},
                }};
            }}
            var envelope = new {{ transactionResult = result }};
            var content = new StringContent(
                JsonSerializer.Serialize(envelope),
                Encoding.UTF8,
                "application/json");

            var req = new HttpRequestMessage(
                HttpMethod.Post,
                $"{{_orchestratorUrl}}/QueueItems({{transactionId}})/UiPathODataSvc.SetTransactionResult");
            AddAuthHeaders(req);
            req.Content = content;

            var resp = await _http.SendAsync(req);
            if (!resp.IsSuccessStatusCode)
            {{
                var text = await resp.Content.ReadAsStringAsync();
                throw new RpaSystemException(
                    $"SetTransactionResult returned {{(int)resp.StatusCode}}: {{text}}");
            }}
        }}
    }}
}}
"""


def generate_performer_init_state_cs(namespace: str = DEFAULT_NAMESPACE) -> str:
    return f"""using System.Threading.Tasks;

namespace {namespace}
{{
    /// <summary>
    /// Performer warmup — validate SuiteCRM auth + PerformerQueueClient
    /// token exchange before we start leasing items. Fails fast if creds
    /// are bad.
    /// </summary>
    public class PerformerInitState : IState
    {{
        public string Name => "PerformerInit";

        public async Task<IState?> ExecuteAsync(ClaimsProcessContext ctx)
        {{
            if (ctx.SuiteCrm == null || ctx.PerformerQueue == null)
                throw new RpaSystemException("Performer missing dependencies");

            // Warmup: a tiny query that validates auth without side effects.
            try
            {{
                await ctx.SuiteCrm.ListRecentCasesByClaimantAsync("__warmup__", 1);
            }}
            catch (System.Exception ex)
            {{
                throw new RpaSystemException($"SuiteCRM warmup failed: {{ex.Message}}", ex);
            }}

            return new PerformerGetTransactionDataState();
        }}
    }}
}}
"""


def generate_performer_get_transaction_state_cs(
    namespace: str = DEFAULT_NAMESPACE,
) -> str:
    return f"""using System;
using System.Collections.Generic;
using System.Threading.Tasks;

namespace {namespace}
{{
    /// <summary>
    /// Fetches the next Queued case from SuiteCRM directly. We bypass
    /// the Orchestrator queue's StartTransaction because that endpoint
    /// requires robot-session context (external app tokens get 204 No
    /// Content even when items are available — BW-19).
    ///
    /// Instead, the Performer queries SuiteCRM for cases with
    /// status="Queued" (set by the Dispatcher) and processes them
    /// one-by-one. This is less atomic than StartTransaction but works
    /// reliably with external-app auth on Community Cloud.
    /// </summary>
    public class PerformerGetTransactionDataState : IState
    {{
        public string Name => "PerformerGetTransactionData";

        public async Task<IState?> ExecuteAsync(ClaimsProcessContext ctx)
        {{
            // Fetch one Queued case from SuiteCRM.
            var cases = await ctx.SuiteCrm!.ListQueuedCasesAsync(1);
            if (cases.Count == 0)
            {{
                Console.WriteLine("[performer] no more Queued cases → End");
                return new EndState();
            }}

            var claim = cases[0];
            ctx.CurrentCase = claim;
            ctx.CurrentTransactionId = claim.SuiteCrmId ?? "";

            // Pre-fetch the policy so CoverageVerificationRule is a pure
            // in-memory check — no extra SuiteCRM round-trip in the hot path.
            try
            {{
                ctx.CurrentPolicy = await ctx.SuiteCrm!.GetPolicyByNumberAsync(claim.PolicyNumber);
            }}
            catch (BusinessException)
            {{
                // No matching policy — leave null so CoverageVerification denies.
                ctx.CurrentPolicy = null;
            }}

            Console.WriteLine($"[performer] processing {{claim.ClaimId}} (id={{claim.SuiteCrmId}})");
            return new PerformerProcessState();
        }}
    }}
}}
"""


def generate_performer_process_state_cs(namespace: str = DEFAULT_NAMESPACE) -> str:
    return f"""using System;
using System.Threading.Tasks;

namespace {namespace}
{{
    /// <summary>
    /// Runs the 5-rule engine on the current claim, writes the verdict
    /// back to SuiteCRM, and creates an audit note. Advances to
    /// SetTransactionStatusState regardless of outcome — only the queue
    /// transaction status differs.
    /// </summary>
    public class PerformerProcessState : IState
    {{
        public string Name => "PerformerProcess";

        public async Task<IState?> ExecuteAsync(ClaimsProcessContext ctx)
        {{
            var claim = ctx.CurrentCase
                ?? throw new RpaSystemException("PerformerProcess: no CurrentCase on context");

            // Evaluate rules.
            var verdict = await ctx.Rules.EvaluateAsync(claim, ctx);
            claim.Verdict = verdict;

            // Build the combined reason from accumulated flag reasons.
            var reason = ctx.FlagReasons.Count > 0
                ? string.Join("; ", ctx.FlagReasons)
                : $"verdict={{verdict}} (no rules fired)";

            // Write verdict back to SuiteCRM + audit note.
            if (!string.IsNullOrEmpty(claim.SuiteCrmId))
            {{
                await ctx.SuiteCrm!.UpdateCaseVerdictAsync(claim.SuiteCrmId!, verdict, reason);
                await ctx.SuiteCrm!.CreateAdjudicationNoteAsync(claim.SuiteCrmId!, verdict, reason);
            }}

            // Record metrics.
            ctx.Metrics.RecordVerdict(verdict, claim.ClaimantName);

            Console.WriteLine($"[performer] {{claim.ClaimId}} → {{verdict}} — {{reason}}");

            return new PerformerSetTransactionStatusState();
        }}
    }}
}}
"""


def generate_performer_set_transaction_status_state_cs(
    namespace: str = DEFAULT_NAMESPACE,
) -> str:
    return f"""using System.Threading.Tasks;

namespace {namespace}
{{
    /// <summary>
    /// Finalises the leased queue transaction. Auto-approved and
    /// flag-for-review claims are marked Successful; Deny verdicts are
    /// still Successful from an Orchestrator perspective (the rule ran
    /// to completion — the verdict is the business outcome, not an error).
    /// True business failures happen upstream in the state transitions.
    /// </summary>
    public class PerformerSetTransactionStatusState : IState
    {{
        public string Name => "PerformerSetTransactionStatus";

        public async Task<IState?> ExecuteAsync(ClaimsProcessContext ctx)
        {{
            // BW-19: We update the case status directly in SuiteCRM
            // instead of calling SetTransactionResult (which also needs
            // robot session context). The Orchestrator queue items are
            // tracking-only — the real state is in SuiteCRM.
            var caseId = ctx.CurrentTransactionId;
            if (!string.IsNullOrEmpty(caseId))
            {{
                var newStatus = ctx.CurrentCase?.Verdict == ClaimVerdict.AutoApprove ? "Closed_Closed"
                    : ctx.CurrentCase?.Verdict == ClaimVerdict.Deny ? "Rejected"
                    : "Pending_Input";
                try
                {{
                    await ctx.SuiteCrm!.UpdateCaseStatusAsync(caseId!, newStatus);
                }}
                catch (System.Exception ex)
                {{
                    Console.WriteLine($"[performer] status update failed: {{ex.Message}}");
                }}
            }}

            // Clear per-item state for the next loop iteration.
            ctx.CurrentCase = null;
            ctx.CurrentPolicy = null;
            ctx.CurrentTransactionId = null;
            ctx.FlagReasons.Clear();
            ctx.RetryCount = 0;

            return new PerformerGetTransactionDataState();
        }}
    }}
}}
"""


def generate_performer_main_cs(
    namespace: str = DEFAULT_NAMESPACE,
    project_namespace: str = "ClaimsPerformer",
) -> str:
    """Emit the Performer's [Workflow] entry point.

    BW-18 fix: class lives in ``project_namespace`` (matching project.json
    name). ``[Workflow]`` attribute on Execute() method, not the class.
    """
    return f"""using System;
using System.Threading.Tasks;
using UiPath.CodedWorkflows;
using {namespace};

namespace {project_namespace}
{{
    /// <summary>
    /// Performer entry point. Wires up SuiteCRM + Orchestrator clients
    /// from baked-in AssetClient constants, then drains the queue until
    /// it's empty.
    /// </summary>
    public class PerformerMain : CodedWorkflow
    {{
        [Workflow]
        public async Task<int> Execute()
        {{
            var ctx = new ClaimsProcessContext
            {{
                SuiteCrm = new SuiteCrmClient(
                    AssetClient.SuiteCrmBaseUrl,
                    AssetClient.SuiteCrmClientId,
                    AssetClient.SuiteCrmClientSecret,
                    AssetClient.SuiteCrmUsername,
                    AssetClient.SuiteCrmPassword),
                PerformerQueue = new PerformerQueueClient(
                    AssetClient.UiPathIdentityUrl,
                    AssetClient.UiPathOrchestratorUrl,
                    AssetClient.UiPathClientId,
                    AssetClient.UiPathClientSecret,
                    AssetClient.UiPathFolderId),
                Rules = new ClaimsRuleEngine(),
            }};

            IState? state = new PerformerInitState();
            while (state is not null)
            {{
                try
                {{
                    state = await state.ExecuteAsync(ctx);
                }}
                catch (BusinessException bex)
                {{
                    Console.WriteLine($"[performer] business: {{bex.Message}}");
                    ctx.Metrics.BusinessFailures++;

                    // Mark the current transaction as a BusinessFailure so
                    // Orchestrator categorises it correctly.
                    if (!string.IsNullOrEmpty(ctx.CurrentTransactionId))
                    {{
                        try
                        {{
                            await ctx.PerformerQueue!.SetTransactionResultAsync(
                                ctx.CurrentTransactionId!,
                                isSuccessful: false,
                                output: new {{ error = bex.Message }},
                                businessError: bex.Message);
                        }}
                        catch
                        {{
                            // If the result submission itself fails, the
                            // outer loop will catch it as a system error.
                        }}
                    }}

                    // Reset per-item state and try the next item.
                    ctx.CurrentCase = null;
                    ctx.CurrentPolicy = null;
                    ctx.CurrentTransactionId = null;
                    ctx.FlagReasons.Clear();
                    state = new PerformerGetTransactionDataState();
                }}
                catch (RpaSystemException rex) when (ctx.RetryCount < 3)
                {{
                    Console.WriteLine($"[performer] system error, retrying: {{rex.Message}}");
                    await Task.Delay(TimeSpan.FromSeconds(Math.Pow(2, ctx.RetryCount)));
                    ctx.RetryCount++;
                    // state stays the same — retry the same state
                }}
            }}

            ctx.Metrics.EndedAt = DateTime.UtcNow;
            Console.WriteLine($"[performer] FINAL {{ctx.Metrics}}");
            return ctx.Metrics.Processed;
        }}
    }}
}}
"""
