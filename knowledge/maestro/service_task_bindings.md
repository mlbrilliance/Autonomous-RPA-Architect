# Maestro Service Task Bindings

In UiPath Maestro, service tasks in BPMN processes are bound to executable implementations: RPA workflows, AI agents, API endpoints, or queue operations. This document covers binding patterns for each type.

---

## RPA Workflow Binding

Binds a BPMN service task to a UiPath RPA workflow (XAML or coded).

```xml
<serviceTask id="processInvoice" name="Process Invoice"
  implementation="##UiPathProcess">
  <extensionElements>
    <uipath:workflowBinding
      processKey="ProcessInvoice"
      folderPath="Production/InvoiceBot"
      robotType="Unattended">

      <!-- Input mappings: BPMN variables -> workflow arguments -->
      <uipath:inputMapping>
        <uipath:parameter name="in_InvoiceNumber" expression="${invoiceNumber}"/>
        <uipath:parameter name="in_Amount" expression="${amount}"/>
        <uipath:parameter name="in_VendorId" expression="${vendorId}"/>
      </uipath:inputMapping>

      <!-- Output mappings: workflow arguments -> BPMN variables -->
      <uipath:outputMapping>
        <uipath:parameter name="out_Status" expression="${processingStatus}"/>
        <uipath:parameter name="out_ErrorMessage" expression="${errorMessage}"/>
      </uipath:outputMapping>

      <!-- Execution options -->
      <uipath:executionOptions
        timeout="PT10M"
        priority="Normal"
        retryOnFailure="true"
        maxRetries="2"/>
    </uipath:workflowBinding>
  </extensionElements>
</serviceTask>
```

### Key Properties

| Property | Description | Values |
|----------|-------------|--------|
| `processKey` | Name/key of the UiPath process | String (must match Orchestrator) |
| `folderPath` | Orchestrator folder path | String (e.g., "Production/Finance") |
| `robotType` | Execution mode | `Unattended`, `Attended`, `Headless` |
| `timeout` | Maximum execution time | ISO 8601 duration (e.g., PT10M) |
| `priority` | Job priority in queue | `High`, `Normal`, `Low` |
| `retryOnFailure` | Auto-retry on system exception | boolean |
| `maxRetries` | Maximum retry attempts | integer |

---

## AI Agent Binding

Binds a service task to a UiPath AI capability: Document Understanding, GenAI prompts, or custom agents.

### Document Understanding

```xml
<serviceTask id="classifyDocument" name="Classify Document"
  implementation="##AIAgent">
  <extensionElements>
    <uipath:aiBinding
      agentType="DocumentUnderstanding"
      modelId="invoice-classifier-v2"
      confidenceThreshold="0.85">

      <uipath:inputMapping>
        <uipath:parameter name="document" expression="${documentPath}"/>
        <uipath:parameter name="expectedType" expression="${documentType}"/>
      </uipath:inputMapping>

      <uipath:outputMapping>
        <uipath:parameter name="classification" expression="${docClass}"/>
        <uipath:parameter name="confidence" expression="${classConfidence}"/>
        <uipath:parameter name="extractedFields" expression="${extractedData}"/>
      </uipath:outputMapping>

      <uipath:fallback action="human_review"/>
    </uipath:aiBinding>
  </extensionElements>
</serviceTask>
```

### GenAI / LLM Agent

```xml
<serviceTask id="summarize" name="Summarize Report"
  implementation="##AIAgent">
  <extensionElements>
    <uipath:aiBinding
      agentType="GenAI"
      model="gpt-4o">

      <uipath:prompt>
        Summarize the following invoice data in 2-3 sentences.
        Focus on total amount, vendor, and key line items.

        Input: ${invoiceText}
      </uipath:prompt>

      <uipath:outputMapping>
        <uipath:parameter name="response" expression="${summary}"/>
      </uipath:outputMapping>

      <uipath:options maxTokens="500" temperature="0.3"/>
    </uipath:aiBinding>
  </extensionElements>
</serviceTask>
```

---

## API Workflow Binding

Binds a service task to an external REST API call.

```xml
<serviceTask id="validateVendor" name="Validate Vendor via API"
  implementation="##WebService">
  <extensionElements>
    <uipath:apiBinding
      method="POST"
      endpoint="https://api.vendor-check.com/v2/validate"
      authType="Bearer"
      credentialAsset="VendorCheck_APIKey">

      <uipath:headers>
        <uipath:header name="Content-Type" value="application/json"/>
        <uipath:header name="X-Request-Id" value="${processInstanceId}"/>
      </uipath:headers>

      <uipath:requestBody contentType="application/json">
        {
          "vendorId": "${vendorId}",
          "vendorName": "${vendorName}",
          "taxId": "${vendorTaxId}",
          "country": "${vendorCountry}"
        }
      </uipath:requestBody>

      <uipath:responseMapping>
        <uipath:parameter name="$.status" expression="${vendorStatus}"/>
        <uipath:parameter name="$.riskScore" expression="${vendorRiskScore}"/>
        <uipath:parameter name="$.lastVerified" expression="${vendorLastVerified}"/>
      </uipath:responseMapping>

      <uipath:errorHandling>
        <uipath:retry maxAttempts="3" delay="PT5S" backoff="exponential"/>
        <uipath:onError statusCode="4xx" action="business_exception"/>
        <uipath:onError statusCode="5xx" action="retry"/>
        <uipath:onTimeout timeout="PT30S" action="escalate"/>
      </uipath:errorHandling>
    </uipath:apiBinding>
  </extensionElements>
</serviceTask>
```

### Authentication Types

| Type | Description | Configuration |
|------|-------------|---------------|
| `Bearer` | Bearer token auth | `credentialAsset` with token value |
| `Basic` | HTTP Basic auth | `credentialAsset` with username/password |
| `ApiKey` | API key in header | `credentialAsset` + `apiKeyHeader` name |
| `OAuth2` | OAuth 2.0 flow | `clientId`, `clientSecret`, `tokenUrl` |
| `None` | No authentication | -- |

---

## Queue Operation Binding

Binds a service task to Orchestrator queue operations.

### Add Queue Item

```xml
<serviceTask id="dispatchItem" name="Add to Processing Queue"
  implementation="##Queue">
  <extensionElements>
    <uipath:queueBinding
      operation="AddQueueItem"
      queueName="InvoiceProcessingQueue"
      priority="${itemPriority}">

      <uipath:specificContent>
        <uipath:field name="InvoiceNumber" value="${invoiceNumber}"/>
        <uipath:field name="Amount" value="${amount}"/>
        <uipath:field name="VendorName" value="${vendorName}"/>
      </uipath:specificContent>

      <uipath:options
        reference="${invoiceNumber}"
        deadline="${dueDate}"/>
    </uipath:queueBinding>
  </extensionElements>
</serviceTask>
```

### Get Queue Item

```xml
<serviceTask id="getItem" name="Get Next Queue Item"
  implementation="##Queue">
  <extensionElements>
    <uipath:queueBinding
      operation="GetQueueItem"
      queueName="InvoiceProcessingQueue">

      <uipath:outputMapping>
        <uipath:parameter name="Reference" expression="${currentRef}"/>
        <uipath:parameter name="SpecificContent.InvoiceNumber" expression="${invoiceNum}"/>
        <uipath:parameter name="SpecificContent.Amount" expression="${amount}"/>
      </uipath:outputMapping>
    </uipath:queueBinding>
  </extensionElements>
</serviceTask>
```

### Set Transaction Status

```xml
<serviceTask id="markSuccess" name="Mark as Successful"
  implementation="##Queue">
  <extensionElements>
    <uipath:queueBinding
      operation="SetTransactionStatus"
      status="Success">
      <uipath:options
        transactionItem="${currentQueueItem}"
        reason="Processed successfully"/>
    </uipath:queueBinding>
  </extensionElements>
</serviceTask>
```

---

## DMN Business Rule Binding

Binds a business rule task to a DMN decision table.

```xml
<businessRuleTask id="routingRules" name="Apply Routing Rules"
  implementation="##DMN">
  <extensionElements>
    <uipath:dmnBinding
      decisionId="invoiceRoutingDecision"
      decisionName="Invoice Routing Rules">

      <uipath:inputMapping>
        <uipath:parameter name="amount" expression="${invoiceAmount}"/>
        <uipath:parameter name="vendorCategory" expression="${vendorCat}"/>
        <uipath:parameter name="department" expression="${dept}"/>
      </uipath:inputMapping>

      <uipath:outputMapping>
        <uipath:parameter name="action" expression="${routingAction}"/>
        <uipath:parameter name="approver" expression="${assignedApprover}"/>
      </uipath:outputMapping>
    </uipath:dmnBinding>
  </extensionElements>
</businessRuleTask>
```

---

## Binding Composition: End-to-End Example

A complete process using all binding types:

```xml
<process id="InvoiceE2E" name="End-to-End Invoice Processing">
  <startEvent id="start"/>

  <!-- 1. AI: Extract and classify document -->
  <serviceTask id="classify" name="AI Document Classification"
    implementation="##AIAgent">
    <!-- ai binding: Document Understanding -->
  </serviceTask>

  <!-- 2. DMN: Apply business rules -->
  <businessRuleTask id="routing" name="Apply Routing Rules"
    implementation="##DMN">
    <!-- dmn binding: Invoice routing decision table -->
  </businessRuleTask>

  <!-- 3. API: Validate vendor externally -->
  <serviceTask id="validateVendor" name="Vendor Validation API"
    implementation="##WebService">
    <!-- api binding: External vendor check service -->
  </serviceTask>

  <!-- 4. RPA: Enter data into ERP -->
  <serviceTask id="enterERP" name="Enter in SAP"
    implementation="##UiPathProcess">
    <!-- rpa binding: SAP data entry workflow -->
  </serviceTask>

  <!-- 5. Queue: Dispatch for approval if needed -->
  <serviceTask id="queueApproval" name="Queue for Approval"
    implementation="##Queue">
    <!-- queue binding: Add to approval queue -->
  </serviceTask>

  <!-- 6. Human: Review if flagged -->
  <userTask id="humanReview" name="Manager Review"/>

  <endEvent id="end"/>
</process>
```

---

## Best Practices

1. **Set timeouts on all service tasks** -- prevent hung processes from blocking resources.
2. **Use retry policies for API bindings** -- external services can have transient failures.
3. **Map only needed fields** -- avoid passing entire objects between tasks.
4. **Use Orchestrator assets for credentials** -- never hardcode secrets in BPMN.
5. **Add boundary error events** -- catch failures at the task level for graceful error handling.
6. **Use DMN for routing logic** -- externalize business rules from the process flow.
7. **Test bindings independently** -- verify each service task works before composing the full process.
