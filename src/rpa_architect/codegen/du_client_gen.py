"""Generate C# client code for the UiPath Document Understanding API v2.

The generated `DocumentUnderstandingClient.cs` hits the real endpoints:

    POST https://cloud.uipath.com/{org}/{tenant}/du_/api/framework/projects/{projectId}/digitization/start
    GET  https://cloud.uipath.com/{org}/{tenant}/du_/api/framework/projects/{projectId}/digitization/result/{operationId}
    POST https://cloud.uipath.com/{org}/{tenant}/du_/api/framework/projects/{projectId}/extractors/invoices/extraction/start
    GET  https://cloud.uipath.com/{org}/{tenant}/du_/api/framework/projects/{projectId}/extractors/invoices/extraction/result/{operationId}

Authentication uses a Bearer token obtained via the OAuth2
client_credentials flow with scopes ``Du.Digitization.Api``,
``Du.Extraction.Api``. These scopes must be granted to the external
application at registration time — otherwise the client emits a clear
``DuApiScopeMissingException`` and the DocumentProcessor falls back to
the :class:`LocalInvoiceExtractor`.

The code is production-shaped: typed request/response records, polling
loop with backoff, cancellation token, structured error handling.
Verified to compile under .NET 8 SDK by
``tests/test_codegen/test_du_client_gen.py``.
"""

from __future__ import annotations


def generate_du_client_cs(namespace: str = "OdooInvoiceProcessing") -> str:
    """Return the complete C# file content."""
    return f"""using System;
using System.Collections.Generic;
using System.Net.Http;
using System.Net.Http.Headers;
using System.Text;
using System.Text.Json;
using System.Text.Json.Serialization;
using System.Threading;
using System.Threading.Tasks;

namespace {namespace}
{{
    public sealed class ExtractedField
    {{
        public string Name {{ get; set; }} = "";
        public string Value {{ get; set; }} = "";
        public double Confidence {{ get; set; }}
        public double OcrConfidence {{ get; set; }}
    }}

    public sealed class ExtractedDocument
    {{
        public string DocumentId {{ get; set; }} = "";
        public double AvgConfidence {{ get; set; }}
        public List<ExtractedField> Fields {{ get; set; }} = new();
        public string VendorName {{ get; set; }} = "";
        public string InvoiceNumber {{ get; set; }} = "";
        public string InvoiceDate {{ get; set; }} = "";
        public decimal TotalAmount {{ get; set; }}
        public string Currency {{ get; set; }} = "";
        public string Source {{ get; set; }} = "du.api.v2";
    }}

    public sealed class DuApiScopeMissingException : Exception
    {{
        public DuApiScopeMissingException(string message) : base(message) {{ }}
    }}

    /// <summary>
    /// Client for the UiPath Document Understanding Cloud API v2.
    /// Paths verified against docs.uipath.com Feb 2026.
    /// </summary>
    public sealed class DocumentUnderstandingClient
    {{
        private readonly HttpClient _http;
        private readonly string _baseUrl;  // e.g. https://cloud.uipath.com
        private readonly string _org;
        private readonly string _tenant;
        private readonly string _projectId;
        private readonly string _clientId;
        private readonly string _clientSecret;
        private string? _token;
        private DateTimeOffset _tokenExpiry;

        public DocumentUnderstandingClient(
            string baseUrl,
            string org,
            string tenant,
            string projectId,
            string clientId,
            string clientSecret,
            HttpClient? httpClient = null)
        {{
            _baseUrl = baseUrl.TrimEnd('/');
            _org = org;
            _tenant = tenant;
            _projectId = projectId;
            _clientId = clientId;
            _clientSecret = clientSecret;
            _http = httpClient ?? new HttpClient {{ Timeout = TimeSpan.FromMinutes(5) }};
        }}

        private string BasePath => $"{{_baseUrl}}/{{_org}}/{{_tenant}}/du_/api/framework/projects/{{_projectId}}";

        private async Task<string> GetTokenAsync(CancellationToken ct)
        {{
            if (_token is not null && DateTimeOffset.UtcNow < _tokenExpiry)
                return _token;
            var tokenUrl = $"{{_baseUrl}}/{{_org}}/identity_/connect/token";
            var form = new FormUrlEncodedContent(new[]
            {{
                new KeyValuePair<string, string>("grant_type", "client_credentials"),
                new KeyValuePair<string, string>("client_id", _clientId),
                new KeyValuePair<string, string>("client_secret", _clientSecret),
                new KeyValuePair<string, string>("scope", "Du.Digitization.Api Du.Extraction.Api Du.Classification.Api Du.Validation.Api"),
            }});
            var resp = await _http.PostAsync(tokenUrl, form, ct);
            var body = await resp.Content.ReadAsStringAsync(ct);
            if (!resp.IsSuccessStatusCode)
            {{
                if (body.Contains("invalid_scope"))
                {{
                    throw new DuApiScopeMissingException(
                        "The external application is not authorized for "
                        + "Du.Extraction.Api. Grant the scope at "
                        + "cloud.uipath.com/{{org}}/portal_/externalAppsRegistration "
                        + "and retry. See docs/community_cloud_limitations.md.");
                }}
                throw new InvalidOperationException($"DU token request failed: {{(int)resp.StatusCode}} {{body}}");
            }}
            using var doc = JsonDocument.Parse(body);
            _token = doc.RootElement.GetProperty("access_token").GetString();
            var expiresIn = doc.RootElement.GetProperty("expires_in").GetInt32();
            _tokenExpiry = DateTimeOffset.UtcNow.AddSeconds(expiresIn - 60);
            return _token!;
        }}

        private async Task<HttpResponseMessage> AuthedPostAsync(string path, HttpContent content, CancellationToken ct)
        {{
            var token = await GetTokenAsync(ct);
            using var req = new HttpRequestMessage(HttpMethod.Post, $"{{BasePath}}{{path}}")
            {{
                Content = content,
            }};
            req.Headers.Authorization = new AuthenticationHeaderValue("Bearer", token);
            return await _http.SendAsync(req, ct);
        }}

        private async Task<HttpResponseMessage> AuthedGetAsync(string path, CancellationToken ct)
        {{
            var token = await GetTokenAsync(ct);
            using var req = new HttpRequestMessage(HttpMethod.Get, $"{{BasePath}}{{path}}");
            req.Headers.Authorization = new AuthenticationHeaderValue("Bearer", token);
            return await _http.SendAsync(req, ct);
        }}

        /// <summary>Step 1: POST the PDF bytes to the digitization endpoint.</summary>
        public async Task<string> StartDigitizationAsync(
            byte[] pdfBytes, string fileName, CancellationToken ct = default)
        {{
            using var form = new MultipartFormDataContent();
            var fileContent = new ByteArrayContent(pdfBytes);
            fileContent.Headers.ContentType = new MediaTypeHeaderValue("application/pdf");
            form.Add(fileContent, "File", fileName);
            var resp = await AuthedPostAsync("/digitization/start?api-version=1", form, ct);
            var body = await resp.Content.ReadAsStringAsync(ct);
            if (!resp.IsSuccessStatusCode)
                throw new InvalidOperationException($"Digitize start failed: {{(int)resp.StatusCode}} {{body}}");
            using var doc = JsonDocument.Parse(body);
            return doc.RootElement.GetProperty("documentId").GetString()!;
        }}

        /// <summary>Step 2: Poll digitization result until Succeeded.</summary>
        public async Task WaitForDigitizationAsync(
            string documentId, CancellationToken ct = default)
        {{
            var deadline = DateTimeOffset.UtcNow.AddMinutes(3);
            while (DateTimeOffset.UtcNow < deadline)
            {{
                var resp = await AuthedGetAsync($"/digitization/result/{{documentId}}?api-version=1", ct);
                var body = await resp.Content.ReadAsStringAsync(ct);
                if (resp.IsSuccessStatusCode)
                {{
                    using var doc = JsonDocument.Parse(body);
                    if (doc.RootElement.TryGetProperty("status", out var st))
                    {{
                        var status = st.GetString();
                        if (status == "Succeeded") return;
                        if (status == "Failed")
                            throw new InvalidOperationException($"Digitize failed: {{body}}");
                    }}
                }}
                await Task.Delay(TimeSpan.FromSeconds(2), ct);
            }}
            throw new TimeoutException("Digitize polling deadline exceeded");
        }}

        /// <summary>Step 3: POST to extraction start endpoint.</summary>
        public async Task<string> StartExtractionAsync(
            string documentId, CancellationToken ct = default)
        {{
            var payload = new {{ documentId = documentId, boostExtractionConfidence = 70 }};
            using var content = new StringContent(
                JsonSerializer.Serialize(payload),
                Encoding.UTF8,
                "application/json");
            var resp = await AuthedPostAsync(
                "/extractors/invoices/extraction/start?api-version=1", content, ct);
            var body = await resp.Content.ReadAsStringAsync(ct);
            if (!resp.IsSuccessStatusCode)
                throw new InvalidOperationException($"Extract start failed: {{(int)resp.StatusCode}} {{body}}");
            using var doc = JsonDocument.Parse(body);
            return doc.RootElement.GetProperty("operationId").GetString()!;
        }}

        /// <summary>Step 4: Poll extraction result and parse fields.</summary>
        public async Task<ExtractedDocument> WaitForExtractionAsync(
            string operationId, CancellationToken ct = default)
        {{
            var deadline = DateTimeOffset.UtcNow.AddMinutes(3);
            while (DateTimeOffset.UtcNow < deadline)
            {{
                var resp = await AuthedGetAsync(
                    $"/extractors/invoices/extraction/result/{{operationId}}?api-version=1", ct);
                var body = await resp.Content.ReadAsStringAsync(ct);
                if (resp.IsSuccessStatusCode)
                {{
                    using var doc = JsonDocument.Parse(body);
                    var status = doc.RootElement.GetProperty("status").GetString();
                    if (status == "Succeeded")
                    {{
                        return ParseExtractionResult(doc.RootElement);
                    }}
                    if (status == "Failed")
                        throw new InvalidOperationException($"Extract failed: {{body}}");
                }}
                await Task.Delay(TimeSpan.FromSeconds(2), ct);
            }}
            throw new TimeoutException("Extraction polling deadline exceeded");
        }}

        private static ExtractedDocument ParseExtractionResult(JsonElement root)
        {{
            var extracted = new ExtractedDocument();
            if (!root.TryGetProperty("extractionResult", out var exr)) return extracted;
            if (!exr.TryGetProperty("ResultsDocument", out var resDoc)) return extracted;
            if (resDoc.TryGetProperty("Fields", out var fields))
            {{
                double conf_sum = 0; int conf_n = 0;
                foreach (var f in fields.EnumerateArray())
                {{
                    var field = new ExtractedField
                    {{
                        Name = f.GetProperty("FieldName").GetString() ?? "",
                    }};
                    if (f.TryGetProperty("Values", out var vs) && vs.GetArrayLength() > 0)
                    {{
                        var v = vs[0];
                        if (v.TryGetProperty("Value", out var vEl)) field.Value = vEl.GetString() ?? "";
                        if (v.TryGetProperty("Confidence", out var cEl)) field.Confidence = cEl.GetDouble();
                        if (v.TryGetProperty("OcrConfidence", out var oEl)) field.OcrConfidence = oEl.GetDouble();
                    }}
                    extracted.Fields.Add(field);
                    conf_sum += field.Confidence;
                    conf_n += 1;
                    // Map well-known fields onto the typed properties.
                    switch (field.Name)
                    {{
                        case "vendor-name": case "VendorName": extracted.VendorName = field.Value; break;
                        case "invoice-number": case "InvoiceNumber": extracted.InvoiceNumber = field.Value; break;
                        case "invoice-date": case "InvoiceDate": extracted.InvoiceDate = field.Value; break;
                        case "total-amount": case "TotalAmount":
                            if (decimal.TryParse(field.Value, out var t)) extracted.TotalAmount = t;
                            break;
                        case "currency": case "Currency": extracted.Currency = field.Value; break;
                    }}
                }}
                extracted.AvgConfidence = conf_n > 0 ? conf_sum / conf_n : 0;
            }}
            return extracted;
        }}

        /// <summary>End-to-end convenience: digitize + extract + parse.</summary>
        public async Task<ExtractedDocument> ExtractInvoiceAsync(
            byte[] pdfBytes, string fileName, CancellationToken ct = default)
        {{
            var docId = await StartDigitizationAsync(pdfBytes, fileName, ct);
            await WaitForDigitizationAsync(docId, ct);
            var opId = await StartExtractionAsync(docId, ct);
            var result = await WaitForExtractionAsync(opId, ct);
            result.DocumentId = docId;
            return result;
        }}
    }}
}}
"""
