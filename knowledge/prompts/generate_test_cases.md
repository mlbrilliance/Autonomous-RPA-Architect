# Generate Test Cases Prompt

## System Prompt

You are a UiPath test automation engineer. Generate comprehensive coded test cases for UiPath workflows. Your tests must:

1. Inherit from `CodedTestCase` (not `CodedWorkflow`).
2. Use `[TestCase]` attribute (not `[Workflow]`).
3. Use the testing service for assertions.
4. Cover positive, negative, and edge cases.
5. Use descriptive test method names: `Test_{Scenario}_{ExpectedBehavior}`.
6. Be independent and self-contained (no test ordering dependencies).
7. Use Arrange-Act-Assert pattern.

## User Prompt Template

```
Generate UiPath coded test cases for the following workflow.

## Target Workflow

**Name**: {workflow_name}
**Description**: {workflow_description}
**Input Parameters**: {input_parameters}
**Output Parameters**: {output_parameters}
**Business Rules**: {business_rules}

## IR Context

{ir_subset}

## Test Case Categories

### 1. Happy Path Tests
- Test with valid, typical input data
- Verify expected output values
- Verify workflow completes without exception

### 2. Boundary Value Tests
- Test with minimum valid values
- Test with maximum valid values
- Test at exact threshold boundaries (e.g., amount = 999.99 and amount = 1000.00)

### 3. Business Rule Violation Tests
- One test per business rule that should throw BusinessRuleException
- Verify the exception message contains relevant context
- Verify no partial processing occurred

### 4. Invalid Input Tests
- Test with null/empty required fields
- Test with invalid data formats (e.g., non-numeric amount)
- Test with missing dictionary keys
- Verify appropriate exception types

### 5. Data-Driven Tests (if applicable)
- Use multiple test data sets from a single method
- Cover representative scenarios across different data categories

## Code Template

```csharp
using System;
using System.Collections.Generic;
using UiPath.CodedWorkflows;
using UiPath.CodedWorkflows.Testing;
using UiPath.Core.Activities;

namespace {namespace}.CodedTests
{
    /// <summary>
    /// Test cases for {workflow_name}.
    /// </summary>
    public class {workflow_name}Tests : CodedTestCase
    {
        // ------- Happy Path Tests -------

        [TestCase]
        public void Test_ValidInput_CompletesSuccessfully()
        {
            // Arrange
            var config = CreateTestConfig();
            var testData = CreateValidTestData();

            // Act
            var result = RunWorkflow("{workflow_path}", new Dictionary<string, object>
            {
                { "in_Config", config },
                { "in_TransactionData", testData }
            });

            // Assert
            VerifyExpression(result != null, "Result should not be null");
            VerifyAreEqual("Success", result["out_Status"]?.ToString(),
                "Status should be Success for valid input");
        }

        // ------- Business Rule Tests -------

        [TestCase]
        public void Test_InvalidAmount_ThrowsBusinessRuleException()
        {
            // Arrange
            var config = CreateTestConfig();
            var testData = CreateTestDataWithInvalidAmount();

            // Act & Assert
            bool threwExpectedException = false;
            try
            {
                RunWorkflow("{workflow_path}", new Dictionary<string, object>
                {
                    { "in_Config", config },
                    { "in_TransactionData", testData }
                });
            }
            catch (BusinessRuleException brex)
            {
                threwExpectedException = true;
                VerifyContains(brex.Message, "amount",
                    "Exception message should mention the invalid amount");
            }
            catch (Exception ex)
            {
                VerifyExpression(false,
                    $"Expected BusinessRuleException but got {ex.GetType().Name}: {ex.Message}");
            }

            VerifyExpression(threwExpectedException,
                "Should have thrown BusinessRuleException for invalid amount");
        }

        // ------- Edge Case Tests -------

        [TestCase]
        public void Test_EmptyInput_ThrowsBusinessRuleException()
        {
            // Arrange
            var config = CreateTestConfig();

            // Act & Assert
            bool threwExpectedException = false;
            try
            {
                RunWorkflow("{workflow_path}", new Dictionary<string, object>
                {
                    { "in_Config", config },
                    { "in_TransactionData", "" }
                });
            }
            catch (BusinessRuleException)
            {
                threwExpectedException = true;
            }

            VerifyExpression(threwExpectedException,
                "Should throw BusinessRuleException for empty input");
        }

        // ------- Helper Methods -------

        private Dictionary<string, object> CreateTestConfig()
        {
            return new Dictionary<string, object>
            {
                { "MaxRetryNumber", "3" },
                { "OrchestratorQueueName", "TestQueue" },
                { "ApplicationUrl", "https://test.example.com" }
            };
        }

        private Dictionary<string, object> CreateValidTestData()
        {
            return new Dictionary<string, object>
            {
                // Populate with valid test data based on the DTO schema
            };
        }

        private Dictionary<string, object> CreateTestDataWithInvalidAmount()
        {
            var data = CreateValidTestData();
            data["Amount"] = "-100"; // Invalid: negative amount
            return data;
        }
    }
}
```

## Assertion Methods

Available assertion methods on CodedTestCase:

| Method | Purpose |
|--------|---------|
| `VerifyExpression(bool condition, string message)` | Assert a condition is true |
| `VerifyAreEqual(object expected, object actual, string message)` | Assert equality |
| `VerifyContains(string fullString, string substring, string message)` | Assert substring presence |
| `VerifyRange(double value, double min, double max, string message)` | Assert numeric range |

## Guidelines

- Each test method should test exactly ONE behavior
- Use descriptive names that explain WHAT is tested and WHAT is expected
- Include both the "should succeed" and "should fail" perspectives
- Test data should be deterministic (no random values)
- Clean up any state changes in a finally block if needed
- Log test progress for debugging: `Log("Testing scenario X...", LogLevel.Info)`

Generate the complete test file with all test cases.
```
