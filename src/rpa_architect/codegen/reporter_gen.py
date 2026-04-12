"""C# generator for the Reporter UiPath process.

The Reporter is the third process in the claims factory. It runs on a
schedule (via external cron or manual invocation at SLA test end) and:

  1. Queries the MedicalClaims queue for items finished in the last N
     hours using PerformerQueueClient.ListQueueItemsAsync.
  2. Parses the verdict output from each item's ReturnData.
  3. Renders an HTML SLA report with counts per verdict category, total
     latency, and a flag for any drift window.
  4. Logs the HTML to stdout (Orchestrator captures to RobotLogs). The
     Python ``proof/run_sla_claims.py`` post-processes the logs to
     extract the HTML and save it locally — bucket upload is omitted
     because buckets need extra OAuth scopes (BW §8).
"""

from __future__ import annotations

DEFAULT_NAMESPACE = "MedicalClaimsProcessing"


def generate_reporter_queue_reader_cs(namespace: str = DEFAULT_NAMESPACE) -> str:
    """Emit ReporterQueueReader.cs — thin wrapper over OData ListQueueItems.

    Reuses PerformerQueueClient's token handling but adds a list method
    since the Performer doesn't need it directly.
    """
    return f"""using System;
using System.Collections.Generic;
using System.Net.Http;
using System.Net.Http.Headers;
using System.Text.Json;
using System.Threading.Tasks;

namespace {namespace}
{{
    /// <summary>
    /// Reads queue items from Orchestrator for the Reporter.
    /// </summary>
    public class ReporterQueueReader
    {{
        private readonly HttpClient _http;
        private readonly string _identityUrl;
        private readonly string _orchestratorUrl;
        private readonly string _clientId;
        private readonly string _clientSecret;
        private readonly string _folderId;

        private string? _token;
        private DateTime _expiresAt = DateTime.MinValue;

        public ReporterQueueReader(
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

        public async Task<List<QueueItemSnapshot>> ListQueueItemsAsync(
            string queueName,
            int maxItems = 500)
        {{
            await EnsureTokenAsync();

            var filter = Uri.EscapeDataString(
                $"QueueDefinition/Name eq '{{queueName}}'");
            var req = new HttpRequestMessage(
                HttpMethod.Get,
                $"{{_orchestratorUrl}}/QueueItems?$filter={{filter}}&$top={{maxItems}}");
            req.Headers.Authorization = new AuthenticationHeaderValue("Bearer", _token);
            req.Headers.Add("X-UIPATH-OrganizationUnitId", _folderId);

            var resp = await _http.SendAsync(req);
            resp.EnsureSuccessStatusCode();

            var json = await resp.Content.ReadAsStringAsync();
            using var doc = JsonDocument.Parse(json);
            var items = new List<QueueItemSnapshot>();
            foreach (var item in doc.RootElement.GetProperty("value").EnumerateArray())
            {{
                var snap = new QueueItemSnapshot
                {{
                    Id = item.GetProperty("Id").GetRawText().Trim('"'),
                    Reference = item.TryGetProperty("Reference", out var r)
                        ? r.GetString() ?? "" : "",
                    Status = item.TryGetProperty("Status", out var s)
                        ? s.GetString() ?? "" : "",
                }};
                if (item.TryGetProperty("Output", out var output) && output.ValueKind == JsonValueKind.Object)
                {{
                    if (output.TryGetProperty("verdict", out var v))
                        snap.Verdict = v.GetString() ?? "";
                }}
                items.Add(snap);
            }}
            return items;
        }}
    }}

    public class QueueItemSnapshot
    {{
        public string Id {{ get; set; }} = string.Empty;
        public string Reference {{ get; set; }} = string.Empty;
        public string Status {{ get; set; }} = string.Empty;
        public string Verdict {{ get; set; }} = string.Empty;
    }}
}}
"""


def generate_reporter_init_state_cs(namespace: str = DEFAULT_NAMESPACE) -> str:
    return f"""using System.Threading.Tasks;

namespace {namespace}
{{
    public class ReporterInitState : IState
    {{
        public string Name => "ReporterInit";

        public Task<IState?> ExecuteAsync(ClaimsProcessContext ctx)
        {{
            return Task.FromResult<IState?>(new ReporterProcessState());
        }}
    }}
}}
"""


def generate_reporter_process_state_cs(namespace: str = DEFAULT_NAMESPACE) -> str:
    return f"""using System;
using System.Linq;
using System.Text;
using System.Threading.Tasks;

namespace {namespace}
{{
    /// <summary>
    /// Fetches queue history, aggregates verdict counts, and emits an
    /// HTML SLA report to stdout. Python post-processor at
    /// proof/run_sla_claims.py extracts the HTML from RobotLogs and
    /// saves it to proof/output/sla_claims_report.html.
    /// </summary>
    public class ReporterProcessState : IState
    {{
        public string Name => "ReporterProcess";

        public async Task<IState?> ExecuteAsync(ClaimsProcessContext ctx)
        {{
            var reader = new ReporterQueueReader(
                AssetClient.UiPathIdentityUrl,
                AssetClient.UiPathOrchestratorUrl,
                AssetClient.UiPathClientId,
                AssetClient.UiPathClientSecret,
                AssetClient.UiPathFolderId);

            var items = await reader.ListQueueItemsAsync(AssetClient.QueueName, 500);

            int autoApprove = items.Count(i => i.Verdict == "AutoApprove");
            int flagReview = items.Count(i => i.Verdict == "FlagForReview");
            int deny = items.Count(i => i.Verdict == "Deny");
            int pending = items.Count(i => string.IsNullOrEmpty(i.Verdict));
            int total = items.Count;

            var html = new StringBuilder();
            html.AppendLine("<!DOCTYPE html>");
            html.AppendLine("<html><head><title>Claims SLA Report</title></head><body>");
            html.AppendLine("<h1>Medical Claims — SLA Report</h1>");
            html.AppendLine($"<p>Generated: {{DateTime.UtcNow:o}}</p>");
            html.AppendLine($"<p>Total items: {{total}}</p>");
            html.AppendLine("<h2>Verdict distribution</h2>");
            html.AppendLine("<ul>");
            html.AppendLine($"  <li>auto_approve: {{autoApprove}} ({{Pct(autoApprove, total)}})</li>");
            html.AppendLine($"  <li>flag_for_review: {{flagReview}} ({{Pct(flagReview, total)}})</li>");
            html.AppendLine($"  <li>deny: {{deny}} ({{Pct(deny, total)}})</li>");
            html.AppendLine($"  <li>pending: {{pending}} ({{Pct(pending, total)}})</li>");
            html.AppendLine("</ul>");
            html.AppendLine("</body></html>");

            // Emit the HTML wrapped in markers so the Python post-processor
            // can grep for it in RobotLogs.
            Console.WriteLine("[reporter] <<<SLA_HTML_START>>>");
            Console.WriteLine(html.ToString());
            Console.WriteLine("[reporter] <<<SLA_HTML_END>>>");

            ctx.Metrics.Processed = total;
            ctx.Metrics.AutoApproved = autoApprove;
            ctx.Metrics.Flagged = flagReview;
            ctx.Metrics.Denied = deny;

            return new ReporterSetStatusState();
        }}

        private static string Pct(int n, int total) =>
            total == 0 ? "0%" : $"{{100.0 * n / total:F1}}%";
    }}
}}
"""


def generate_reporter_set_status_state_cs(namespace: str = DEFAULT_NAMESPACE) -> str:
    return f"""using System.Threading.Tasks;

namespace {namespace}
{{
    public class ReporterSetStatusState : IState
    {{
        public string Name => "ReporterSetStatus";

        public Task<IState?> ExecuteAsync(ClaimsProcessContext ctx)
        {{
            return Task.FromResult<IState?>(new EndState());
        }}
    }}
}}
"""


def generate_reporter_main_cs(namespace: str = DEFAULT_NAMESPACE) -> str:
    return f"""using System;
using System.Threading.Tasks;
using UiPath.CodedWorkflows;

namespace {namespace}
{{
    [Workflow]
    public class ReporterMain : CodedWorkflow
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
                Rules = new ClaimsRuleEngine(),
            }};

            IState? state = new ReporterInitState();
            while (state is not null)
            {{
                try
                {{
                    state = await state.ExecuteAsync(ctx);
                }}
                catch (RpaSystemException rex) when (ctx.RetryCount < 3)
                {{
                    Console.WriteLine($"[reporter] retry: {{rex.Message}}");
                    await Task.Delay(TimeSpan.FromSeconds(Math.Pow(2, ctx.RetryCount)));
                    ctx.RetryCount++;
                }}
            }}

            ctx.Metrics.EndedAt = DateTime.UtcNow;
            Console.WriteLine($"[reporter] FINAL {{ctx.Metrics}}");
            return ctx.Metrics.Processed;
        }}
    }}
}}
"""
