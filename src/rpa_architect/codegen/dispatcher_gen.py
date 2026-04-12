"""C# generator for the Dispatcher UiPath process.

The Dispatcher is the first of three processes in the claims factory:

  Dispatcher (this file)   — fetches new-status Cases from SuiteCRM,
                              pushes each as a queue item, PATCHes the
                              case to 'Queued'. Runs every 2 min via
                              external cron.

  Performer (EV2-6)        — leases one queue item at a time, runs the
                              5-rule engine, writes verdict back to
                              SuiteCRM.

  Reporter (EV2-7)         — aggregates queue history, renders an HTML
                              SLA report.

Each process is a completely separate .nupkg. This file emits the
Dispatcher-specific state machine + its supporting UiPathQueueClient
(an in-robot HTTP client for Orchestrator's AddQueueItem endpoint) and
AssetClient (reads SuiteCRM creds baked in at pack time).
"""

from __future__ import annotations

DEFAULT_NAMESPACE = "MedicalClaimsProcessing"


def generate_claims_istate_cs(namespace: str = DEFAULT_NAMESPACE) -> str:
    """Emit IState + IState interface for the claims flow.

    Separate from v0.5's ``generate_istate_cs`` because it takes
    ``ClaimsProcessContext`` rather than the Odoo ``ProcessContext``.
    """
    return f"""using System.Threading.Tasks;

namespace {namespace}
{{
    /// <summary>
    /// A single state in the Dispatcher/Performer state machine. Returns
    /// the next state to transition to, or <c>null</c> to end the loop.
    /// </summary>
    public interface IState
    {{
        string Name {{ get; }}
        Task<IState?> ExecuteAsync(ClaimsProcessContext ctx);
    }}
}}
"""


def generate_claims_exceptions_cs(namespace: str = DEFAULT_NAMESPACE) -> str:
    """Emit BusinessException + RpaSystemException for the claims flow.

    Shape-identical to v0.5's ``generate_exceptions_cs`` but included here
    so the claims C# project set is self-contained.
    """
    return f"""using System;

namespace {namespace}
{{
    /// <summary>
    /// Thrown when a claim fails a business rule deterministically.
    /// The state machine catches this and advances to the next item
    /// without retrying — retrying a business failure yields the same
    /// answer.
    /// </summary>
    public class BusinessException : Exception
    {{
        public BusinessException(string message) : base(message) {{ }}
    }}

    /// <summary>
    /// Thrown when an infrastructure call fails transiently (HTTP 5xx,
    /// network timeout, token expiry). The state machine catches this
    /// and retries the same state with exponential backoff.
    /// </summary>
    public class RpaSystemException : Exception
    {{
        public RpaSystemException(string message) : base(message) {{ }}
        public RpaSystemException(string message, Exception inner) : base(message, inner) {{ }}
    }}
}}
"""


def generate_uipath_queue_client_cs(namespace: str = DEFAULT_NAMESPACE) -> str:
    """Emit a C# HTTP client that hits Orchestrator's AddQueueItem endpoint.

    Can't call the Python ``UiPathClient`` from inside the robot — all
    Orchestrator interactions from a CodedWorkflow must be pure C#.
    Authenticates via OAuth2 client credentials, caches the token, and
    issues POSTs to ``Queues/UiPathODataSvc.AddQueueItem``.
    """
    return f"""using System;
using System.Collections.Generic;
using System.Net.Http;
using System.Net.Http.Headers;
using System.Text;
using System.Text.Json;
using System.Threading.Tasks;

namespace {namespace}
{{
    /// <summary>
    /// Lightweight Orchestrator client usable from inside a CodedWorkflow.
    /// Only implements what the Dispatcher needs: token exchange + add
    /// queue item. The Performer uses StartTransaction/SetTransactionResult
    /// through a similar client (see PerformerQueueClient).
    ///
    /// Declared ``partial`` so the forward-declared stub in
    /// ClaimsProcessContext.cs doesn't collide — the C# compiler merges
    /// the two declarations at compile time.
    /// </summary>
    public partial class UiPathQueueClient
    {{
        private readonly HttpClient _http;
        private readonly string _identityUrl;
        private readonly string _orchestratorUrl;
        private readonly string _clientId;
        private readonly string _clientSecret;
        private readonly string _folderId;

        private string? _token;
        private DateTime _expiresAt = DateTime.MinValue;

        public UiPathQueueClient(
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
            if (_token != null && DateTime.UtcNow < _expiresAt)
                return;

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

        public async Task AddQueueItemAsync(
            string queueName,
            string reference,
            object specificContent,
            string priority = "Normal")
        {{
            await EnsureTokenAsync();

            var envelope = new
            {{
                itemData = new
                {{
                    Name = queueName,
                    Reference = reference,
                    Priority = priority,
                    SpecificContent = specificContent,
                }},
            }};
            var content = new StringContent(
                JsonSerializer.Serialize(envelope),
                Encoding.UTF8,
                "application/json");

            var req = new HttpRequestMessage(
                HttpMethod.Post,
                $"{{_orchestratorUrl}}/Queues/UiPathODataSvc.AddQueueItem");
            req.Headers.Authorization = new AuthenticationHeaderValue("Bearer", _token);
            req.Headers.Add("X-UIPATH-OrganizationUnitId", _folderId);
            req.Content = content;

            var resp = await _http.SendAsync(req);
            if (!resp.IsSuccessStatusCode)
            {{
                var text = await resp.Content.ReadAsStringAsync();
                throw new RpaSystemException(
                    $"AddQueueItem returned {{(int)resp.StatusCode}}: {{text}}");
            }}
        }}
    }}
}}
"""


def generate_asset_client_cs(namespace: str = DEFAULT_NAMESPACE) -> str:
    """Emit AssetClient.cs — reads SuiteCRM credentials baked in at pack time.

    Because Orchestrator Assets don't surface as env vars in Portable
    (v0.5 brick wall §7), the deploy script regenerates this file with
    the current SuiteCRM URL + OAuth credentials as C# string literals
    before every ``uipcli pack``. Runtime reads are then just property
    lookups — no async, no HTTP.
    """
    return f"""namespace {namespace}
{{
    /// <summary>
    /// Baked-at-pack-time configuration for SuiteCRM + UiPath identity.
    /// Regenerated by ``proof/deploy_claims.py`` on every deploy so the
    /// compiled DLL has the current tunnel URL + external app creds.
    ///
    /// Note: in a real enterprise with an Enterprise Orchestrator tenant,
    /// these would be per-environment Assets accessed via the UiPath SDK.
    /// On Community tier with Portable runtime, that path is broken
    /// (assets don't reach the robot as env vars), so we bake at build.
    /// </summary>
    public static class AssetClient
    {{
        // These values are placeholders that deploy_claims.py rewrites
        // before packing. The compile-time constants guarantee there's
        // no secret lookup path at runtime — what ships is exactly what
        // was sealed into the package.
        public const string SuiteCrmBaseUrl = "__SUITECRM_BASE_URL__";
        public const string SuiteCrmClientId = "__SUITECRM_CLIENT_ID__";
        public const string SuiteCrmClientSecret = "__SUITECRM_CLIENT_SECRET__";
        public const string SuiteCrmUsername = "__SUITECRM_USERNAME__";
        public const string SuiteCrmPassword = "__SUITECRM_PASSWORD__";

        public const string UiPathIdentityUrl = "__UIPATH_IDENTITY_URL__";
        public const string UiPathOrchestratorUrl = "__UIPATH_ORCHESTRATOR_URL__";
        public const string UiPathClientId = "__UIPATH_CLIENT_ID__";
        public const string UiPathClientSecret = "__UIPATH_CLIENT_SECRET__";
        public const string UiPathFolderId = "__UIPATH_FOLDER_ID__";
        public const string QueueName = "MedicalClaims";

        public static string GetSuiteCrmBaseUrl() => SuiteCrmBaseUrl;
        public static string GetSuiteCrmClientId() => SuiteCrmClientId;
        public static string GetSuiteCrmClientSecret() => SuiteCrmClientSecret;
    }}
}}
"""


def generate_dispatcher_init_state_cs(namespace: str = DEFAULT_NAMESPACE) -> str:
    return f"""using System.Collections.Generic;
using System.Threading.Tasks;

namespace {namespace}
{{
    /// <summary>
    /// Dispatcher init: stand up SuiteCRM client, warm it up with a dummy
    /// request to fail fast on bad creds, and leave the transaction-
    /// gathering for GetTransactionDataState.
    /// </summary>
    public class DispatcherInitState : IState
    {{
        public string Name => "DispatcherInit";

        public async Task<IState?> ExecuteAsync(ClaimsProcessContext ctx)
        {{
            if (ctx.SuiteCrm == null)
                throw new RpaSystemException("Dispatcher SuiteCrm client not initialized");

            // Warm-up request: list new Cases with a small page size.
            // This doubles as auth validation and populates the work
            // list in CurrentCase batch (we use ctx.FlagReasons as a
            // makeshift queue for the dispatch batch — a hack acceptable
            // because the DispatcherProcessState consumes it immediately).
            try
            {{
                // This first GET is just for auth validation; the real
                // list is fetched in GetTransactionDataState on each loop.
                await ctx.SuiteCrm.ListRecentCasesByClaimantAsync("__warmup__", 1);
            }}
            catch (System.Exception ex)
            {{
                throw new RpaSystemException($"SuiteCRM warmup failed: {{ex.Message}}", ex);
            }}

            return new DispatcherGetTransactionDataState();
        }}
    }}
}}
"""


def generate_dispatcher_get_transaction_state_cs(namespace: str = DEFAULT_NAMESPACE) -> str:
    return f"""using System.Threading.Tasks;

namespace {namespace}
{{
    /// <summary>
    /// The dispatcher's GetTransactionData state. Unlike the Performer
    /// (which leases one item from an Orchestrator queue), the Dispatcher
    /// is a PRODUCER — it pulls Cases from SuiteCRM and will enqueue them.
    ///
    /// For simplicity in the Dispatcher's Execute loop, we transition
    /// directly to ProcessState without any per-item work — ProcessState
    /// does the fetch+loop in one pass, then transitions to End.
    /// </summary>
    public class DispatcherGetTransactionDataState : IState
    {{
        public string Name => "DispatcherGetTransactionData";

        public Task<IState?> ExecuteAsync(ClaimsProcessContext ctx)
        {{
            return Task.FromResult<IState?>(new DispatcherProcessState());
        }}
    }}
}}
"""


def generate_dispatcher_process_state_cs(namespace: str = DEFAULT_NAMESPACE) -> str:
    """Emit the Dispatcher's ProcessState — the hot loop that fetches all
    new-status Cases from SuiteCRM, pushes each to the MedicalClaims queue
    via UiPathQueueClient, and PATCHes the Case to 'Queued'.

    Implements BW-10 payload-size fallback: if a case's serialized payload
    would exceed 800 KiB, we omit the embedded payload and let the
    Performer re-fetch from SuiteCRM using just the claim_id.
    """
    return f"""using System;
using System.Collections.Generic;
using System.Text;
using System.Text.Json;
using System.Threading.Tasks;

namespace {namespace}
{{
    /// <summary>
    /// Fetches all new-status Cases from SuiteCRM and enqueues each one
    /// as a MedicalClaims queue item. Patches each case's status to
    /// 'Queued' on success so a re-run doesn't re-dispatch it.
    ///
    /// Payload-size guard (BW-10): queue item SpecificContent has a 1 MiB
    /// limit in Orchestrator. If the embedded base64 case JSON would
    /// exceed 800 KiB (leaving headroom for the OData envelope), we omit
    /// the payload and write ``payload_bucket_ref`` instead — the
    /// Performer recognises this and re-fetches from SuiteCRM.
    /// </summary>
    public class DispatcherProcessState : IState
    {{
        public string Name => "DispatcherProcess";

        private const int MaxPayloadSize = 800 * 1024;

        public async Task<IState?> ExecuteAsync(ClaimsProcessContext ctx)
        {{
            if (ctx.SuiteCrm == null || ctx.UiPathQueue == null)
                throw new RpaSystemException("Dispatcher missing dependencies");

            // Fetch the work batch. Limited to 50 per run — the Dispatcher
            // is cron-driven (every 2 min) and the Performer drains the
            // queue concurrently, so bigger batches just wait longer.
            var batch = await ctx.SuiteCrm.ListNewCasesAsync(50);

            foreach (var claim in batch)
            {{
                // Serialize the case for the queue payload.
                var json = JsonSerializer.Serialize(claim);
                var bytes = Encoding.UTF8.GetBytes(json);
                var b64 = Convert.ToBase64String(bytes);

                object specificContent;
                if (b64.Length > MaxPayloadSize)
                {{
                    // BW-10: payload too big for queue item. Performer will
                    // re-fetch by id.
                    specificContent = new
                    {{
                        claim_id = claim.ClaimId,
                        suitecrm_id = claim.SuiteCrmId ?? "",
                        payload_bucket_ref = $"bucket://ClaimPayloads/{{claim.ClaimId}}.json",
                        dispatched_at = DateTime.UtcNow.ToString("o"),
                    }};
                }}
                else
                {{
                    specificContent = new
                    {{
                        claim_id = claim.ClaimId,
                        suitecrm_id = claim.SuiteCrmId ?? "",
                        payload_b64 = b64,
                        dispatched_at = DateTime.UtcNow.ToString("o"),
                    }};
                }}

                try
                {{
                    await ctx.UiPathQueue.AddQueueItemAsync(
                        AssetClient.QueueName,
                        reference: claim.ClaimId,
                        specificContent: specificContent);

                    // Flip SuiteCRM status so we don't re-dispatch.
                    if (!string.IsNullOrEmpty(claim.SuiteCrmId))
                    {{
                        await ctx.SuiteCrm.UpdateCaseStatusAsync(
                            claim.SuiteCrmId!,
                            "Queued");
                    }}

                    ctx.Metrics.Processed++;
                }}
                catch (BusinessException bex)
                {{
                    ctx.Metrics.BusinessFailures++;
                    ctx.FlagReasons.Add($"[{{claim.ClaimId}}] business: {{bex.Message}}");
                }}
                catch (RpaSystemException)
                {{
                    ctx.Metrics.SystemFailures++;
                    throw;  // let the driver retry the whole state
                }}
            }}

            return new DispatcherSetTransactionStatusState();
        }}
    }}
}}
"""


def generate_dispatcher_set_transaction_status_state_cs(
    namespace: str = DEFAULT_NAMESPACE,
) -> str:
    return f"""using System.Threading.Tasks;

namespace {namespace}
{{
    /// <summary>
    /// Terminal state of the dispatcher loop. Since the Dispatcher
    /// processes the entire batch in ProcessState (not one-at-a-time
    /// like the Performer), this state just transitions to EndState.
    /// </summary>
    public class DispatcherSetTransactionStatusState : IState
    {{
        public string Name => "DispatcherSetTransactionStatus";

        public Task<IState?> ExecuteAsync(ClaimsProcessContext ctx)
        {{
            return Task.FromResult<IState?>(new EndState());
        }}
    }}
}}
"""


def generate_claims_end_state_cs(namespace: str = DEFAULT_NAMESPACE) -> str:
    """Emit a claims-flavoured EndState that emits the batch summary.

    Reused by both Dispatcher and Performer. Can't use v0.5's
    ``generate_end_state_cs`` because that references the Odoo-locked
    ``BatchMetrics`` shape (TotalInvoices, CreatedBillIds, ByVendor, ...).
    """
    return f"""using System;
using System.Threading.Tasks;

namespace {namespace}
{{
    /// <summary>
    /// Terminal state. Emits the ClaimMetrics summary to stdout which
    /// Orchestrator captures in RobotLogs — the Reporter reads these
    /// logs to build the SLA HTML.
    /// </summary>
    public class EndState : IState
    {{
        public string Name => "End";

        public Task<IState?> ExecuteAsync(ClaimsProcessContext ctx)
        {{
            ctx.Metrics.EndedAt = DateTime.UtcNow;
            Console.WriteLine($"[end] {{ctx.Metrics}}");
            return Task.FromResult<IState?>(null);
        }}
    }}
}}
"""


def generate_dispatcher_main_cs(namespace: str = DEFAULT_NAMESPACE) -> str:
    return f"""using System;
using System.Threading.Tasks;
using UiPath.CodedWorkflows;

namespace {namespace}
{{
    /// <summary>
    /// Dispatcher entry point — the [Workflow]-annotated class that
    /// UiPath invokes from Main.xaml. Instantiates SuiteCrmClient and
    /// UiPathQueueClient from baked-in AssetClient constants, then runs
    /// the state machine loop to drain all new-status Cases into the
    /// MedicalClaims queue.
    /// </summary>
    [Workflow]
    public class DispatcherMain : CodedWorkflow
    {{
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
                UiPathQueue = new UiPathQueueClient(
                    AssetClient.UiPathIdentityUrl,
                    AssetClient.UiPathOrchestratorUrl,
                    AssetClient.UiPathClientId,
                    AssetClient.UiPathClientSecret,
                    AssetClient.UiPathFolderId),
                Rules = new ClaimsRuleEngine(),
            }};

            IState? state = new DispatcherInitState();
            while (state is not null)
            {{
                try
                {{
                    state = await state.ExecuteAsync(ctx);
                }}
                catch (BusinessException bex)
                {{
                    Console.WriteLine($"[dispatcher] business: {{bex.Message}}");
                    ctx.Metrics.BusinessFailures++;
                    state = new DispatcherSetTransactionStatusState();
                }}
                catch (RpaSystemException rex) when (ctx.RetryCount < 3)
                {{
                    Console.WriteLine($"[dispatcher] system error, retrying: {{rex.Message}}");
                    await Task.Delay(TimeSpan.FromSeconds(Math.Pow(2, ctx.RetryCount)));
                    ctx.RetryCount++;
                }}
            }}

            ctx.Metrics.EndedAt = DateTime.UtcNow;
            Console.WriteLine($"[dispatcher] {{ctx.Metrics}}");
            return ctx.Metrics.Processed;
        }}
    }}
}}
"""
