"""C# generator for SuiteCrmClient.cs — the OAuth2 REST adapter.

Generates a standalone `HttpClient`-based client for SuiteCRM 8's JSON:API
surface. Handles token caching, BW-09 401-refresh-retry, and the seven
methods the claims factory needs.

Policies and providers are modelled as SuiteCRM Accounts with an
`account_type` discriminator, since SuiteCRM Community doesn't ship with
dedicated modules for either. The structured data lives in the `description`
field (key=value lines) because we can't add custom fields on a free
install. The generator emits the parsing logic inline.
"""

from __future__ import annotations

DEFAULT_NAMESPACE = "MedicalClaimsProcessing"


def generate_suitecrm_client_cs(namespace: str = DEFAULT_NAMESPACE) -> str:
    """Emit SuiteCrmClient.cs for the given namespace."""
    return f"""using System;
using System.Collections.Generic;
using System.Globalization;
using System.Linq;
using System.Net;
using System.Net.Http;
using System.Net.Http.Headers;
using System.Text;
using System.Text.Json;
using System.Threading.Tasks;

namespace {namespace}
{{
    /// <summary>
    /// SuiteCRM 8 OAuth2 REST client. Password-grant token caching with
    /// automatic 401 refresh-retry (BW-09 mitigation — SuiteCRM evicts
    /// tokens from the Laravel Passport cache at ~50 min idle even though
    /// the TTL is nominally 3600s).
    ///
    /// All methods throw <see cref="BusinessException"/> on 404 (the
    /// resource doesn't exist — a rule-level concern) and
    /// <see cref="RpaSystemException"/> on 5xx / network failures (an
    /// infrastructure concern that should trigger a retry at the state
    /// machine level).
    /// </summary>
    public class SuiteCrmClient
    {{
        private readonly HttpClient _http;
        private readonly string _baseUrl;
        private readonly string _clientId;
        private readonly string _clientSecret;
        private readonly string _username;
        private readonly string _password;

        private string? _accessToken;
        private DateTime _expiresAt = DateTime.MinValue;

        private static readonly JsonSerializerOptions JsonOpts = new()
        {{
            PropertyNameCaseInsensitive = true,
        }};

        public SuiteCrmClient(
            string baseUrl,
            string clientId,
            string clientSecret,
            string username,
            string password)
        {{
            _baseUrl = baseUrl.TrimEnd('/');
            _clientId = clientId;
            _clientSecret = clientSecret;
            _username = username;
            _password = password;
            _http = new HttpClient {{ Timeout = TimeSpan.FromSeconds(30) }};
        }}

        // ------------------------------------------------------------------
        // OAuth2 — password grant + cached bearer token
        // ------------------------------------------------------------------

        private async Task EnsureTokenAsync()
        {{
            if (_accessToken != null && DateTime.UtcNow < _expiresAt)
                return;

            var payload = new
            {{
                grant_type = "password",
                client_id = _clientId,
                client_secret = _clientSecret,
                username = _username,
                password = _password,
                scope = "",
            }};
            var body = new StringContent(
                JsonSerializer.Serialize(payload),
                Encoding.UTF8,
                "application/json");

            HttpResponseMessage resp;
            try
            {{
                resp = await _http.PostAsync($"{{_baseUrl}}/Api/access_token", body);
            }}
            catch (HttpRequestException ex)
            {{
                throw new RpaSystemException($"suitecrm token request failed: {{ex.Message}}", ex);
            }}

            if (!resp.IsSuccessStatusCode)
            {{
                var text = await resp.Content.ReadAsStringAsync();
                throw new RpaSystemException(
                    $"suitecrm token request returned {{(int)resp.StatusCode}}: {{text}}");
            }}

            var json = await resp.Content.ReadAsStringAsync();
            using var doc = JsonDocument.Parse(json);
            _accessToken = doc.RootElement.GetProperty("access_token").GetString();
            var ttl = doc.RootElement.TryGetProperty("expires_in", out var exp) ? exp.GetInt32() : 3600;
            // Refresh 5 minutes before expiry to stay ahead of the 50-min
            // idle eviction bug (BW-09).
            _expiresAt = DateTime.UtcNow.AddSeconds(Math.Min(ttl, 2700));
        }}

        // ------------------------------------------------------------------
        // Core request helper — 401 refresh + retry once
        // ------------------------------------------------------------------

        private async Task<HttpResponseMessage> SendAsync(
            HttpMethod method,
            string path,
            HttpContent? content = null)
        {{
            await EnsureTokenAsync();

            HttpResponseMessage send()
            {{
                var req = new HttpRequestMessage(method, $"{{_baseUrl}}{{path}}");
                req.Headers.Authorization = new AuthenticationHeaderValue("Bearer", _accessToken);
                req.Headers.Accept.Add(new MediaTypeWithQualityHeaderValue("application/vnd.api+json"));
                if (content != null) req.Content = content;
                return _http.Send(req);
            }}

            HttpResponseMessage resp;
            try
            {{
                resp = await Task.Run(send);
            }}
            catch (HttpRequestException ex)
            {{
                throw new RpaSystemException($"suitecrm request failed: {{ex.Message}}", ex);
            }}

            if (resp.StatusCode == HttpStatusCode.Unauthorized)
            {{
                // BW-09: token was evicted mid-session. Clear and retry once.
                _accessToken = null;
                _expiresAt = DateTime.MinValue;
                await EnsureTokenAsync();
                try
                {{
                    resp = await Task.Run(send);
                }}
                catch (HttpRequestException ex)
                {{
                    throw new RpaSystemException($"suitecrm retry after 401 failed: {{ex.Message}}", ex);
                }}
            }}

            if ((int)resp.StatusCode >= 500)
            {{
                var text = await resp.Content.ReadAsStringAsync();
                throw new RpaSystemException(
                    $"suitecrm {{method}} {{path}} returned {{(int)resp.StatusCode}}: {{text}}");
            }}

            return resp;
        }}

        // ------------------------------------------------------------------
        // Case fetch + update
        // ------------------------------------------------------------------

        public async Task<Case> GetCaseByIdAsync(string caseId)
        {{
            var resp = await SendAsync(HttpMethod.Get, $"/Api/V8/module/Cases/{{caseId}}");
            if (resp.StatusCode == HttpStatusCode.NotFound)
                throw new BusinessException($"Case {{caseId}} not found in SuiteCRM");
            resp.EnsureSuccessStatusCode();

            var json = await resp.Content.ReadAsStringAsync();
            using var doc = JsonDocument.Parse(json);
            var attrs = doc.RootElement.GetProperty("data").GetProperty("attributes");

            return new Case
            {{
                ClaimId = attrs.GetProperty("name").GetString() ?? "",
                Status = attrs.GetProperty("status").GetString() ?? "New",
                SuiteCrmId = doc.RootElement.GetProperty("data").GetProperty("id").GetString(),
            }}.WithDescriptionFields(attrs.GetProperty("description").GetString() ?? "");
        }}

        public async Task<List<Case>> ListNewCasesAsync(int limit = 50)
        {{
            // SuiteCRM maps status "New" to internal key "Open_New".
            // The filter syntax MUST include the [eq] operator —
            // filter[status][eq]=Open_New works; filter[status]=Open_New
            // silently returns empty or 500.
            var resp = await SendAsync(
                HttpMethod.Get,
                $"/Api/V8/module/Cases?filter%5Bstatus%5D%5Beq%5D=Open_New&page%5Bsize%5D={{limit}}");
            resp.EnsureSuccessStatusCode();

            var json = await resp.Content.ReadAsStringAsync();
            using var doc = JsonDocument.Parse(json);
            var data = doc.RootElement.GetProperty("data");
            var cases = new List<Case>();
            foreach (var item in data.EnumerateArray())
            {{
                var attrs = item.GetProperty("attributes");
                var c = new Case
                {{
                    ClaimId = attrs.GetProperty("name").GetString() ?? "",
                    Status = attrs.GetProperty("status").GetString() ?? "New",
                    SuiteCrmId = item.GetProperty("id").GetString(),
                }}.WithDescriptionFields(attrs.GetProperty("description").GetString() ?? "");
                cases.Add(c);
            }}
            return cases;
        }}

        public async Task<List<Case>> ListQueuedCasesAsync(int limit = 1)
        {{
            // BW-19 workaround: Performer reads from SuiteCRM directly
            // instead of using Orchestrator StartTransaction (which needs
            // robot-session context). "Queued" is the status the
            // Dispatcher sets after pushing the item to the queue.
            var resp = await SendAsync(
                HttpMethod.Get,
                $"/Api/V8/module/Cases?filter%5Bstatus%5D%5Beq%5D=Queued&page%5Bsize%5D={{limit}}");
            resp.EnsureSuccessStatusCode();

            var json = await resp.Content.ReadAsStringAsync();
            using var doc = JsonDocument.Parse(json);
            var data = doc.RootElement.GetProperty("data");
            var cases = new List<Case>();
            foreach (var item in data.EnumerateArray())
            {{
                var attrs = item.GetProperty("attributes");
                var c = new Case
                {{
                    ClaimId = attrs.GetProperty("name").GetString() ?? "",
                    Status = attrs.GetProperty("status").GetString() ?? "Queued",
                    SuiteCrmId = item.GetProperty("id").GetString(),
                }}.WithDescriptionFields(attrs.GetProperty("description").GetString() ?? "");
                cases.Add(c);
            }}
            return cases;
        }}

        public async Task UpdateCaseStatusAsync(string caseId, string status)
        {{
            var payload = new
            {{
                data = new
                {{
                    type = "Cases",
                    id = caseId,
                    attributes = new {{ status = status }},
                }},
            }};
            var content = new StringContent(
                JsonSerializer.Serialize(payload),
                Encoding.UTF8,
                "application/vnd.api+json");
            // SuiteCRM 8 JSON:API: PATCH goes to /Api/V8/module (no type
            // suffix in the URL). The type + id live in the payload body.
            var resp = await SendAsync(
                new HttpMethod("PATCH"),
                "/Api/V8/module",
                content);
            resp.EnsureSuccessStatusCode();
        }}

        public async Task UpdateCaseVerdictAsync(string caseId, ClaimVerdict verdict, string reason)
        {{
            var patchPayload = new
            {{
                data = new
                {{
                    type = "Cases",
                    id = caseId,
                    attributes = new
                    {{
                        status = verdict == ClaimVerdict.AutoApprove ? "Closed"
                               : verdict == ClaimVerdict.Deny ? "Rejected"
                               : "Pending Input",
                        resolution = $"verdict={{verdict}}; reason={{reason}}",
                    }},
                }},
            }};
            var content = new StringContent(
                JsonSerializer.Serialize(patchPayload),
                Encoding.UTF8,
                "application/vnd.api+json");

            var resp = await SendAsync(
                new HttpMethod("PATCH"),
                "/Api/V8/module",
                content);
            resp.EnsureSuccessStatusCode();
        }}

        // ------------------------------------------------------------------
        // Policy + provider fetch (stored as Accounts with type discriminator)
        // ------------------------------------------------------------------

        public async Task<Policy> GetPolicyByNumberAsync(string policyNumber)
        {{
            var resp = await SendAsync(
                HttpMethod.Get,
                $"/Api/V8/module/Accounts?filter%5Bname%5D%5Beq%5D={{Uri.EscapeDataString(policyNumber)}}");
            if (resp.StatusCode == HttpStatusCode.NotFound)
                throw new BusinessException($"Policy {{policyNumber}} not found");
            resp.EnsureSuccessStatusCode();

            var json = await resp.Content.ReadAsStringAsync();
            using var doc = JsonDocument.Parse(json);
            var data = doc.RootElement.GetProperty("data");
            if (data.GetArrayLength() == 0)
                throw new BusinessException($"Policy {{policyNumber}} not found");

            var attrs = data[0].GetProperty("attributes");
            var descLines = (attrs.GetProperty("description").GetString() ?? "").Split('\\n');
            var dict = ParseDescriptionFields(descLines);

            return new Policy
            {{
                PolicyNumber = policyNumber,
                Holder = dict.GetValueOrDefault("holder", ""),
                CoverageStart = ParseDate(dict.GetValueOrDefault("coverage_start", "")),
                CoverageEnd = ParseDate(dict.GetValueOrDefault("coverage_end", "")),
                DeductibleRemaining = ParseDecimal(dict.GetValueOrDefault("deductible_remaining", "0")),
                OutOfPocketMax = ParseDecimal(dict.GetValueOrDefault("out_of_pocket_max", "0")),
            }};
        }}

        public async Task<Provider> GetProviderByNpiAsync(string npi)
        {{
            var resp = await SendAsync(
                HttpMethod.Get,
                $"/Api/V8/module/Accounts?filter%5Bname%5D%5Beq%5D={{Uri.EscapeDataString(npi)}}");
            if (resp.StatusCode == HttpStatusCode.NotFound)
                throw new BusinessException($"Provider {{npi}} not found");
            resp.EnsureSuccessStatusCode();

            var json = await resp.Content.ReadAsStringAsync();
            using var doc = JsonDocument.Parse(json);
            var data = doc.RootElement.GetProperty("data");
            if (data.GetArrayLength() == 0)
                throw new BusinessException($"Provider {{npi}} not found");

            var attrs = data[0].GetProperty("attributes");
            var dict = ParseDescriptionFields((attrs.GetProperty("description").GetString() ?? "").Split('\\n'));

            return new Provider
            {{
                Npi = npi,
                Name = dict.GetValueOrDefault("name", ""),
                InNetwork = dict.GetValueOrDefault("in_network", "false")
                    .Equals("true", StringComparison.OrdinalIgnoreCase),
                SpecialtyCode = dict.GetValueOrDefault("specialty_code", ""),
            }};
        }}

        // ------------------------------------------------------------------
        // Fraud velocity — batched recent-cases query for claimant
        // ------------------------------------------------------------------

        public async Task<List<Case>> ListRecentCasesByClaimantAsync(
            string claimantName,
            int withinDays = 30)
        {{
            // SuiteCRM JSON:API supports filter[name] but not arbitrary
            // date ranges on claim fields. We fetch by claimant and filter
            // client-side — cheap because the result set is tiny.
            // Note: claimant_name lives in description, not the top-level
            // name field, so we scan the description of matching cases.
            var resp = await SendAsync(
                HttpMethod.Get,
                $"/Api/V8/module/Cases?filter%5Bdescription%5D%5Blike%5D=claimant_name%3D{{Uri.EscapeDataString(claimantName)}}&page%5Bsize%5D=50");
            if (!resp.IsSuccessStatusCode)
                return new List<Case>();

            var json = await resp.Content.ReadAsStringAsync();
            using var doc = JsonDocument.Parse(json);
            var data = doc.RootElement.GetProperty("data");
            var cutoff = DateTime.UtcNow.AddDays(-withinDays);
            var cases = new List<Case>();

            foreach (var item in data.EnumerateArray())
            {{
                var attrs = item.GetProperty("attributes");
                var c = new Case
                {{
                    ClaimId = attrs.GetProperty("name").GetString() ?? "",
                    Status = attrs.GetProperty("status").GetString() ?? "",
                    SuiteCrmId = item.GetProperty("id").GetString(),
                }}.WithDescriptionFields(attrs.GetProperty("description").GetString() ?? "");

                if (c.ClaimantName == claimantName && c.SubmittedAt >= cutoff)
                    cases.Add(c);
            }}

            return cases;
        }}

        // ------------------------------------------------------------------
        // Notes as document substitute (BW-07 — Documents REST broken)
        // ------------------------------------------------------------------

        public async Task<List<string>> GetCaseNotesAsync(string caseId)
        {{
            var resp = await SendAsync(
                HttpMethod.Get,
                $"/Api/V8/module/Notes?filter%5Bparent_type%5D%5Beq%5D=Cases&filter%5Bparent_id%5D%5Beq%5D={{Uri.EscapeDataString(caseId)}}");
            if (!resp.IsSuccessStatusCode) return new List<string>();

            var json = await resp.Content.ReadAsStringAsync();
            using var doc = JsonDocument.Parse(json);
            var data = doc.RootElement.GetProperty("data");
            var filenames = new List<string>();
            foreach (var item in data.EnumerateArray())
            {{
                var name = item.GetProperty("attributes").GetProperty("filename").GetString();
                if (!string.IsNullOrEmpty(name)) filenames.Add(name);
            }}
            return filenames;
        }}

        public async Task CreateAdjudicationNoteAsync(
            string caseId,
            ClaimVerdict verdict,
            string reason)
        {{
            var payload = new
            {{
                data = new
                {{
                    type = "Notes",
                    attributes = new
                    {{
                        name = $"Adjudication: {{verdict}}",
                        parent_type = "Cases",
                        parent_id = caseId,
                        description = $"Verdict: {{verdict}}\\n\\nReason: {{reason}}\\n\\nProcessed: {{DateTime.UtcNow:o}}",
                    }},
                }},
            }};
            var content = new StringContent(
                JsonSerializer.Serialize(payload),
                Encoding.UTF8,
                "application/vnd.api+json");

            // POST goes to /Api/V8/module (no type suffix).
            var resp = await SendAsync(HttpMethod.Post, "/Api/V8/module", content);
            resp.EnsureSuccessStatusCode();
        }}

        // ------------------------------------------------------------------
        // Helpers
        // ------------------------------------------------------------------

        private static Dictionary<string, string> ParseDescriptionFields(string[] lines)
        {{
            var dict = new Dictionary<string, string>();
            foreach (var line in lines)
            {{
                var eq = line.IndexOf('=');
                if (eq <= 0) continue;
                dict[line.Substring(0, eq).Trim()] = line.Substring(eq + 1).Trim();
            }}
            return dict;
        }}

        private static DateTime ParseDate(string s)
        {{
            if (DateTime.TryParse(s, CultureInfo.InvariantCulture, DateTimeStyles.AssumeUniversal, out var dt))
                return dt;
            return DateTime.MinValue;
        }}

        private static decimal ParseDecimal(string s)
        {{
            return decimal.TryParse(s, NumberStyles.Any, CultureInfo.InvariantCulture, out var d) ? d : 0m;
        }}
    }}

    /// <summary>Extension helpers for hydrating a <see cref="Case"/> from its description field.</summary>
    internal static class CaseDescriptionParser
    {{
        public static Case WithDescriptionFields(this Case c, string description)
        {{
            var lines = (description ?? "").Split('\\n');
            foreach (var line in lines)
            {{
                var eq = line.IndexOf('=');
                if (eq <= 0) continue;
                var key = line.Substring(0, eq).Trim();
                var val = line.Substring(eq + 1).Trim();
                switch (key)
                {{
                    case "policy_number": c.PolicyNumber = val; break;
                    case "claimant_name": c.ClaimantName = val; break;
                    case "diagnosis_code": c.DiagnosisCode = val; break;
                    case "procedure_code": c.ProcedureCode = val; break;
                    case "total_amount":
                        if (decimal.TryParse(val, System.Globalization.NumberStyles.Any,
                            System.Globalization.CultureInfo.InvariantCulture, out var amt))
                            c.TotalAmount = amt;
                        break;
                    case "currency": c.Currency = val; break;
                    case "submitted_at":
                        if (DateTime.TryParse(val, System.Globalization.CultureInfo.InvariantCulture,
                            System.Globalization.DateTimeStyles.AssumeUniversal, out var dt))
                            c.SubmittedAt = dt;
                        break;
                    case "provider_npi": c.ProviderNpi = val; break;
                }}
            }}
            return c;
        }}
    }}
}}
"""
