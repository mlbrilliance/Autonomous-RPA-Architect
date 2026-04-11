# Maestro + REFramework Hybrid Orchestration

## When to Use Each

| Aspect | REFramework | Maestro |
|--------|------------|---------|
| Scope | Single bot, single process | Multi-bot, multi-system orchestration |
| Error handling | Built-in retry/exception states | BPMN boundary events + escalation |
| Human-in-loop | Not natively supported | First-class user tasks |
| Decision logic | Coded or hardcoded in workflow | DMN decision tables (externalized) |
| Monitoring | Orchestrator job logs | BPMN process instance tracking |
| Queue processing | Native (core use case) | Via queue operation bindings |
| API integration | Via HTTP activities | Via API service task bindings |
| AI integration | Via AI activities | Via AI agent service task bindings |

### Use REFramework When

- Processing a queue of homogeneous items (invoices, orders, claims)
- Single-system or single-bot automation
- Retry/exception handling is the primary concern
- Process is well-defined with clear transaction boundaries

### Use Maestro When

- Orchestrating multiple bots across systems
- Human approval or review steps are needed
- Complex routing/decision logic (better expressed as DMN)
- End-to-end process visibility is required
- Mixing RPA, AI, and API steps in one process

### Use Both Together When

- Maestro orchestrates the end-to-end process flow
- REFramework bots handle the heavy-lifting queue processing steps
- Each REFramework bot is exposed as a Maestro service task
- DMN tables drive routing decisions that REFramework bots execute

---

## Architecture: Composing REFramework as Maestro Sub-Processes

```
Maestro BPMN Process (End-to-End Orchestrator)
|
+-- [Start Event: New Invoice Batch]
|
+-- [Service Task: AI Extract]        -> Document Understanding
|
+-- [Business Rule: DMN Routing]      -> Decision Table
|
+-- [Exclusive Gateway: Route]
|   |
|   +-- [Service Task: Dispatcher]    -> REFramework Dispatcher Bot
|   |     Reads source, enqueues items to Orchestrator Queue
|   |
|   +-- [User Task: Manual Review]    -> Human reviewer (low confidence)
|
+-- [Parallel Gateway: Fan Out]
|   |
|   +-- [Service Task: Performer 1]   -> REFramework Performer (Robot 1)
|   +-- [Service Task: Performer 2]   -> REFramework Performer (Robot 2)
|   +-- [Service Task: Performer 3]   -> REFramework Performer (Robot 3)
|
+-- [Service Task: Wait for Queue]    -> Monitor queue completion
|
+-- [Service Task: Report]            -> Generate summary
|
+-- [User Task: Final Review]         -> Stakeholder sign-off
|
+-- [End Event]
```

---

## Dispatcher Bot as Maestro Service Task

The Dispatcher bot reads from a source (file, email, API) and creates queue items:

```xml
<serviceTask id="dispatch" name="Dispatch Invoices to Queue"
  implementation="##UiPathProcess">
  <extensionElements>
    <uipath:workflowBinding
      processKey="Dispatcher_Main"
      folderPath="Production/InvoiceBot"
      robotType="Unattended">

      <uipath:inputMapping>
        <uipath:parameter name="in_InputFilePath" expression="${inputFilePath}"/>
        <uipath:parameter name="in_BatchId" expression="${batchId}"/>
      </uipath:inputMapping>

      <uipath:outputMapping>
        <uipath:parameter name="out_ItemsDispatched" expression="${dispatchedCount}"/>
        <uipath:parameter name="out_ItemsSkipped" expression="${skippedCount}"/>
      </uipath:outputMapping>

      <uipath:executionOptions timeout="PT30M"/>
    </uipath:workflowBinding>
  </extensionElements>
</serviceTask>
```

---

## Performer Bot as Queue-Triggered Service

Instead of binding the Performer directly as a blocking service task, use a pattern where Maestro starts performers and then monitors the queue:

```xml
<!-- Start performer bots (non-blocking) -->
<serviceTask id="startPerformers" name="Start Performer Bots"
  implementation="##UiPathProcess">
  <extensionElements>
    <uipath:workflowBinding
      processKey="Performer_Main"
      folderPath="Production/InvoiceBot"
      robotType="Unattended"
      instances="3">

      <uipath:executionOptions
        timeout="PT2H"
        waitForCompletion="false"/>
    </uipath:workflowBinding>
  </extensionElements>
</serviceTask>

<!-- Wait for queue to drain -->
<serviceTask id="waitForQueue" name="Wait for Queue Completion"
  implementation="##Queue">
  <extensionElements>
    <uipath:queueBinding
      operation="WaitForEmpty"
      queueName="InvoiceProcessingQueue"
      pollInterval="PT1M"
      timeout="PT4H"/>
  </extensionElements>
</serviceTask>
```

---

## Shared Configuration

### Centralized Config via Orchestrator Assets

Both Maestro and REFramework bots read from the same Orchestrator assets:

```
Orchestrator Assets (shared):
+-- InvoiceBot_ApplicationURL     = "https://erp.company.com"
+-- InvoiceBot_MaxRetryNumber     = 3
+-- InvoiceBot_QueueName          = "InvoiceProcessingQueue"
+-- InvoiceBot_Credential         = (credential asset)
+-- InvoiceBot_NotificationEmail  = "ops@company.com"
```

### Config.xlsx with Maestro Settings

The REFramework Config.xlsx can include Maestro-specific settings:

| Name | Value | Sheet | Description |
|------|-------|-------|-------------|
| OrchestratorQueueName | InvoiceProcessingQueue | Settings | Queue name |
| MaxRetryNumber | 3 | Settings | Retry count |
| MaestroProcessId | invoice-e2e | Constants | Maestro process ID |
| MaestroCallbackUrl | https://maestro.co/callback | Constants | Status callback URL |
| MaestroCorrelationKey | batchId | Constants | Key to correlate with Maestro |

---

## REFramework Bot Reporting Back to Maestro

The Performer bot can report progress and completion back to Maestro:

```csharp
[Workflow]
public void ReportToMaestro(Dictionary<string, object> config, string status,
    int successCount, int failureCount)
{
    string callbackUrl = config["MaestroCallbackUrl"]?.ToString();
    string batchId = config["MaestroCorrelationKey"]?.ToString();

    if (string.IsNullOrEmpty(callbackUrl))
        return; // Not running under Maestro

    var payload = new Dictionary<string, object>
    {
        { "batchId", batchId },
        { "status", status },
        { "completedAt", DateTime.UtcNow.ToString("o") },
        { "successCount", successCount },
        { "failureCount", failureCount }
    };

    // POST to Maestro callback
    HttpClient.PostJson(callbackUrl, payload);
    Log($"Reported to Maestro: {status} for batch {batchId}", LogLevel.Info);
}
```

---

## Hybrid Decision Patterns

### DMN for Routing, REFramework for Execution

Use Maestro DMN to decide which REFramework bot processes each item:

```xml
<!-- DMN decides processing path -->
<businessRuleTask id="routeDecision" name="Route Invoice"
  implementation="##DMN">
  <extensionElements>
    <uipath:dmnBinding decisionId="invoiceRouting">
      <uipath:inputMapping>
        <uipath:parameter name="amount" expression="${invoiceAmount}"/>
        <uipath:parameter name="type" expression="${invoiceType}"/>
      </uipath:inputMapping>
      <uipath:outputMapping>
        <uipath:parameter name="targetQueue" expression="${targetQueue}"/>
        <uipath:parameter name="botProject" expression="${targetBot}"/>
      </uipath:outputMapping>
    </uipath:dmnBinding>
  </extensionElements>
</businessRuleTask>

<!-- Route to the appropriate queue/bot -->
<exclusiveGateway id="routeGateway"/>

<sequenceFlow sourceRef="routeGateway" targetRef="standardBot">
  <conditionExpression>${targetBot == 'StandardInvoiceBot'}</conditionExpression>
</sequenceFlow>

<sequenceFlow sourceRef="routeGateway" targetRef="complexBot">
  <conditionExpression>${targetBot == 'ComplexInvoiceBot'}</conditionExpression>
</sequenceFlow>
```

### Escalation from REFramework to Maestro

When a REFramework bot encounters an item it cannot process, it can escalate to Maestro for human review:

```csharp
// In REFramework Process.xaml / ProcessTransaction.cs
catch (BusinessRuleException brex) when (brex.Message.Contains("requires approval"))
{
    // Instead of marking as Failed, escalate to Maestro
    var escalation = new Dictionary<string, object>
    {
        { "invoiceNumber", invoiceNumber },
        { "reason", brex.Message },
        { "escalationType", "human_approval" }
    };

    // Add to Maestro escalation queue
    Orchestrator.AddQueueItem("MaestroEscalationQueue", escalation);

    // Mark as business exception (handled)
    SetTransactionStatus(item, TransactionStatus.Failed, brex.Message);
}
```

---

## End-to-End Example

```xml
<process id="InvoiceE2E" name="End-to-End Invoice Processing">

  <!-- 1. Trigger: new invoice batch arrives -->
  <startEvent id="start">
    <messageEventDefinition messageRef="newInvoiceBatch"/>
  </startEvent>

  <!-- 2. AI: Extract and classify documents -->
  <serviceTask id="aiExtract" name="AI Document Extraction"
    implementation="##AIAgent"/>

  <!-- 3. DMN: Apply routing rules -->
  <businessRuleTask id="routingRules" name="Apply Routing Rules"
    implementation="##DMN"/>

  <!-- 4. Route based on DMN output -->
  <exclusiveGateway id="routeDecision"/>

  <!-- 4a. Auto-process path: REFramework handles queue -->
  <serviceTask id="dispatcher" name="Dispatch to Queue"
    implementation="##UiPathProcess"/>

  <!-- Performers process the queue (started by Orchestrator triggers) -->
  <serviceTask id="waitQueue" name="Wait for Processing"
    implementation="##Queue"/>

  <!-- 4b. Manual review path -->
  <userTask id="manualReview" name="Human Review Required"/>

  <!-- 5. Merge paths -->
  <exclusiveGateway id="mergeResults"/>

  <!-- 6. Generate report -->
  <serviceTask id="report" name="Generate Summary Report"
    implementation="##UiPathProcess"/>

  <!-- 7. Notify stakeholders -->
  <serviceTask id="notify" name="Send Notification"
    implementation="##WebService"/>

  <endEvent id="end"/>
</process>
```

---

## Best Practices

1. **Use Maestro for orchestration, REFramework for execution** -- Maestro handles the "what" and "when", REFramework handles the "how".

2. **Keep REFramework bots stateless** -- Each bot processes queue items independently, making it easy to scale horizontally.

3. **Use shared Orchestrator assets** -- Configuration shared between Maestro and REFramework should live in Orchestrator assets, not in Config.xlsx.

4. **Correlate with batch IDs** -- Use a correlation key (batch ID) to track items across Maestro processes and REFramework queues.

5. **Design for partial failure** -- Maestro should handle scenarios where the REFramework bot processes some items but fails on others.

6. **Use DMN for routing decisions** -- Externalize business rules so they can be updated without modifying bot code.

7. **Implement callbacks** -- Have REFramework bots report status back to Maestro for real-time process visibility.
