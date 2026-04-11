"""Healthcare domain pack."""

from rpa_architect.domains.base import DomainPack, ProcessTemplate

PACK = DomainPack(
    name="Healthcare",
    industry="healthcare",
    description="Automations for claims processing, patient intake, clinical data management, and medical billing.",
    knowledge_dir="domains/healthcare",
    compliance_requirements=[
        "HIPAA compliance for all patient data handling",
        "HL7/FHIR standards for clinical data interchange",
        "Audit trail for clinical record modifications",
        "PHI encryption in transit and at rest",
    ],
    templates=[
        ProcessTemplate(
            name="Claims Processing",
            description="Process insurance claims from submission through adjudication.",
            process_type="transactional",
            systems=[
                {"name": "Claims Portal", "type": "web"},
                {"name": "EHR", "type": "web"},
                {"name": "Payer Portal", "type": "web"},
            ],
            steps_outline=[
                "Receive claim submission (EDI 837 or portal)",
                "Verify patient eligibility and coverage",
                "Validate diagnosis and procedure codes (ICD-10, CPT)",
                "Apply medical necessity rules",
                "Check for duplicate claims",
                "Calculate reimbursement based on fee schedule",
                "Route exceptions to medical review",
                "Generate EOB and remittance advice",
            ],
            config_defaults={
                "AutoAdjudicateThreshold": "500",
                "DuplicateWindowDays": "30",
            },
            tags=["claims", "adjudication", "insurance", "medical", "health", "payer"],
        ),
        ProcessTemplate(
            name="Patient Intake",
            description="Automate patient registration, insurance verification, and scheduling.",
            process_type="linear",
            systems=[
                {"name": "EHR", "type": "web"},
                {"name": "Insurance Verification", "type": "api"},
                {"name": "Scheduling System", "type": "web"},
            ],
            steps_outline=[
                "Receive patient registration form",
                "Extract demographics and insurance info",
                "Verify insurance eligibility via API",
                "Check for existing patient record (dedup)",
                "Create or update patient record in EHR",
                "Schedule appointment",
                "Generate welcome packet",
            ],
            config_defaults={
                "VerificationTimeout": "30",
                "DedupMatchThreshold": "0.85",
            },
            tags=["patient", "intake", "registration", "ehr", "scheduling", "eligibility"],
        ),
    ],
    business_rule_patterns=[
        {
            "name": "Auto-Adjudication",
            "condition": "claim_amount <= threshold AND codes_valid AND coverage_active",
            "outcome": "auto_approve",
        },
        {
            "name": "Medical Review Required",
            "condition": "prior_auth_required OR experimental_treatment",
            "outcome": "escalate",
        },
    ],
)
