"""Insurance domain pack."""

from rpa_architect.domains.base import DomainPack, ProcessTemplate

PACK = DomainPack(
    name="Insurance",
    industry="insurance",
    description="Automations for policy administration, claims adjudication, underwriting, and regulatory reporting.",
    knowledge_dir="domains/insurance",
    compliance_requirements=[
        "State insurance regulations compliance",
        "NAIC reporting requirements",
        "Data privacy regulations (CCPA, GDPR for international)",
        "Audit trail for underwriting decisions",
    ],
    templates=[
        ProcessTemplate(
            name="Policy Issuance",
            description="Automate new policy creation from application through binding.",
            process_type="transactional",
            systems=[
                {"name": "Policy Admin System", "type": "web"},
                {"name": "Rating Engine", "type": "api"},
                {"name": "Document Generation", "type": "web"},
            ],
            steps_outline=[
                "Receive application submission",
                "Extract applicant and risk information",
                "Run rating engine for premium calculation",
                "Apply underwriting rules",
                "Generate policy documents",
                "Issue policy and send to applicant",
                "Update policy admin system",
            ],
            config_defaults={
                "AutoBindThreshold": "10000",
                "UnderwritingRequired": "True",
            },
            tags=["policy", "issuance", "underwriting", "premium", "binding"],
        ),
        ProcessTemplate(
            name="Claims Adjudication",
            description="Process insurance claims from first notice of loss through settlement.",
            process_type="transactional",
            systems=[
                {"name": "Claims System", "type": "web"},
                {"name": "Policy Admin", "type": "web"},
                {"name": "Payment System", "type": "web"},
            ],
            steps_outline=[
                "Receive first notice of loss (FNOL)",
                "Validate policy coverage and dates",
                "Extract claim details and documentation",
                "Apply coverage rules and exclusions",
                "Calculate reserve and settlement amount",
                "Route complex claims to adjuster",
                "Process payment",
                "Generate settlement letter",
            ],
            config_defaults={
                "AutoSettleMax": "5000",
                "ReserveMultiplier": "1.5",
            },
            tags=["claims", "adjudication", "fnol", "settlement", "coverage", "loss"],
        ),
    ],
    business_rule_patterns=[
        {
            "name": "Auto-Settle Small Claims",
            "condition": "claim_amount <= auto_settle_max AND coverage_confirmed AND no_fraud_flags",
            "outcome": "auto_approve",
        },
        {
            "name": "Fraud Flag Escalation",
            "condition": "fraud_score > 0.7 OR suspicious_pattern_detected",
            "outcome": "escalate",
        },
    ],
)
