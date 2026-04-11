# ISystemService API Reference

> **Namespace:** `UiPath.CodedWorkflows`
> **Injection:** `[Service] ISystemService system`

Provides system-level operations: logging, delays, credential management, asset
access, and Orchestrator queue operations. Available in all coded workflows via
the `[Service]` attribute.

---

## Logging

### Log

Writes a message to the UiPath execution log at the specified level.

```csharp
void Log(
    string message,
    LogLevel level = LogLevel.Info
);
```

**Log levels:** `Trace`, `Info`, `Warn`, `Error`, `Fatal`

**Example:**
```csharp
[Service] ISystemService system;

[Workflow]
public void ProcessItem(string itemId)
{
    system.Log($"Processing item: {itemId}", LogLevel.Info);

    try
    {
        // ... processing logic ...
        system.Log($"Item {itemId} processed successfully.", LogLevel.Info);
    }
    catch (Exception ex)
    {
        system.Log($"Error processing {itemId}: {ex.Message}", LogLevel.Error);
        throw;
    }
}
```

---

## Timing

### Delay

Pauses execution for the specified number of milliseconds.

```csharp
void Delay(int milliseconds);
```

**Example:**
```csharp
[Workflow]
public void WaitBetweenActions()
{
    system.Log("Waiting for page to stabilize...");
    system.Delay(2000); // 2-second pause
}
```

---

## Credential Management

### GetCredential

Retrieves a credential (username + secure password) from Orchestrator.

```csharp
Credential GetCredential(string credentialName);
```

**Returns:** A `Credential` object with `.Username` (string) and `.Password` (SecureString) properties.

**Example:**
```csharp
[Workflow]
public void LoginWithOrchestratorCredential()
{
    var cred = system.GetCredential("SAP_ServiceAccount");

    system.Log($"Logging in as: {cred.Username}");
    // Use cred.Username and cred.Password.ToString() for login
}
```

---

## Asset Management

### GetAsset

Retrieves an asset value from Orchestrator by name.

```csharp
T GetAsset<T>(string assetName);
// Common overloads:
string GetAsset(string assetName);          // Text asset
int GetAssetInt(string assetName);           // Integer asset
bool GetAssetBool(string assetName);         // Boolean asset
```

**Example:**
```csharp
[Workflow]
public void ConfigureFromAssets()
{
    string appUrl = system.GetAsset("InvoiceApp_URL");
    int maxRetries = system.GetAssetInt("MaxRetryCount");
    bool isProduction = system.GetAssetBool("IsProductionMode");

    system.Log($"Using URL: {appUrl}, Max Retries: {maxRetries}, Production: {isProduction}");
}
```

### SetAsset

Updates an asset value in Orchestrator.

```csharp
void SetAsset(string assetName, object value);
```

**Example:**
```csharp
[Workflow]
public void UpdateProcessStatus()
{
    system.SetAsset("LastProcessRunTime", DateTime.Now.ToString("yyyy-MM-dd HH:mm:ss"));
    system.SetAsset("ItemsProcessedCount", processedCount);
}
```

---

## Queue Operations

### AddQueueItem

Adds a new item to an Orchestrator queue.

```csharp
void AddQueueItem(
    string queueName,
    Dictionary<string, object> specificContent,
    AddQueueItemOptions? options = null
);
```

**Parameters:**
| Parameter | Type | Description |
|-----------|------|-------------|
| `queueName` | `string` | Name of the Orchestrator queue |
| `specificContent` | `Dictionary<string, object>` | Key-value data for the queue item |
| `options` | `AddQueueItemOptions?` | Optional: priority (High/Normal/Low), reference, deadline |

**Example:**
```csharp
[Workflow]
public void DispatchInvoice(string invoiceNumber, decimal amount, string vendor)
{
    var content = new Dictionary<string, object>
    {
        { "InvoiceNumber", invoiceNumber },
        { "Amount", amount },
        { "Vendor", vendor },
        { "SubmittedDate", DateTime.Now.ToString("yyyy-MM-dd") }
    };

    system.AddQueueItem("InvoiceProcessingQueue", content, new AddQueueItemOptions
    {
        Priority = QueueItemPriority.High,
        Reference = invoiceNumber
    });

    system.Log($"Added invoice {invoiceNumber} to queue.");
}
```

### GetQueueItem

Retrieves the next available queue item for processing (transaction item).

```csharp
QueueItem GetQueueItem(
    string queueName,
    GetQueueItemOptions? options = null
);
```

**Returns:** A `QueueItem` with `.SpecificContent` dictionary and `.Reference` string.
Returns `null` if no items are available.

**Example:**
```csharp
[Workflow]
public QueueItem GetNextTransaction()
{
    var item = system.GetQueueItem("InvoiceProcessingQueue");

    if (item == null)
    {
        system.Log("No more items in queue.", LogLevel.Info);
        return null;
    }

    system.Log($"Processing: {item.Reference} (ID: {item.Id})");
    return item;
}
```

### SetTransactionStatus

Sets the processing status of a queue item (Success, Failed, or Application Exception).

```csharp
void SetTransactionStatus(
    QueueItem item,
    TransactionStatus status,
    SetTransactionStatusOptions? options = null
);
```

**Parameters:**
| Parameter | Type | Description |
|-----------|------|-------------|
| `item` | `QueueItem` | The queue item to update |
| `status` | `TransactionStatus` | `Success`, `Failed`, or `ApplicationException` |
| `options` | `SetTransactionStatusOptions?` | Optional: reason string, exception details |

**Example:**
```csharp
[Workflow]
public void ProcessTransaction(QueueItem item)
{
    try
    {
        // ... business logic ...

        system.SetTransactionStatus(item, TransactionStatus.Success);
        system.Log($"Transaction {item.Reference} completed successfully.");
    }
    catch (BusinessRuleException brex)
    {
        system.SetTransactionStatus(item, TransactionStatus.Failed,
            new SetTransactionStatusOptions { Reason = brex.Message });
        system.Log($"Business exception: {brex.Message}", LogLevel.Warn);
    }
    catch (Exception ex)
    {
        system.SetTransactionStatus(item, TransactionStatus.ApplicationException,
            new SetTransactionStatusOptions { Reason = ex.Message });
        system.Log($"System exception: {ex.Message}", LogLevel.Error);
        throw; // Re-throw for retry logic
    }
}
```

---

## Common Patterns

### Full Queue Processing Loop

```csharp
[Service] ISystemService system;

[Workflow]
public void ProcessAllQueueItems(string queueName)
{
    QueueItem item;
    int successCount = 0;
    int failCount = 0;

    while ((item = system.GetQueueItem(queueName)) != null)
    {
        try
        {
            ProcessSingleItem(item);
            system.SetTransactionStatus(item, TransactionStatus.Success);
            successCount++;
        }
        catch (BusinessRuleException brex)
        {
            system.SetTransactionStatus(item, TransactionStatus.Failed,
                new SetTransactionStatusOptions { Reason = brex.Message });
            failCount++;
        }
        catch (Exception ex)
        {
            system.SetTransactionStatus(item, TransactionStatus.ApplicationException,
                new SetTransactionStatusOptions { Reason = ex.Message });
            failCount++;
        }
    }

    system.Log($"Queue processing complete. Success: {successCount}, Failed: {failCount}");
}
```
