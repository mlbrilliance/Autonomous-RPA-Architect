"""Financial services domain pack."""

from rpa_architect.domains.base import DomainPack, ProcessTemplate

PACK = DomainPack(
    name="Financial Services",
    industry="finance",
    description="Automations for banking, lending, accounts payable/receivable, and financial reconciliation.",
    knowledge_dir="domains/finance",
    compliance_requirements=[
        "SOX compliance for financial reporting automations",
        "PCI-DSS for payment card data handling",
        "KYC/AML for customer verification processes",
        "Audit trail required for all financial transactions",
    ],
    templates=[
        ProcessTemplate(
            name="Invoice Processing",
            description="Extract, validate, and post vendor invoices to ERP systems.",
            process_type="transactional",
            systems=[
                {"name": "Email", "type": "email"},
                {"name": "ERP", "type": "web"},
                {"name": "Document Management", "type": "web"},
            ],
            steps_outline=[
                "Monitor inbox for new invoices",
                "Extract invoice data (vendor, amount, line items, dates)",
                "Validate against PO and vendor master",
                "Apply 3-way match (PO, receipt, invoice)",
                "Post to ERP accounts payable",
                "Archive to document management system",
                "Handle exceptions (mismatches, missing POs)",
            ],
            config_defaults={
                "InvoiceThreshold": "5000",
                "MatchTolerance": "0.01",
                "ApprovalRequired": "True",
            },
            tags=["invoice", "ap", "accounts payable", "vendor", "procurement"],
        ),
        ProcessTemplate(
            name="Bank Reconciliation",
            description="Reconcile bank statements against general ledger entries.",
            process_type="transactional",
            systems=[
                {"name": "Banking Portal", "type": "web"},
                {"name": "ERP", "type": "web"},
            ],
            steps_outline=[
                "Download bank statement (CSV/PDF)",
                "Parse statement transactions",
                "Match against GL entries by amount, date, reference",
                "Flag unmatched transactions",
                "Generate reconciliation report",
                "Post adjusting entries if needed",
            ],
            config_defaults={
                "MatchWindowDays": "3",
                "AmountTolerance": "0.01",
            },
            tags=["reconciliation", "bank", "ledger", "gl", "statement"],
        ),
        ProcessTemplate(
            name="Loan Origination QA",
            description="Quality assurance checks on mortgage/loan applications.",
            process_type="transactional",
            systems=[
                {"name": "LOS", "type": "web"},
                {"name": "Core Banking", "type": "web"},
                {"name": "Document Management", "type": "web"},
            ],
            steps_outline=[
                "Retrieve loan application from LOS",
                "Verify borrower identity documents",
                "Check income/employment verification",
                "Validate loan-to-value calculations",
                "Cross-check against compliance rules",
                "Flag defects for human review",
                "Generate QA audit report",
            ],
            config_defaults={
                "MaxLTV": "0.80",
                "DefectSeverityThreshold": "Critical",
            },
            tags=["loan", "mortgage", "origination", "qa", "lending", "compliance"],
        ),
    ],
    business_rule_patterns=[
        {
            "name": "Three-Way Match",
            "condition": "abs(invoice_amount - po_amount) <= tolerance AND receipt_confirmed",
            "outcome": "auto_approve",
        },
        {
            "name": "Amount Threshold Escalation",
            "condition": "invoice_amount > threshold",
            "outcome": "escalate",
        },
    ],
)
