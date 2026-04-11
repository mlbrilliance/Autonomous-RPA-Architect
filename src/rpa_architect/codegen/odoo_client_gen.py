"""Generate the C# OdooClient — auth, partner lookup/create, bill create."""

from __future__ import annotations


def generate_odoo_client_cs(
    namespace: str = "OdooInvoiceProcessing",
    default_base_url: str = "http://localhost:8069",
) -> str:
    return f"""using System;
using System.Collections.Generic;
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
    /// Odoo JSON-RPC client for res.partner + account.move operations.
    /// Holds the session cookie across calls via an internal CookieContainer.
    /// </summary>
    public sealed class OdooClient
    {{
        private readonly HttpClient _http;
        private readonly string _baseUrl;
        private readonly string _db;
        private readonly string _login;
        private readonly string _password;
        private bool _authenticated;

        public OdooClient(string baseUrl, string db, string login, string password)
        {{
            _baseUrl = baseUrl.TrimEnd('/');
            _db = db;
            _login = login;
            _password = password;
            var handler = new HttpClientHandler {{ CookieContainer = new CookieContainer(), UseCookies = true }};
            _http = new HttpClient(handler) {{ Timeout = TimeSpan.FromSeconds(60) }};
            _http.DefaultRequestHeaders.Accept.Add(new MediaTypeWithQualityHeaderValue("application/json"));
        }}

        private async Task EnsureAuthenticatedAsync()
        {{
            if (_authenticated) return;
            var payload = JsonSerializer.Serialize(new
            {{
                jsonrpc = "2.0",
                method = "call",
                @params = new {{ db = _db, login = _login, password = _password }}
            }});
            var resp = await _http.PostAsync(
                $"{{_baseUrl}}/web/session/authenticate",
                new StringContent(payload, Encoding.UTF8, "application/json"));
            resp.EnsureSuccessStatusCode();
            var text = await resp.Content.ReadAsStringAsync();
            using var doc = JsonDocument.Parse(text);
            var result = doc.RootElement.TryGetProperty("result", out var r) ? r : default;
            if (result.ValueKind != JsonValueKind.Object ||
                !result.TryGetProperty("uid", out var uidEl) ||
                uidEl.ValueKind == JsonValueKind.Null)
            {{
                throw new InvalidOperationException($"Odoo auth failed: {{text}}");
            }}
            _authenticated = true;
            Console.WriteLine($"[OdooClient] authenticated uid={{uidEl.GetInt32()}}");
        }}

        private async Task<JsonElement> CallKwAsync(
            string model, string method, object[] args, object? kwargs = null)
        {{
            await EnsureAuthenticatedAsync();
            var payload = JsonSerializer.Serialize(new
            {{
                jsonrpc = "2.0",
                method = "call",
                @params = new
                {{
                    model = model,
                    method = method,
                    args = args,
                    kwargs = kwargs ?? new {{ }}
                }}
            }});
            var resp = await _http.PostAsync(
                $"{{_baseUrl}}/web/dataset/call_kw",
                new StringContent(payload, Encoding.UTF8, "application/json"));
            resp.EnsureSuccessStatusCode();
            var text = await resp.Content.ReadAsStringAsync();
            using var doc = JsonDocument.Parse(text);
            if (doc.RootElement.TryGetProperty("error", out var errEl))
                throw new InvalidOperationException($"Odoo RPC error: {{errEl.GetRawText()}}");
            // Clone so the returned element stays valid after doc dispose.
            return doc.RootElement.GetProperty("result").Clone();
        }}

        public async Task<int> FindPartnerByNameAsync(string name)
        {{
            var result = await CallKwAsync("res.partner", "search_read", new object[]
            {{
                new object[]
                {{
                    new object[] {{ "name", "=", name }}
                }},
                new[] {{ "id", "name" }},
            }}, new {{ limit = 1 }});
            if (result.ValueKind == JsonValueKind.Array && result.GetArrayLength() > 0)
                return result[0].GetProperty("id").GetInt32();
            return 0;
        }}

        public async Task<int> CreatePartnerAsync(string name, string email = "")
        {{
            var result = await CallKwAsync("res.partner", "create", new object[]
            {{
                new[]
                {{
                    new Dictionary<string, object>
                    {{
                        {{ "name", name }},
                        {{ "is_company", true }},
                        {{ "email", email }},
                        {{ "comment", "Auto-created by UiPath bot during invoice processing" }},
                    }}
                }}
            }});
            if (result.ValueKind == JsonValueKind.Array && result.GetArrayLength() > 0)
                return result[0].GetInt32();
            return result.GetInt32();
        }}

        public async Task<int> EnsurePartnerAsync(string name, string email = "")
        {{
            var existing = await FindPartnerByNameAsync(name);
            if (existing > 0) return existing;
            return await CreatePartnerAsync(name, email);
        }}

        public async Task<int> CountExistingBillsAsync(string reference, string vendorName)
        {{
            if (string.IsNullOrEmpty(reference)) return 0;
            var partnerId = await FindPartnerByNameAsync(vendorName);
            if (partnerId <= 0) return 0;
            var result = await CallKwAsync("account.move", "search_count", new object[]
            {{
                new object[]
                {{
                    new object[] {{ "move_type", "=", "in_invoice" }},
                    new object[] {{ "ref", "=", reference }},
                    new object[] {{ "partner_id", "=", partnerId }},
                }}
            }});
            return result.GetInt32();
        }}

        public async Task<(int billId, decimal total)> CreateVendorBillAsync(
            ExtractedDocument doc, int partnerId, List<(string name, int qty, decimal price)> lineItems)
        {{
            var lines = lineItems.Select(l => new object[]
            {{
                0, 0, new Dictionary<string, object>
                {{
                    {{ "name", l.name }},
                    {{ "quantity", l.qty }},
                    {{ "price_unit", l.price }},
                }}
            }}).ToArray();

            // Resolve the currency code to its Odoo id (and activate
            // non-USD currencies on demand — Odoo 17 ships them inactive).
            var currencyId = await FindCurrencyIdAsync(doc.Currency);
            if (currencyId > 0)
                await EnsureCurrencyActiveAsync(currencyId);

            var payload = new Dictionary<string, object>
            {{
                {{ "move_type", "in_invoice" }},
                {{ "partner_id", partnerId }},
                {{ "ref", doc.InvoiceNumber }},
                {{ "invoice_date", doc.InvoiceDate }},
                {{ "invoice_line_ids", lines }},
            }};
            if (currencyId > 0)
                payload["currency_id"] = currencyId;

            var created = await CallKwAsync("account.move", "create", new object[]
            {{
                new object[] {{ payload }}
            }});

            int billId;
            if (created.ValueKind == JsonValueKind.Array && created.GetArrayLength() > 0)
                billId = created[0].GetInt32();
            else
                billId = created.GetInt32();

            // Read back the computed total.
            var read = await CallKwAsync("account.move", "read", new object[]
            {{
                new[] {{ billId }},
                new[] {{ "amount_total" }}
            }});
            decimal total = 0;
            if (read.ValueKind == JsonValueKind.Array && read.GetArrayLength() > 0)
            {{
                var el = read[0];
                if (el.TryGetProperty("amount_total", out var at))
                    total = at.GetDecimal();
            }}
            return (billId, total);
        }}

        public async Task<int> CreateManagerApprovalTaskAsync(
            int billId, string vendorName, decimal amount, string currency, string reason)
        {{
            // Community tier: no Action Center. The correct Odoo pattern
            // is the ``activity_schedule`` helper on the target model —
            // it looks up the activity type xml_id and populates the
            // res_model_id / res_id / user_id fields correctly (direct
            // mail.activity create fails on res_model_id not-null
            // constraint, verified live).
            var summary = $"Manager approval — {{vendorName}} {{amount:F2}} {{currency}}";
            var note = $"<p>The UiPath bot flagged this bill for manager approval.</p>"
                     + $"<p><b>Reason:</b> {{reason}}</p>"
                     + $"<p>Vendor: {{vendorName}}<br/>Amount: {{amount:F2}} {{currency}}</p>";
            try
            {{
                var result = await CallKwAsync(
                    "account.move",
                    "activity_schedule",
                    new object[] {{ new[] {{ billId }}, "mail.mail_activity_data_todo" }},
                    new Dictionary<string, object>
                    {{
                        {{ "summary", summary }},
                        {{ "note", note }},
                    }});
                // activity_schedule returns a recordset string like
                // "mail.activity(8,)" — we don't need the id itself,
                // just confirm it was created.
                Console.WriteLine($"[OdooClient] scheduled activity on bill {{billId}}: {{summary}}");
                return 1;  // sentinel: success
            }}
            catch (Exception ex)
            {{
                Console.WriteLine($"[OdooClient] activity_schedule failed on bill {{billId}}: {{ex.Message}}");
                return 0;
            }}
        }}

        public async Task<int> FindCurrencyIdAsync(string code)
        {{
            // Currencies are inactive by default in Odoo 17 until used.
            // Use active_test=false in context so we find them.
            var result = await CallKwAsync(
                "res.currency",
                "search_read",
                new object[]
                {{
                    new object[] {{ new object[] {{ "name", "=", code }} }},
                    new[] {{ "id", "name" }}
                }},
                new Dictionary<string, object>
                {{
                    {{ "limit", 1 }},
                    {{ "context", new Dictionary<string, object> {{ {{ "active_test", false }} }} }}
                }});
            if (result.ValueKind == JsonValueKind.Array && result.GetArrayLength() > 0)
                return result[0].GetProperty("id").GetInt32();
            return 0;
        }}

        public async Task EnsureCurrencyActiveAsync(int currencyId)
        {{
            if (currencyId <= 0) return;
            try
            {{
                await CallKwAsync("res.currency", "write", new object[]
                {{
                    new[] {{ currencyId }},
                    new Dictionary<string, object> {{ {{ "active", true }} }}
                }});
            }}
            catch (Exception ex)
            {{
                Console.WriteLine($"[OdooClient] activate currency {{currencyId}} failed: {{ex.Message}}");
            }}
        }}
    }}
}}
"""
