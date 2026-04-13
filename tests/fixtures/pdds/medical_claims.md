# Medical Claims Adjudication Factory — PDD

## Process Overview

- **Name:** MedicalClaimsAdjudication
- **Type:** transactional
- **Topology:** dispatcher_performer_reporter
- **Description:** A fully-automated medical insurance claims adjudication pipeline running as a three-process UiPath factory on Community Cloud's Linux serverless robot. Cases originate in a self-hosted SuiteCRM 8 instance as the system of record; the robot factory pulls new-status cases, runs them through a 5-rule business engine, writes verdicts back to SuiteCRM, and emits an HTML SLA report.

## Systems

| Name       | Type | URL                       | Login Required |
|------------|------|---------------------------|----------------|
| SuiteCRM 8 | web  | ${SUITECRM_PUBLIC_URL}    | Yes            |

## Credentials

| Name               | Type       | Path                        | Description                                |
|--------------------|------------|-----------------------------|--------------------------------------------|
| SuiteCrmOAuthApp   | credential | Shared/SuiteCrmOAuthApp     | OAuth2 client_id + client_secret for SuiteCRM |
| SuiteCrmAdminUser  | credential | Shared/SuiteCrmAdminUser    | SuiteCRM admin username + password         |

## Transactions

### MedicalClaim

The factory processes one transaction type: `MedicalClaim`. Each claim is
queued as an Orchestrator queue item with `specific_content` containing:

  - `claim_id` (string)
  - `suitecrm_id` (string)
  - `payload_b64` (base64 of serialised Case) OR `payload_bucket_ref`
    if the payload exceeds 800 KiB (BW-10)

## Process Steps

### Dispatcher Steps

1. Authenticate to SuiteCRM via OAuth2 password grant
2. List Cases where `status = "New"` (page size = 50)
3. For each Case:
   a. Serialise the Case to JSON and base64-encode
   b. If >800 KiB, use bucket-ref fallback
   c. Push to the `MedicalClaims` queue via Orchestrator AddQueueItem
   d. PATCH the SuiteCRM Case status to `"Queued"`
4. Emit batch summary to stdout

### Performer Steps

1. Authenticate to SuiteCRM
2. Loop:
   a. StartTransaction on `MedicalClaims` — lease next item
   b. If null (queue drained), transition to End
   c. Decode payload_b64 or re-fetch Case by id (BW-10 fallback)
   d. Pre-fetch the Policy (for cheap in-memory CoverageVerification)
   e. Run the 5-rule engine
   f. UpdateCaseVerdictAsync on SuiteCRM with verdict + reason
   g. CreateAdjudicationNoteAsync on SuiteCRM (audit trail)
   h. SetTransactionResult(Successful, output={verdict, claim_id})
3. On BusinessException: SetTransactionResult(Failed, business_error=...)
4. On RpaSystemException: exponential-backoff retry, max 3

### Reporter Steps

1. Authenticate to Orchestrator
2. ListQueueItems on `MedicalClaims` (top=500)
3. Aggregate verdict counts (auto_approve / flag_for_review / deny / pending)
4. Render HTML SLA report with distribution + total
5. Emit to stdout wrapped in `<<<SLA_HTML_START>>>` / `<<<SLA_HTML_END>>>`
   markers for Python post-processing

## Business Rules

### Rule 1: CoverageVerification (deterministic, in-memory)

Deny the claim if the pre-fetched Policy's `CoverageEnd` is before the
claim's `SubmittedAt`, or `CoverageStart` is after.

### Rule 2: AmountThreshold (deterministic, in-memory)

- Amount > $100,000 → Deny (hard cap)
- Amount > $10,000 → FlagForReview
- Otherwise pass

### Rule 3: DocumentationCompleteness (live — SuiteCRM Notes)

Procedure codes starting with `992` (E&M levels) require ≥2 Notes attached;
others require ≥1. Otherwise Deny.

### Rule 4: NetworkProvider (live — SuiteCRM Accounts)

FlagForReview if the provider with the given NPI has `InNetwork = false`.

### Rule 5: FraudVelocity (live — SuiteCRM Cases, most expensive)

- ≥4 prior Cases for same claimant in last 30 days → Deny
- 2-3 prior Cases → FlagForReview
- Otherwise pass

## Configuration

| Name             | Value          | Description                               |
|------------------|----------------|-------------------------------------------|
| QueueName        | MedicalClaims  | Orchestrator queue name                   |
| MaxBatchSize     | 50             | Max items per Dispatcher run              |
| MaxPayloadBytes  | 819200         | Queue item payload limit (BW-10)          |
| ReviewThreshold  | 10000          | USD amount that flags for review          |
| HardCapThreshold | 100000         | USD amount that denies hard               |
| FraudVelocityWindowDays | 30      | Lookback window for fraud velocity rule   |

## Exception Handling

| Category               | Type     | Retry | Notes                              |
|------------------------|----------|-------|------------------------------------|
| SuiteCrmUnreachable    | system   | 3     | Exponential backoff on HTTP 5xx    |
| SuiteCrmAuthExpired    | system   | 1     | Token refresh + retry once         |
| CaseNotFoundInSuiteCrm | business | 0     | Skip with BusinessException        |
| PolicyNotFound         | business | 0     | Route to CoverageVerificationRule  |
| DuplicateClaim         | business | 0     | FraudVelocity caught it, Deny      |

## Target Runtime

UiPath Community Cloud, Linux serverless robot, .NET 8 Portable. All 12
v0.5 brick walls (`docs/community_cloud_limitations.md`) still apply plus
the 5 new ones (BW 13-17) documented for the multi-process pattern.
