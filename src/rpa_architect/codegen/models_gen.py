"""Generate the Models and ProcessContext C# files that underpin the state machine.

These are simple DTOs + a ProcessContext that carries per-run state
(config, metrics, in-flight transaction). Kept small so the compiled
DLL stays under 100 KB.
"""

from __future__ import annotations


def generate_process_config_cs(namespace: str = "OdooInvoiceProcessing") -> str:
    return f"""using System.Collections.Generic;

namespace {namespace}
{{
    public sealed class ProcessConfig
    {{
        public string OdooBaseUrl {{ get; set; }} = "http://localhost:8069";
        public string OdooLogin {{ get; set; }} = "admin";
        public string OdooPassword {{ get; set; }} = "admin";
        public string OdooDb {{ get; set; }} = "odoo";
        public decimal AmountThresholdUsd {{ get; set; }} = 10000m;
        public List<string> AllowedCurrencies {{ get; set; }} = new() {{ "USD", "EUR", "GBP" }};
        public int MaxRetries {{ get; set; }} = 3;
        public bool UseLiveDuApi {{ get; set; }} = false;
        public string? DuProjectId {{ get; set; }}
    }}
}}
"""


def generate_batch_metrics_cs(namespace: str = "OdooInvoiceProcessing") -> str:
    return f"""using System.Collections.Generic;

namespace {namespace}
{{
    public sealed class BatchMetrics
    {{
        public int TotalInvoices {{ get; set; }}
        public int Processed {{ get; set; }}
        public int Flagged {{ get; set; }}
        public int Rejected {{ get; set; }}
        public int BusinessExceptions {{ get; set; }}
        public int SystemExceptions {{ get; set; }}
        public decimal TotalValueUsd {{ get; set; }}
        public List<int> CreatedBillIds {{ get; set; }} = new();
        public List<string> PerInvoiceLogs {{ get; set; }} = new();
        public Dictionary<string, int> ByVendor {{ get; set; }} = new();
        public string Source {{ get; set; }} = "local.groundtruth";
    }}
}}
"""


def generate_process_context_cs(namespace: str = "OdooInvoiceProcessing") -> str:
    return f"""using System.Collections.Generic;

namespace {namespace}
{{
    /// <summary>
    /// Per-run state passed between REFramework-pattern states.
    /// </summary>
    public sealed class ProcessContext
    {{
        public ProcessConfig Config {{ get; set; }} = new();
        public BatchMetrics Metrics {{ get; set; }} = new();
        public OdooClient Odoo {{ get; set; }} = null!;
        public DocumentUnderstandingClient? DuClient {{ get; set; }}
        public LocalInvoiceExtractor LocalExtractor {{ get; set; }} = new();
        public BusinessRuleEngine Rules {{ get; set; }} = new();
        public int CurrentIndex {{ get; set; }}
        public int RetryCount {{ get; set; }}
        public List<EmbeddedInvoice> Queue {{ get; set; }} = new();
        public EmbeddedInvoice? CurrentInvoice {{ get; set; }}
        public ExtractedDocument? CurrentExtraction {{ get; set; }}
        public RuleChainResult? CurrentRuleResult {{ get; set; }}
    }}
}}
"""
