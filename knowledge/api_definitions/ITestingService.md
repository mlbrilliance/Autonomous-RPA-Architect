# ITestingService API Reference

> **Namespace:** `UiPath.CodedWorkflows.Testing`
> **Injection:** `[Service] ITestingService testing`

Provides assertion and test data operations for UiPath coded test cases.
Test classes inherit from `CodedTestCase` instead of `CodedWorkflow`.

---

## Assertion Methods

### VerifyExpression

Asserts that a boolean expression evaluates to `true`.

```csharp
void VerifyExpression(
    bool expression,
    string outputMessage
);
```

**Parameters:**
| Parameter | Type | Description |
|-----------|------|-------------|
| `expression` | `bool` | The expression to evaluate |
| `outputMessage` | `string` | Message displayed on failure |

**Example:**
```csharp
[Service] ITestingService testing;

[TestCase]
public void VerifyInvoiceProcessed()
{
    string status = GetInvoiceStatus("INV-001");
    testing.VerifyExpression(
        status == "Processed",
        $"Expected status 'Processed' but got '{status}'"
    );
}
```

---

### VerifyAreEqual

Asserts that two values are equal.

```csharp
void VerifyAreEqual(
    object expected,
    object actual,
    string outputMessage
);
```

**Parameters:**
| Parameter | Type | Description |
|-----------|------|-------------|
| `expected` | `object` | Expected value |
| `actual` | `object` | Actual value from the system under test |
| `outputMessage` | `string` | Message displayed on failure |

**Example:**
```csharp
[TestCase]
public void VerifyCalculatedTotal()
{
    decimal expectedTotal = 1250.00m;
    decimal actualTotal = CalculateInvoiceTotal("INV-001");

    testing.VerifyAreEqual(
        expectedTotal,
        actualTotal,
        $"Invoice total mismatch: expected {expectedTotal}, got {actualTotal}"
    );
}
```

---

### VerifyContains

Asserts that a string contains a specified substring.

```csharp
void VerifyContains(
    string fullString,
    string substring,
    string outputMessage
);
```

**Parameters:**
| Parameter | Type | Description |
|-----------|------|-------------|
| `fullString` | `string` | The string to search within |
| `substring` | `string` | The substring to look for |
| `outputMessage` | `string` | Message displayed on failure |

**Example:**
```csharp
[TestCase]
public void VerifyConfirmationMessage()
{
    string message = GetConfirmationText();
    testing.VerifyContains(
        message,
        "successfully submitted",
        $"Confirmation message did not contain expected text. Got: {message}"
    );
}
```

---

### VerifyRange

Asserts that a numeric value falls within a specified range.

```csharp
void VerifyRange(
    double value,
    double min,
    double max,
    string outputMessage
);
```

**Parameters:**
| Parameter | Type | Description |
|-----------|------|-------------|
| `value` | `double` | The value to check |
| `min` | `double` | Minimum acceptable value (inclusive) |
| `max` | `double` | Maximum acceptable value (inclusive) |
| `outputMessage` | `string` | Message displayed on failure |

**Example:**
```csharp
[TestCase]
public void VerifyProcessingTime()
{
    double elapsedSeconds = MeasureProcessingTime();
    testing.VerifyRange(
        elapsedSeconds,
        0.0,
        30.0,
        $"Processing took {elapsedSeconds}s, expected between 0-30s"
    );
}
```

---

## Test Data Queue Operations

### AddTestDataQueueItem

Adds a test data item to a test data queue. Test data queues are separate
from Orchestrator queues and are used for parameterized test execution.

```csharp
void AddTestDataQueueItem(
    string queueName,
    Dictionary<string, object> data
);
```

**Parameters:**
| Parameter | Type | Description |
|-----------|------|-------------|
| `queueName` | `string` | Test data queue name |
| `data` | `Dictionary<string, object>` | Key-value pairs for the test data row |

**Example:**
```csharp
[TestCase]
public void SetupTestData()
{
    var testCases = new[]
    {
        new Dictionary<string, object>
        {
            { "InvoiceNumber", "INV-TEST-001" },
            { "Amount", 500.00 },
            { "ExpectedStatus", "Approved" }
        },
        new Dictionary<string, object>
        {
            { "InvoiceNumber", "INV-TEST-002" },
            { "Amount", 15000.00 },
            { "ExpectedStatus", "PendingApproval" }
        }
    };

    foreach (var tc in testCases)
    {
        testing.AddTestDataQueueItem("InvoiceTestData", tc);
    }
}
```

### GetTestDataQueueItem

Retrieves the next item from a test data queue for data-driven testing.

```csharp
TestDataQueueItem GetTestDataQueueItem(string queueName);
```

**Returns:** A `TestDataQueueItem` with a `.Data` dictionary, or `null` if empty.

**Example:**
```csharp
[TestCase]
public void DataDrivenInvoiceTest()
{
    var testData = testing.GetTestDataQueueItem("InvoiceTestData");

    if (testData == null)
    {
        testing.VerifyExpression(false, "No test data available.");
        return;
    }

    string invoiceNumber = testData.Data["InvoiceNumber"].ToString();
    string expectedStatus = testData.Data["ExpectedStatus"].ToString();

    // Run the workflow under test
    RunWorkflow("ProcessInvoice", new Dictionary<string, object>
    {
        { "in_InvoiceNumber", invoiceNumber }
    });

    // Verify outcome
    string actualStatus = GetInvoiceStatus(invoiceNumber);
    testing.VerifyAreEqual(
        expectedStatus,
        actualStatus,
        $"Invoice {invoiceNumber}: expected '{expectedStatus}', got '{actualStatus}'"
    );
}
```

---

## Complete Test Case Example

```csharp
using UiPath.CodedWorkflows;
using UiPath.CodedWorkflows.Testing;

namespace InvoiceBot.CodedTests
{
    public class InvoiceProcessingTests : CodedTestCase
    {
        [Service] ITestingService testing;
        [Service] ISystemService system;

        [TestCase]
        public void Test_ValidInvoice_IsProcessedSuccessfully()
        {
            // Arrange
            var invoiceNumber = "INV-TEST-001";
            var amount = 500.00m;

            // Act
            RunWorkflow("ProcessInvoice", new Dictionary<string, object>
            {
                { "in_InvoiceNumber", invoiceNumber },
                { "in_Amount", amount }
            });

            // Assert
            string status = GetInvoiceStatus(invoiceNumber);
            testing.VerifyAreEqual("Processed", status,
                "Valid invoice should be processed successfully.");
        }

        [TestCase]
        public void Test_HighValueInvoice_RequiresApproval()
        {
            // Arrange
            var invoiceNumber = "INV-TEST-002";
            var amount = 15000.00m;

            // Act
            RunWorkflow("ProcessInvoice", new Dictionary<string, object>
            {
                { "in_InvoiceNumber", invoiceNumber },
                { "in_Amount", amount }
            });

            // Assert
            string status = GetInvoiceStatus(invoiceNumber);
            testing.VerifyAreEqual("PendingApproval", status,
                "High-value invoice should require manager approval.");
        }

        [TestCase]
        public void Test_InvalidInvoice_ThrowsBusinessException()
        {
            // Arrange
            var invoiceNumber = "";

            // Act & Assert
            try
            {
                RunWorkflow("ProcessInvoice", new Dictionary<string, object>
                {
                    { "in_InvoiceNumber", invoiceNumber },
                    { "in_Amount", 0 }
                });

                testing.VerifyExpression(false,
                    "Expected BusinessRuleException for invalid invoice.");
            }
            catch (BusinessRuleException ex)
            {
                testing.VerifyContains(ex.Message, "invalid",
                    "Exception message should mention 'invalid'.");
            }
        }
    }
}
```
