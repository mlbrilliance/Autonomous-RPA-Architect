# BPMN Patterns for UiPath Maestro

UiPath Maestro uses BPMN 2.0 as its orchestration language for composing automated workflows, human tasks, AI agents, and API calls into end-to-end business processes.

---

## Sequential Pattern

Tasks execute one after another in a simple linear flow.

```xml
<process id="InvoiceApproval" name="Invoice Approval Process">
  <startEvent id="start" name="Invoice Received"/>

  <sequenceFlow sourceRef="start" targetRef="extractData"/>

  <serviceTask id="extractData" name="Extract Invoice Data"
    implementation="##UiPathProcess"/>

  <sequenceFlow sourceRef="extractData" targetRef="validateData"/>

  <serviceTask id="validateData" name="Validate Invoice"
    implementation="##UiPathProcess"/>

  <sequenceFlow sourceRef="validateData" targetRef="postToERP"/>

  <serviceTask id="postToERP" name="Post to ERP"
    implementation="##UiPathProcess"/>

  <sequenceFlow sourceRef="postToERP" targetRef="end"/>

  <endEvent id="end" name="Invoice Posted"/>
</process>
```

Use sequential patterns when:
- Each step depends on the output of the previous step
- Order of operations matters
- Steps interact with the same application session

---

## Parallel Pattern

Use a parallel gateway to run tasks concurrently, then join when all complete.

```xml
<process id="ParallelValidation" name="Parallel Validation">
  <startEvent id="start"/>
  <sequenceFlow sourceRef="start" targetRef="fork"/>

  <!-- Fork: split into parallel branches -->
  <parallelGateway id="fork" name="Start Parallel Checks"/>

  <sequenceFlow sourceRef="fork" targetRef="validateFormat"/>
  <sequenceFlow sourceRef="fork" targetRef="checkDuplicates"/>
  <sequenceFlow sourceRef="fork" targetRef="verifyVendor"/>

  <serviceTask id="validateFormat" name="Validate Format"/>
  <serviceTask id="checkDuplicates" name="Check Duplicates"/>
  <serviceTask id="verifyVendor" name="Verify Vendor"/>

  <!-- Join: wait for ALL parallel branches to complete -->
  <sequenceFlow sourceRef="validateFormat" targetRef="join"/>
  <sequenceFlow sourceRef="checkDuplicates" targetRef="join"/>
  <sequenceFlow sourceRef="verifyVendor" targetRef="join"/>

  <parallelGateway id="join" name="All Checks Complete"/>

  <sequenceFlow sourceRef="join" targetRef="aggregateResults"/>

  <serviceTask id="aggregateResults" name="Aggregate Results"/>

  <sequenceFlow sourceRef="aggregateResults" targetRef="end"/>
  <endEvent id="end"/>
</process>
```

Use parallel patterns when:
- Tasks are independent of each other
- You want to reduce total processing time
- Different systems or APIs can be queried simultaneously

---

## Exclusive Gateway Pattern

Routes to exactly one branch based on a condition. Only the first matching condition fires.

```xml
<process id="InvoiceRouting" name="Invoice Routing">
  <startEvent id="start"/>
  <sequenceFlow sourceRef="start" targetRef="classifyInvoice"/>

  <serviceTask id="classifyInvoice" name="Classify Invoice"/>

  <sequenceFlow sourceRef="classifyInvoice" targetRef="routingDecision"/>

  <!-- Exclusive gateway: only one path is taken -->
  <exclusiveGateway id="routingDecision" name="Route by Amount"/>

  <!-- Branch 1: Auto-approve small amounts -->
  <sequenceFlow sourceRef="routingDecision" targetRef="autoApprove" name="Under $1,000">
    <conditionExpression xsi:type="tFormalExpression">
      ${amount &lt; 1000}
    </conditionExpression>
  </sequenceFlow>

  <!-- Branch 2: Manager review for medium amounts -->
  <sequenceFlow sourceRef="routingDecision" targetRef="managerReview" name="$1,000 - $10,000">
    <conditionExpression xsi:type="tFormalExpression">
      ${amount &gt;= 1000 &amp;&amp; amount &lt; 10000}
    </conditionExpression>
  </sequenceFlow>

  <!-- Branch 3: VP approval for large amounts -->
  <sequenceFlow sourceRef="routingDecision" targetRef="vpApproval" name="Over $10,000">
    <conditionExpression xsi:type="tFormalExpression">
      ${amount &gt;= 10000}
    </conditionExpression>
  </sequenceFlow>

  <serviceTask id="autoApprove" name="Auto-Approve"/>
  <userTask id="managerReview" name="Manager Review"/>
  <userTask id="vpApproval" name="VP Review"/>

  <!-- Merge branches back together -->
  <sequenceFlow sourceRef="autoApprove" targetRef="merge"/>
  <sequenceFlow sourceRef="managerReview" targetRef="merge"/>
  <sequenceFlow sourceRef="vpApproval" targetRef="merge"/>

  <exclusiveGateway id="merge" name="Merge"/>

  <sequenceFlow sourceRef="merge" targetRef="postInvoice"/>
  <serviceTask id="postInvoice" name="Post Invoice"/>

  <sequenceFlow sourceRef="postInvoice" targetRef="end"/>
  <endEvent id="end"/>
</process>
```

---

## Error Boundary Event Pattern

Attach error boundary events to service tasks to handle failures without crashing the entire process.

```xml
<process id="ResilientProcess" name="Resilient Processing">
  <startEvent id="start"/>
  <sequenceFlow sourceRef="start" targetRef="processInvoice"/>

  <serviceTask id="processInvoice" name="Process Invoice"
    implementation="##UiPathProcess"/>

  <!-- Boundary error event: catches failures from processInvoice -->
  <boundaryEvent id="processingError" attachedToRef="processInvoice">
    <errorEventDefinition errorRef="systemError"/>
  </boundaryEvent>

  <!-- Normal flow (success) -->
  <sequenceFlow sourceRef="processInvoice" targetRef="end"/>

  <!-- Error flow -->
  <sequenceFlow sourceRef="processingError" targetRef="logError"/>

  <serviceTask id="logError" name="Log Error and Notify"/>

  <sequenceFlow sourceRef="logError" targetRef="escalateToHuman"/>

  <userTask id="escalateToHuman" name="Manual Review Required">
    <humanPerformer>
      <resourceAssignmentExpression>
        <formalExpression>operations_team</formalExpression>
      </resourceAssignmentExpression>
    </humanPerformer>
  </userTask>

  <sequenceFlow sourceRef="escalateToHuman" targetRef="errorEnd"/>

  <endEvent id="end" name="Success"/>
  <endEvent id="errorEnd" name="Escalated"/>
</process>
```

### Timer Boundary Event (Timeout)

```xml
<serviceTask id="longTask" name="Complex Processing"/>

<!-- Timeout after 30 minutes, cancels the task -->
<boundaryEvent id="timeout" attachedToRef="longTask" cancelActivity="true">
  <timerEventDefinition>
    <timeDuration>PT30M</timeDuration>
  </timerEventDefinition>
</boundaryEvent>

<sequenceFlow sourceRef="timeout" targetRef="handleTimeout"/>
<serviceTask id="handleTimeout" name="Handle Timeout"/>
```

---

## Subprocess Pattern

Encapsulate reusable process fragments as subprocesses.

### Embedded Subprocess

```xml
<subProcess id="validationSuite" name="Invoice Validation Suite">
  <startEvent id="subStart"/>

  <sequenceFlow sourceRef="subStart" targetRef="checkFormat"/>
  <serviceTask id="checkFormat" name="Check Format"/>

  <sequenceFlow sourceRef="checkFormat" targetRef="checkValues"/>
  <serviceTask id="checkValues" name="Validate Values"/>

  <sequenceFlow sourceRef="checkValues" targetRef="checkCompliance"/>
  <serviceTask id="checkCompliance" name="Compliance Check"/>

  <sequenceFlow sourceRef="checkCompliance" targetRef="subEnd"/>
  <endEvent id="subEnd"/>
</subProcess>
```

### Call Activity (Reusable Process)

```xml
<!-- Reference to a separately defined process -->
<callActivity id="validateInvoice" name="Validate Invoice"
              calledElement="InvoiceValidationProcess"/>
```

---

## Loop Patterns

### Multi-Instance (For Each)

Process a collection of items in parallel or sequentially:

```xml
<!-- Process each line item in parallel -->
<serviceTask id="processLineItem" name="Process Line Item">
  <multiInstanceLoopCharacteristics isSequential="false">
    <loopDataInputRef>lineItems</loopDataInputRef>
    <inputDataItem name="currentItem"/>
  </multiInstanceLoopCharacteristics>
</serviceTask>

<!-- Process items sequentially -->
<serviceTask id="processSequential" name="Process Item">
  <multiInstanceLoopCharacteristics isSequential="true">
    <loopDataInputRef>itemList</loopDataInputRef>
    <inputDataItem name="currentItem"/>
  </multiInstanceLoopCharacteristics>
</serviceTask>
```

### Retry Loop with Exclusive Gateway

```xml
<exclusiveGateway id="retryCheck"/>

<sequenceFlow sourceRef="retryCheck" targetRef="attemptProcess">
  <conditionExpression>${retryCount &lt; maxRetries}</conditionExpression>
</sequenceFlow>

<serviceTask id="attemptProcess" name="Attempt Processing"/>

<sequenceFlow sourceRef="attemptProcess" targetRef="checkResult"/>
<exclusiveGateway id="checkResult"/>

<!-- Success path -->
<sequenceFlow sourceRef="checkResult" targetRef="end">
  <conditionExpression>${status == 'success'}</conditionExpression>
</sequenceFlow>

<!-- Failure: loop back -->
<sequenceFlow sourceRef="checkResult" targetRef="retryCheck">
  <conditionExpression>${status != 'success'}</conditionExpression>
</sequenceFlow>
```

---

## Human-in-the-Loop Pattern

Combine automated and manual steps:

```xml
<process id="HumanInLoop" name="Invoice with Human Review">
  <startEvent id="start"/>

  <!-- Automated: extract data -->
  <serviceTask id="extractData" name="AI Document Extraction"/>

  <!-- Automated: validate -->
  <serviceTask id="validate" name="Validate Extracted Data"/>

  <!-- Decision: needs human review? -->
  <exclusiveGateway id="reviewNeeded" name="Confidence Check"/>

  <!-- High confidence: proceed automatically -->
  <sequenceFlow sourceRef="reviewNeeded" targetRef="autoProcess">
    <conditionExpression>${confidence &gt;= 0.95}</conditionExpression>
  </sequenceFlow>

  <!-- Low confidence: human review -->
  <sequenceFlow sourceRef="reviewNeeded" targetRef="humanReview">
    <conditionExpression>${confidence &lt; 0.95}</conditionExpression>
  </sequenceFlow>

  <userTask id="humanReview" name="Review Extracted Data">
    <humanPerformer>
      <resourceAssignmentExpression>
        <formalExpression>data_reviewers</formalExpression>
      </resourceAssignmentExpression>
    </humanPerformer>
  </userTask>

  <serviceTask id="autoProcess" name="Process Invoice"/>

  <!-- Merge and continue -->
  <exclusiveGateway id="reviewMerge"/>
  <serviceTask id="postToERP" name="Post to ERP"/>

  <endEvent id="end"/>
</process>
```
