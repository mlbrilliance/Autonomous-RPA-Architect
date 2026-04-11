# REFramework Patterns

## Overview

The Robotic Enterprise Framework (REFramework) is UiPath's production-grade template for building transactional automations. It provides a state machine with four states: Init, Get Transaction Data, Process Transaction, and End Process.

REFramework is designed for queue-based processing but can be adapted for any data source (Excel, database, API). It handles retry logic, exception classification, logging, and application lifecycle management.

---

## Architecture: State Machine

```
[Init] --> [Get Transaction Data] --> [Process Transaction] --> [Get Transaction Data]
  |              |                          |                         |
  v              v                          v                         v
[End Process] <-- (no more items) <-- (on exception) --> [Init] (retry)
```

### State Transitions

| From | To | Condition |
|------|----|-----------|
| Init | Get Transaction Data | Initialization succeeded |
| Init | End Process | Initialization failed (SystemException) |
| Get Transaction Data | Process Transaction | Transaction item retrieved |
| Get Transaction Data | End Process | No more items (TransactionItem is Nothing) |
| Process Transaction | Get Transaction Data | Processing succeeded |
| Process Transaction | Init | System exception (triggers retry after re-init) |
| Process Transaction | Get Transaction Data | Business exception (skip item, get next) |

---

## Phase 1: Init

The Init state prepares the environment for processing. It runs once at startup and again after any system exception during processing.

### What Happens in Init

1. **KillAllProcesses.xaml** (called first): Kills existing app instances to ensure a clean slate.
2. **InitAllSettings.xaml**: Reads Config.xlsx into a `Dictionary<string, object>`.
   - Settings sheet: environment-specific values (URLs, credentials, queue names)
   - Constants sheet: values that do not change between environments
   - Assets sheet: Orchestrator asset names to fetch at runtime
3. **InitAllApplications.xaml**: Opens and logs into target applications.

### Config.xlsx Structure

```
Config.xlsx
+-- Settings sheet (Name, Value, Description)
|   +-- OrchestratorQueueName = "InvoiceProcessing"
|   +-- MaxRetryNumber = 3
|   +-- logF_BusinessProcessName = "Invoice Bot"
|   +-- ApplicationUrl = "https://app.example.com"
|   +-- TimeoutSeconds = 30
+-- Constants sheet (Name, Value, Description)
|   +-- MaxTransactionsPerRun = 500
|   +-- ReportEmailRecipients = "team@example.com"
+-- Assets sheet (Name, OrchestratorAssetName, Description)
    +-- ApplicationCredential = "InvoiceBot_Credential"
    +-- ApiKey = "InvoiceBot_ApiKey"
```

### Retry-Aware Init

On a system exception, the framework transitions back to Init before retrying. The Init state must handle this gracefully:
- Close applications that may be in an unknown state
- Re-open fresh application instances
- Navigate to the correct starting position

### Init Pattern in C#

```csharp
[Workflow]
public void InitAllApplications(Dictionary<string, object> config)
{
    Log("Initializing applications...", LogLevel.Info);

    // Kill any leftover processes
    KillAllProcesses();

    // Open and login to each application
    string appUrl = config["ApplicationUrl"]?.ToString();
    var credential = GetCredential(config["ApplicationCredential"]?.ToString());

    OpenBrowser(appUrl);
    Login(credential.Username, credential.Password);

    Log("All applications initialized.", LogLevel.Info);
}
```

---

## Phase 2: Get Transaction Data

Retrieves the next transaction item to process.

### Queue-Based Pattern (Default)

```csharp
[Workflow]
public QueueItem GetTransactionData(Dictionary<string, object> config, int transactionNumber)
{
    string queueName = config["OrchestratorQueueName"]?.ToString();
    QueueItem item = Orchestrator.GetQueueItem(queueName);

    if (item != null)
    {
        Log($"Retrieved transaction #{transactionNumber}: {item.Reference}", LogLevel.Info);
    }
    else
    {
        Log("No more items in the queue.", LogLevel.Info);
    }

    return item; // null signals end of processing
}
```

### Alternative Data Sources

**Excel/DataTable Pattern:**
```csharp
if (transactionNumber < dataTable.Rows.Count)
    return dataTable.Rows[transactionNumber]; // cast to TransactionItem equivalent
else
    return null; // signals end of processing
```

**Database Pattern:**
```csharp
var row = db.QueryFirstOrDefault("SELECT TOP 1 * FROM Transactions WHERE Status='Pending'");
if (row != null)
    db.Execute("UPDATE Transactions SET Status='Processing' WHERE Id=@Id", row.Id);
return row;
```

**API Pattern:**
```csharp
var response = httpClient.Get("/api/tasks?status=pending&limit=1");
if (response.Items.Any())
{
    httpClient.Patch($"/api/tasks/{response.Items[0].Id}", new { status = "in_progress" });
    return response.Items[0];
}
return null;
```

---

## Phase 3: Process Transaction

Executes the business logic for a single transaction item.

### Processing Pattern

```csharp
[Workflow]
public void ProcessTransaction(QueueItem item, Dictionary<string, object> config)
{
    string reference = item.Reference;
    Log($"Processing: {reference}", LogLevel.Info);

    // Step 1: Extract and validate data
    var dto = InvoiceDto.FromQueueItem(item);
    ValidateBusinessRules(dto);

    // Step 2: Perform automation steps
    NavigateToInvoicePage();
    EnterInvoiceData(dto);
    SubmitInvoice();

    // Step 3: Verify results
    VerifySubmissionSuccess(dto.InvoiceNumber);

    Log($"Completed: {reference}", LogLevel.Info);
}
```

### Exception Handling

**BusinessRuleException** -- data issues that retrying will NOT fix:
```csharp
// Validation failures
throw new BusinessRuleException("Invoice number is empty.");
throw new BusinessRuleException($"Amount {amount} exceeds limit of 1,000,000.");
throw new BusinessRuleException("Duplicate invoice detected.");
```

**System Exception** -- infrastructure issues that MAY be fixed by retrying:
```csharp
// Let these propagate naturally:
// - SelectorNotFoundException (element not found)
// - TimeoutException (app not responding)
// - WebException (network issue)
// The REFramework will catch them and trigger retry via Init
```

### Decision Rule

```
Is the error caused by the data itself?
  YES -> BusinessRuleException (do NOT retry)
  NO  -> System Exception (retry via Init)

Would a human operator get the same error on retry?
  YES -> BusinessRuleException
  NO  -> System Exception
```

---

## Phase 4: End Process

Cleanup phase after all items are processed or after an unrecoverable Init failure.

### End Process Pattern

```csharp
[Workflow]
public void EndProcess(Dictionary<string, object> config, int successCount, int failCount)
{
    // Step 1: Close all applications gracefully
    try { CloseAllApplications(); }
    catch (Exception ex) { Log($"Cleanup warning: {ex.Message}", LogLevel.Warn); }

    // Step 2: Force-kill any remaining processes
    KillAllProcesses();

    // Step 3: Log summary
    int total = successCount + failCount;
    Log($"Process ended. Total: {total}, Success: {successCount}, Failed: {failCount}",
        LogLevel.Info);

    // Step 4: Send notification
    string notifyEmail = config["NotificationEmail"]?.ToString();
    if (!string.IsNullOrEmpty(notifyEmail))
        SendSummaryEmail(notifyEmail, successCount, failCount);
}
```

---

## Exception Handling Patterns

### Retry Logic

The REFramework retries system exceptions automatically:

```
On System Exception:
  1. Set queue item status to ApplicationException
  2. Transition to Init (re-initialize applications)
  3. Orchestrator makes the item available again (RetryNo incremented)
  4. Get Transaction Data retrieves the same item
  5. Process Transaction tries again

  If RetryNo >= MaxRetryNumber:
    - Item is marked as permanently Failed
    - Processing moves to the next item
```

### Custom Exception Types

```csharp
// Business rule violations (never retried)
throw new BusinessRuleException("Invoice amount exceeds approval limit.");
throw new BusinessRuleException("Customer account is inactive.");

// System exceptions with added context (retried)
throw new Exception($"Login failed for user {username}", innerException);
throw new Exception($"SAP transaction {tcode} timed out", innerException);
```

---

## Config Management Patterns

### Environment-Specific Settings

Use the Settings sheet for values that differ between environments:

| Name | DEV Value | PROD Value |
|------|-----------|------------|
| ApplicationUrl | https://dev.app.com | https://app.com |
| OrchestratorQueueName | InvoiceBot_DEV | InvoiceBot_PROD |
| MaxRetryNumber | 1 | 3 |

### Orchestrator Assets for Secrets

For credentials and API keys, reference Orchestrator assets:

| Name | OrchestratorAssetName |
|------|----------------------|
| AppCredential | InvoiceBot_Credential |
| ApiKey | InvoiceBot_ApiKey |

### Strongly-Typed Config Wrapper

Instead of `config["SettingName"].ToString()` everywhere:

```csharp
var cfg = new ProcessConfig(configDictionary);
string url = cfg.ApplicationUrl;        // type-safe string
int timeout = cfg.TimeoutSeconds;       // parsed int with default
bool notify = cfg.SendNotifications;    // parsed bool with default
```

See `templates/config_model.cs.j2` for the generation template.

---

## Logging Patterns

### Standard Log Fields

```
logF_BusinessProcessName = "Invoice Processing Bot"
```

### Recommended Log Points

| Location | Level | Content |
|----------|-------|---------|
| Init start | Info | "Process starting. Config loaded." |
| App open | Info | "Application opened: {appName}" |
| Get transaction | Trace | "Retrieved transaction #{n}: {reference}" |
| Process start | Info | "Processing: {reference}" |
| Process success | Info | "Completed: {reference} in {duration}s" |
| Business exception | Warn | "Business rule: {message} for {reference}" |
| System exception | Error | "System error: {message} for {reference}" |
| End process | Info | "Process ended. Total: {n}, Success: {s}, Failed: {f}" |

---

## Performance Patterns

### Batch Processing

For high-volume scenarios, group items by target system to minimize application switches:

```
1. Get batch of N items from queue
2. Group by target system or operation type
3. Open each system once, process all related items
4. Close systems after batch
```

### Parallel Processing

Deploy multiple robots processing the same queue:

```
Queue: InvoiceProcessing (shared)
Robot 1: Gets item A, processes A
Robot 2: Gets item B, processes B (simultaneously)
```

Orchestrator manages queue locking so no two robots get the same item.
