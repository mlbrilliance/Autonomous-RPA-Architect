# Hybrid Integration: Coded C# Workflows with XAML REFramework

## Overview

UiPath supports a hybrid approach where the REFramework state machine remains in XAML while individual processing steps, utilities, and business logic are implemented as coded C# workflows. This combines the visual orchestration of the state machine with the testability, refactorability, and expressiveness of C#.

---

## Architecture

```
REFramework (XAML State Machine)
+-- Main.xaml                        <- State machine (keep as XAML)
+-- Framework/
|   +-- InitAllSettings.xaml         <- Config loading (keep as XAML)
|   +-- InitAllApplications.xaml     <- Can invoke coded workflows
|   +-- GetTransactionData.xaml      <- Queue interaction (keep as XAML)
|   +-- Process.xaml                 <- Invokes coded workflow
|   +-- SetTransactionStatus.xaml    <- Status update (keep as XAML)
|   +-- CloseAllApplications.xaml
|   +-- KillAllProcesses.xaml
+-- CodedWorkflows/
|   +-- ProcessTransaction.cs        <- Main business logic (coded)
|   +-- Validators/
|   |   +-- TransactionValidator.cs
|   +-- Services/
|   |   +-- WebPortalService.cs
|   |   +-- SapService.cs
|   +-- Models/
|       +-- ProcessConfig.cs         <- Typed config wrapper
|       +-- InvoiceDto.cs            <- Transaction DTO
```

---

## Invoking Coded Workflows from XAML

### Using Invoke Workflow File

In Process.xaml, use the `Invoke Workflow File` activity to call a coded workflow:

```xml
<ui:InvokeWorkflowFile
  DisplayName="Process Transaction (Coded)"
  WorkflowFileName="CodedWorkflows\ProcessTransaction.cs">
  <ui:InvokeWorkflowFile.Arguments>
    <InArgument x:TypeArguments="x:String" x:Key="in_TransactionID">
      [in_TransactionItem.SpecificContent("TransactionID").ToString]
    </InArgument>
    <InArgument x:TypeArguments="scg:Dictionary(x:String,x:Object)" x:Key="in_Config">
      [in_Config]
    </InArgument>
    <OutArgument x:TypeArguments="x:String" x:Key="out_Result">
      [TransactionResult]
    </OutArgument>
  </ui:InvokeWorkflowFile.Arguments>
</ui:InvokeWorkflowFile>
```

### Direct Method Invocation (Coded-to-Coded)

Within coded workflows, invoke other coded workflows as method calls:

```csharp
var processor = new ProcessTransaction();
processor.Execute(transactionId, config);
```

---

## Argument Passing

### XAML to Coded Workflow

Arguments are defined as method parameters on the `[Workflow]` method:

```csharp
using System.Collections.Generic;
using UiPath.CodedWorkflows;

public class ProcessTransaction : CodedWorkflow
{
    [Workflow]
    public void Execute(
        string in_TransactionID,
        Dictionary<string, object> in_Config,
        string in_ApplicationUrl)
    {
        Log($"Processing transaction: {in_TransactionID}", LogLevel.Info);

        var config = new ProcessConfig(in_Config);
        string url = config.ApplicationUrl;

        // ... business logic ...
    }
}
```

### Output Arguments

Use out parameters for outputs:

```csharp
[Workflow]
public void Execute(
    string in_TransactionID,
    Dictionary<string, object> in_Config,
    out string out_Status,
    out string out_ErrorMessage)
{
    try
    {
        // ... process ...
        out_Status = "Success";
        out_ErrorMessage = "";
    }
    catch (BusinessRuleException brex)
    {
        out_Status = "BusinessException";
        out_ErrorMessage = brex.Message;
        throw; // Still throw so REFramework handles it
    }
}
```

---

## Config Access in Coded Workflows

### Option 1: Raw Dictionary

Pass the entire Config dictionary:

```csharp
[Workflow]
public void Execute(Dictionary<string, object> in_Config)
{
    string queueName = in_Config["OrchestratorQueueName"].ToString();
    int maxRetry = int.Parse(in_Config["MaxRetryNumber"].ToString());
}
```

### Option 2: Strongly-Typed Wrapper (Recommended)

Use a generated config model class for type safety and defaults:

```csharp
[Workflow]
public void Execute(Dictionary<string, object> in_Config)
{
    var config = new ProcessConfig(in_Config);

    string url = config.ApplicationUrl;          // string
    int timeout = config.TimeoutSeconds;         // int, default 30
    bool notify = config.SendNotifications;      // bool, default false
}
```

See `templates/config_model.cs.j2` for generating the wrapper class.

### Option 3: Individual Arguments

For simple cases, pass only needed values:

```csharp
[Workflow]
public void Execute(string in_ApplicationUrl, int in_TimeoutSeconds, string in_TransactionID)
{
    // No config dictionary needed
}
```

---

## Exception Handling in Hybrid Mode

### Business Exceptions from Coded Workflows

The REFramework catches `BusinessRuleException` and `Exception` separately. Coded workflows must use the same exception types:

```csharp
using UiPath.Core.Activities;

[Workflow]
public void Execute(string transactionId, Dictionary<string, object> config)
{
    // Data validation -> BusinessRuleException
    if (string.IsNullOrEmpty(transactionId))
        throw new BusinessRuleException("Transaction ID is empty");

    try
    {
        ProcessInvoice(transactionId);
    }
    catch (FormatException ex)
    {
        // Data format issue = business rule
        throw new BusinessRuleException($"Invalid data format: {ex.Message}");
    }
    catch (KeyNotFoundException ex)
    {
        // Missing required data = business rule
        throw new BusinessRuleException($"Required field not found: {ex.Message}");
    }
    // All other exceptions propagate as system exceptions for retry
}
```

### System Exceptions

Let system exceptions propagate naturally. Add context only if helpful:

```csharp
try
{
    ClickLoginButton();
}
catch (SelectorNotFoundException ex)
{
    // Add context but keep as system exception (NOT BusinessRuleException)
    throw new Exception($"Login button not found for transaction {transactionId}", ex);
}
```

---

## Service Pattern for Application Interaction

Organize application interactions into service classes:

```csharp
// Services/WebPortalService.cs
public class WebPortalService : CodedWorkflow
{
    [Workflow]
    public void Login(string url, string username, string password)
    {
        // Navigate, enter credentials, click login, verify
    }

    [Workflow]
    public string SearchInvoice(string invoiceNumber)
    {
        // Navigate to search, enter number, click search, return result
    }

    [Workflow]
    public void UpdateStatus(string invoiceNumber, string status)
    {
        // Navigate to record, click edit, update field, save
    }
}
```

Compose services in the main process:

```csharp
// CodedWorkflows/ProcessTransaction.cs
public class ProcessTransaction : CodedWorkflow
{
    [Workflow]
    public void Execute(string invoiceNumber, Dictionary<string, object> config)
    {
        var portal = new WebPortalService();
        var validator = new TransactionValidator();

        validator.Validate(invoiceNumber);
        string data = portal.SearchInvoice(invoiceNumber);
        portal.UpdateStatus(invoiceNumber, "Processed");

        Log($"Invoice {invoiceNumber} processed successfully", LogLevel.Info);
    }
}
```

---

## Testing Coded Workflows

Coded workflows can be unit tested independently:

```csharp
using UiPath.CodedWorkflows;
using UiPath.CodedWorkflows.Testing;

[TestFixture]
public class ProcessTransactionTests : CodedWorkflow
{
    [TestCase]
    public void TestValidTransaction()
    {
        var config = new Dictionary<string, object>
        {
            { "MaxRetryNumber", "3" },
            { "ApplicationUrl", "https://test.example.com" }
        };

        var processor = new ProcessTransaction();
        processor.Execute("INV-001", config);
        // Should complete without exception
    }

    [TestCase]
    public void TestEmptyTransactionId_ThrowsBusinessException()
    {
        var config = new Dictionary<string, object>();
        var processor = new ProcessTransaction();

        Assert.Throws<BusinessRuleException>(() =>
            processor.Execute("", config));
    }
}
```

---

## Migration Strategy: XAML to Hybrid

### Phase 1: Keep Framework XAML, Code Business Logic

1. Keep Main.xaml state machine unchanged
2. Keep all Framework/ workflows as XAML
3. Create coded workflows for Process.xaml logic
4. Process.xaml becomes a thin wrapper that invokes the coded workflow

### Phase 2: Code Utilities and Services

1. Convert reusable XAML workflows to coded services
2. Create typed config and DTO models
3. Add unit tests for business logic

### Phase 3: Code Everything Except Main

1. Keep only Main.xaml as XAML (state machine)
2. All other workflows are coded
3. Full test coverage on business logic

### What to Keep as XAML

- **Main.xaml**: The state machine (visual flow is valuable)
- **InitAllSettings.xaml**: Config reading is straightforward
- **GetTransactionData.xaml**: Queue interaction is a single activity
- **SetTransactionStatus.xaml**: Status update is a single activity
- **KillAllProcesses.xaml**: Process killing is simpler in XAML

### What to Code in C#

- **Business logic**: Validation, calculations, data transformation
- **Application services**: Login, search, data entry sequences
- **Error handling**: Complex retry and recovery logic
- **Data models**: DTOs, config wrappers, typed data access
- **Utilities**: String formatting, date parsing, file operations
