# Golden XAML Patterns for Code Generation

## Purpose

This document contains correct, production-ready XAML snippets for the most commonly generated UiPath activities. These patterns serve as reference examples during RAG-augmented code generation to prevent LLM hallucinations.

Every snippet below has been validated against the `known_activities.py` registry and will pass all hallucination lint rules (XL-H001 through XL-H008).

---

## Required Namespace Declarations

All patterns below assume these namespaces are declared on the root `<Activity>` element. Include only the ones you need:

```xml
<Activity
  x:Class="ProjectNamespace.WorkflowName"
  xmlns="http://schemas.uipath.com/workflow/activities"
  xmlns:x="http://schemas.microsoft.com/winfx/2006/xaml"
  xmlns:sap2010="http://schemas.microsoft.com/netfx/2010/xaml/activities/presentation"
  xmlns:scg="clr-namespace:System.Collections.Generic;assembly=mscorlib"
  xmlns:sco="clr-namespace:System.Collections.ObjectModel;assembly=mscorlib"
  xmlns:ui="clr-namespace:UiPath.UIAutomationNext.Activities;assembly=UiPath.UIAutomationNext.Activities"
  xmlns:sa="clr-namespace:System.Activities.Statements;assembly=System.Activities"
  xmlns:s="clr-namespace:System.Activities;assembly=System.Activities"
  xmlns:local="clr-namespace:UiPath.Core.Activities;assembly=UiPath.Core.Activities"
  xmlns:ue="clr-namespace:UiPath.Excel.Activities;assembly=UiPath.Excel.Activities"
  xmlns:uw="clr-namespace:UiPath.Web.Activities;assembly=UiPath.Web.Activities"
  xmlns:uo="clr-namespace:UiPath.Core.Activities;assembly=UiPath.OrchestratorActivities"
  xmlns:uc="clr-namespace:UiPath.Credentials.Activities;assembly=UiPath.Credentials.Activities"
  xmlns:sd="clr-namespace:System.Data;assembly=System.Data"
  xmlns:mc="http://schemas.openxmlformats.org/markup-compatibility/2006"
  xmlns:mca="clr-namespace:Microsoft.CSharp.Activities;assembly=System.Activities"
  sap2010:ExpressionActivityEditor.ExpressionActivityEditor="C#"
  >
```

---

## Pattern 1: NClick with Selector

Click a UI element using the modern NClick activity with a full target specification.

```xml
<ui:NClick ClickType="CLICK_SINGLE"
           MouseButton="BTN_LEFT"
           DelayAfter="300"
           DelayBefore="200"
           DisplayName="Click Submit Button"
           sap2010:WorkflowViewState.IdRef="NClick_1">
  <ui:NClick.Target>
    <ui:Target WaitForReady="INTERACTIVE"
               Timeout="30000"
               Selector="&lt;html app='chrome.exe' title='Invoice Portal*' /&gt;&lt;webctrl tag='button' aaname='Submit' /&gt;" />
  </ui:NClick.Target>
</ui:NClick>
```

**Key points:**
- `ClickType` uses `CLICK_SINGLE` or `CLICK_DOUBLE` (not `Single`/`Double`)
- `MouseButton` uses `BTN_LEFT`, `BTN_RIGHT`, `BTN_MIDDLE` (not `Left`/`Right`)
- Selector goes inside `<ui:NClick.Target><ui:Target ... /></ui:NClick.Target>` (not as a direct `Selector` attribute on NClick)
- XML special characters in selectors must be escaped: `<` becomes `&lt;`, `>` becomes `&gt;`, `"` becomes `&quot;`, `'` stays as `'` inside double-quoted attributes

**Right-click variant:**
```xml
<ui:NClick ClickType="CLICK_SINGLE"
           MouseButton="BTN_RIGHT"
           DisplayName="Right-Click Row"
           sap2010:WorkflowViewState.IdRef="NClick_2">
  <ui:NClick.Target>
    <ui:Target Selector="&lt;html app='chrome.exe' /&gt;&lt;webctrl tag='tr' tableRow='1' /&gt;" />
  </ui:NClick.Target>
</ui:NClick>
```

---

## Pattern 2: NTypeInto with EmptyField

Type text into a UI element, optionally clearing the field first.

```xml
<ui:NTypeInto ClickBeforeTyping="True"
              EmptyField="SingleSpace"
              Text="[invoiceNumber]"
              DelayAfter="200"
              DelayBefore="200"
              DelayBetweenKeys="10"
              DisplayName="Type Invoice Number"
              sap2010:WorkflowViewState.IdRef="NTypeInto_1">
  <ui:NTypeInto.Target>
    <ui:Target WaitForReady="INTERACTIVE"
               Timeout="30000"
               Selector="&lt;html app='chrome.exe' /&gt;&lt;webctrl tag='input' id='invoiceNumber' /&gt;" />
  </ui:NTypeInto.Target>
</ui:NTypeInto>
```

**Key points:**
- `EmptyField` valid values: `None` (don't clear), `Zero` (send empty string), `SingleSpace` (most reliable field clearing)
- `EmptyField="True"` is INVALID -- this is the most common LLM mistake
- `DelayBetweenKeys` valid values: `0`, `10`, `20`, `50`, `100` (milliseconds as string)
- `Text` can be a literal string or a VB.NET/C# expression in brackets `[variable]`

**Typing a literal string:**
```xml
<ui:NTypeInto ClickBeforeTyping="True"
              EmptyField="None"
              Text="admin@example.com"
              DisplayName="Type Email Address"
              sap2010:WorkflowViewState.IdRef="NTypeInto_2">
  <ui:NTypeInto.Target>
    <ui:Target Selector="&lt;html app='chrome.exe' /&gt;&lt;webctrl tag='input' type='email' id='email' /&gt;" />
  </ui:NTypeInto.Target>
</ui:NTypeInto>
```

---

## Pattern 3: ForEach with DataRow Iteration

Iterate over rows in a DataTable. This is one of the most common patterns in data-processing workflows.

```xml
<sa:ForEach x:TypeArguments="sd:DataRow"
            Values="[dt_TransactionData.AsEnumerable()]"
            DisplayName="For Each Transaction Row"
            sap2010:WorkflowViewState.IdRef="ForEach_1">
  <sa:ActivityAction x:TypeArguments="sd:DataRow">
    <sa:ActivityAction.Argument>
      <DelegateInArgument x:TypeArguments="sd:DataRow" Name="CurrentRow" />
    </sa:ActivityAction.Argument>
    <sa:Sequence DisplayName="Process Row">
      <local:LogMessage Level="Info"
                        Message="[&quot;Processing row: &quot; + CurrentRow(&quot;InvoiceNumber&quot;).ToString()]"
                        DisplayName="Log Current Row"
                        sap2010:WorkflowViewState.IdRef="LogMessage_1" />
      <sa:Assign DisplayName="Get Invoice Number"
                 sap2010:WorkflowViewState.IdRef="Assign_1">
        <sa:Assign.To>
          <OutArgument x:TypeArguments="x:String">[currentInvoiceNumber]</OutArgument>
        </sa:Assign.To>
        <sa:Assign.Value>
          <InArgument x:TypeArguments="x:String">[CurrentRow("InvoiceNumber").ToString()]</InArgument>
        </sa:Assign.Value>
      </sa:Assign>
    </sa:Sequence>
  </sa:ActivityAction>
</sa:ForEach>
```

**Key points:**
- `TypeArguments` is `sd:DataRow` (requires `xmlns:sd="clr-namespace:System.Data;assembly=System.Data"`)
- `Values` must call `.AsEnumerable()` on the DataTable for LINQ compatibility
- The `ActivityAction` / `DelegateInArgument` structure is mandatory (not just a plain body)
- Loop body should be wrapped in a `Sequence` if it contains multiple activities
- Access row values with `CurrentRow("ColumnName").ToString()` in VB.NET or `CurrentRow["ColumnName"].ToString()` in C#

**ForEach with string collection:**
```xml
<sa:ForEach x:TypeArguments="x:String"
            Values="[fileList]"
            DisplayName="For Each File Path"
            sap2010:WorkflowViewState.IdRef="ForEach_2">
  <sa:ActivityAction x:TypeArguments="x:String">
    <sa:ActivityAction.Argument>
      <DelegateInArgument x:TypeArguments="x:String" Name="currentFile" />
    </sa:ActivityAction.Argument>
    <sa:Sequence DisplayName="Process File">
      <local:LogMessage Level="Info"
                        Message="[&quot;Processing file: &quot; + currentFile]"
                        DisplayName="Log File"
                        sap2010:WorkflowViewState.IdRef="LogMessage_2" />
    </sa:Sequence>
  </sa:ActivityAction>
</sa:ForEach>
```

---

## Pattern 4: TryCatch with BusinessRuleException

Structured error handling with separate catch blocks for business rule exceptions and system exceptions.

```xml
<sa:TryCatch DisplayName="Handle Transaction Errors"
             sap2010:WorkflowViewState.IdRef="TryCatch_1">
  <sa:TryCatch.Try>
    <sa:Sequence DisplayName="Transaction Processing">
      <local:LogMessage Level="Info"
                        Message="[&quot;Processing transaction: &quot; + transactionItem.Reference]"
                        DisplayName="Log Transaction Start"
                        sap2010:WorkflowViewState.IdRef="LogMessage_3" />
      <!-- Main processing activities go here -->
      <sa:Assign DisplayName="Mark Success"
                 sap2010:WorkflowViewState.IdRef="Assign_2">
        <sa:Assign.To>
          <OutArgument x:TypeArguments="x:Boolean">[isSuccess]</OutArgument>
        </sa:Assign.To>
        <sa:Assign.Value>
          <InArgument x:TypeArguments="x:Boolean">[True]</InArgument>
        </sa:Assign.Value>
      </sa:Assign>
    </sa:Sequence>
  </sa:TryCatch.Try>
  <sa:TryCatch.Catches>
    <!-- Business Rule Exceptions: data problems that retrying won't fix -->
    <sa:Catch x:TypeArguments="UiPath.Core.BusinessRuleException">
      <sa:ActivityAction x:TypeArguments="UiPath.Core.BusinessRuleException">
        <sa:ActivityAction.Argument>
          <DelegateInArgument x:TypeArguments="UiPath.Core.BusinessRuleException"
                              Name="businessException" />
        </sa:ActivityAction.Argument>
        <sa:Sequence DisplayName="Handle Business Exception">
          <local:LogMessage Level="Warn"
                            Message="[&quot;Business rule violation: &quot; + businessException.Message]"
                            DisplayName="Log Business Exception"
                            sap2010:WorkflowViewState.IdRef="LogMessage_4" />
          <sa:Rethrow DisplayName="Rethrow Business Exception"
                      sap2010:WorkflowViewState.IdRef="Rethrow_1" />
        </sa:Sequence>
      </sa:ActivityAction>
    </sa:Catch>
    <!-- System Exceptions: infrastructure problems that may be fixed by retrying -->
    <sa:Catch x:TypeArguments="System.Exception">
      <sa:ActivityAction x:TypeArguments="System.Exception">
        <sa:ActivityAction.Argument>
          <DelegateInArgument x:TypeArguments="System.Exception"
                              Name="systemException" />
        </sa:ActivityAction.Argument>
        <sa:Sequence DisplayName="Handle System Exception">
          <local:LogMessage Level="Error"
                            Message="[&quot;System error: &quot; + systemException.Message + Environment.NewLine + systemException.StackTrace]"
                            DisplayName="Log System Exception"
                            sap2010:WorkflowViewState.IdRef="LogMessage_5" />
          <sa:Rethrow DisplayName="Rethrow System Exception"
                      sap2010:WorkflowViewState.IdRef="Rethrow_2" />
        </sa:Sequence>
      </sa:ActivityAction>
    </sa:Catch>
  </sa:TryCatch.Catches>
</sa:TryCatch>
```

**Key points:**
- The BusinessRuleException `TypeArguments` is `UiPath.Core.BusinessRuleException` (fully qualified)
- System exceptions use `System.Exception`
- Always put the more specific Catch (BusinessRuleException) before the generic one (System.Exception)
- Each `Catch` requires the full `ActivityAction` / `DelegateInArgument` structure
- Never leave Catch blocks empty (XL-B007 violation) -- at minimum log the error
- Use `Rethrow` to propagate exceptions to the REFramework

---

## Pattern 5: InvokeWorkflowFile with Arguments

Invoke a sub-workflow passing In, Out, and InOut arguments.

```xml
<local:InvokeWorkflowFile WorkflowFileName="Framework\ProcessTransaction.xaml"
                          DisplayName="Process Transaction"
                          sap2010:WorkflowViewState.IdRef="InvokeWorkflowFile_1">
  <local:InvokeWorkflowFile.Arguments>
    <scg:Dictionary x:TypeArguments="x:String, s:Argument">
      <InArgument x:TypeArguments="x:Object"
                  x:Key="in_TransactionItem">[transactionItem]</InArgument>
      <InArgument x:TypeArguments="x:Object"
                  x:Key="in_Config">[in_Config]</InArgument>
      <InOutArgument x:TypeArguments="x:Object"
                     x:Key="io_RetryCounter">[retryCounter]</InOutArgument>
      <OutArgument x:TypeArguments="x:Object"
                   x:Key="out_ProcessingResult">[processingResult]</OutArgument>
    </scg:Dictionary>
  </local:InvokeWorkflowFile.Arguments>
</local:InvokeWorkflowFile>
```

**Key points:**
- Use `WorkflowFileName` (not `FileName` or `FilePath`)
- Arguments are wrapped in a `<scg:Dictionary x:TypeArguments="x:String, s:Argument">`
- Each argument uses `InArgument`, `OutArgument`, or `InOutArgument` with `x:Key` for the argument name
- The `x:TypeArguments` on arguments is typically `x:Object` (runtime type resolution)
- Workflow path is relative to the project root
- Values are VB.NET/C# expressions wrapped in `[brackets]`

**Simple invocation without arguments:**
```xml
<local:InvokeWorkflowFile WorkflowFileName="Framework\KillAllProcesses.xaml"
                          DisplayName="Kill All Processes"
                          sap2010:WorkflowViewState.IdRef="InvokeWorkflowFile_2" />
```

---

## Pattern 6: AddQueueItem with SpecificContent

Add a new item to an Orchestrator queue with custom data fields.

```xml
<uo:AddQueueItem QueueName="[in_Config(&quot;OrchestratorQueueName&quot;)]"
                 Priority="Normal"
                 Reference="[&quot;INV-&quot; + invoiceNumber]"
                 DisplayName="Add Invoice to Queue"
                 sap2010:WorkflowViewState.IdRef="AddQueueItem_1">
  <uo:AddQueueItem.ItemInformation>
    <scg:Dictionary x:TypeArguments="x:String, s:Argument">
      <InArgument x:TypeArguments="x:Object"
                  x:Key="InvoiceNumber">[invoiceNumber]</InArgument>
      <InArgument x:TypeArguments="x:Object"
                  x:Key="VendorName">[vendorName]</InArgument>
      <InArgument x:TypeArguments="x:Object"
                  x:Key="Amount">[invoiceAmount.ToString()]</InArgument>
      <InArgument x:TypeArguments="x:Object"
                  x:Key="DueDate">[dueDate.ToString("yyyy-MM-dd")]</InArgument>
    </scg:Dictionary>
  </uo:AddQueueItem.ItemInformation>
</uo:AddQueueItem>
```

**Key points:**
- Use `ItemInformation` child element (not `SpecificContent` -- that is the coded workflow property name, not the XAML property)
- Custom data fields go inside a `scg:Dictionary` as `InArgument` elements with `x:Key`
- `QueueName` should reference Config.xlsx, not be hardcoded (XL-B001)
- `Priority` values: `High`, `Normal`, `Low`
- `Reference` is a searchable identifier string for the queue item
- `DeferDate` and `DueDate` are optional DateTime values for scheduling

---

## Pattern 7: GetRobotCredential

Retrieve credentials securely from Orchestrator.

```xml
<uc:GetRobotCredential AssetName="ApplicationCredential"
                       DisplayName="Get Application Credential"
                       sap2010:WorkflowViewState.IdRef="GetRobotCredential_1">
  <uc:GetRobotCredential.Username>
    <OutArgument x:TypeArguments="x:String">[username]</OutArgument>
  </uc:GetRobotCredential.Username>
  <uc:GetRobotCredential.Password>
    <OutArgument x:TypeArguments="System.Security.SecureString">[securePassword]</OutArgument>
  </uc:GetRobotCredential.Password>
</uc:GetRobotCredential>
```

**Key points:**
- `AssetName` is the name of the Credential asset in Orchestrator
- `Password` output type is `System.Security.SecureString` (not `x:String`)
- To use SecureString password in TypeInto, convert: `new System.Net.NetworkCredential("", securePassword).Password`
- Never store the converted password in a String variable (XL-S001 violation)

**Using the credential for login:**
```xml
<ui:NTypeInto Text="[username]"
              EmptyField="SingleSpace"
              DisplayName="Type Username"
              sap2010:WorkflowViewState.IdRef="NTypeInto_3">
  <ui:NTypeInto.Target>
    <ui:Target Selector="&lt;html app='chrome.exe' /&gt;&lt;webctrl tag='input' id='username' /&gt;" />
  </ui:NTypeInto.Target>
</ui:NTypeInto>
<ui:NTypeInto Text="[new System.Net.NetworkCredential(&quot;&quot;, securePassword).Password]"
              EmptyField="SingleSpace"
              DisplayName="Type Password"
              sap2010:WorkflowViewState.IdRef="NTypeInto_4">
  <ui:NTypeInto.Target>
    <ui:Target Selector="&lt;html app='chrome.exe' /&gt;&lt;webctrl tag='input' id='password' type='password' /&gt;" />
  </ui:NTypeInto.Target>
</ui:NTypeInto>
```

---

## Pattern 8: HttpClient with Headers

Make an HTTP API call with custom headers, authentication, and response handling.

```xml
<local:RetryScope NumberOfRetries="3"
                  RetryInterval="00:00:05"
                  DisplayName="Retry API Call"
                  sap2010:WorkflowViewState.IdRef="RetryScope_1">
  <uw:HttpClient EndPoint="[in_Config(&quot;ApiBaseUrl&quot;) + &quot;/api/v2/invoices&quot;]"
                 Method="POST"
                 AcceptFormat="JSON"
                 BodyFormat="application/json"
                 DisplayName="Create Invoice via API"
                 ContinueOnError="False"
                 TimeoutMS="30000"
                 sap2010:WorkflowViewState.IdRef="HttpClient_1">
    <uw:HttpClient.Headers>
      <scg:Dictionary x:TypeArguments="x:String, x:String">
        <x:String x:Key="Authorization">[&quot;Bearer &quot; + apiToken]</x:String>
        <x:String x:Key="Content-Type">application/json</x:String>
        <x:String x:Key="X-Request-Id">[Guid.NewGuid().ToString()]</x:String>
      </scg:Dictionary>
    </uw:HttpClient.Headers>
    <uw:HttpClient.Body>
      <InArgument x:TypeArguments="x:String">[requestBody]</InArgument>
    </uw:HttpClient.Body>
    <uw:HttpClient.ResponseContent>
      <OutArgument x:TypeArguments="x:String">[responseContent]</OutArgument>
    </uw:HttpClient.ResponseContent>
    <uw:HttpClient.ResponseStatus>
      <OutArgument x:TypeArguments="x:String">[responseStatus]</OutArgument>
    </uw:HttpClient.ResponseStatus>
    <uw:HttpClient.StatusCode>
      <OutArgument x:TypeArguments="System.Net.HttpStatusCode">[statusCode]</OutArgument>
    </uw:HttpClient.StatusCode>
  </uw:HttpClient>
</local:RetryScope>
```

**Key points:**
- `EndPoint` (not `Url` or `Uri`) -- this is the most common LLM mistake on HttpClient
- `Method` values are UPPERCASE: `GET`, `POST`, `PUT`, `PATCH`, `DELETE`, `HEAD`, `OPTIONS`
- `AcceptFormat` values: `ANY`, `JSON`, `XML`, `TEXT`
- `BodyFormat` values: `application/json`, `application/xml`, `text/plain`, `multipart/form-data`
- `ResponseContent` (not `ResponseBody`) returns the response string
- Headers use a `scg:Dictionary x:TypeArguments="x:String, x:String"`
- Always wrap HTTP calls in a `RetryScope` (XL-B003 best practice)
- Never hardcode the endpoint URL (XL-B001)
- Never hardcode API tokens (XL-S003)

**GET request (simpler):**
```xml
<uw:HttpClient EndPoint="[apiUrl]"
               Method="GET"
               AcceptFormat="JSON"
               DisplayName="Get Invoice Data"
               sap2010:WorkflowViewState.IdRef="HttpClient_2">
  <uw:HttpClient.ResponseContent>
    <OutArgument x:TypeArguments="x:String">[responseJson]</OutArgument>
  </uw:HttpClient.ResponseContent>
</uw:HttpClient>
```

---

## Pattern 9: ReadRange with Excel Scope

Read data from an Excel worksheet into a DataTable.

```xml
<ue:ExcelApplicationScope DisplayName="Excel Application Scope"
                          sap2010:WorkflowViewState.IdRef="ExcelApplicationScope_1">
  <ue:ExcelApplicationScope.WorkbookPath>
    <InArgument x:TypeArguments="x:String">[in_Config(&quot;InputFilePath&quot;)]</InArgument>
  </ue:ExcelApplicationScope.WorkbookPath>
  <ue:ExcelApplicationScope.Body>
    <sa:Sequence DisplayName="Excel Operations">
      <ue:ReadRange SheetName="Transactions"
                    Range=""
                    AddHeaders="True"
                    PreserveFormat="True"
                    DisplayName="Read Transaction Data"
                    sap2010:WorkflowViewState.IdRef="ReadRange_1">
        <ue:ReadRange.DataTable>
          <OutArgument x:TypeArguments="sd:DataTable">[dt_Transactions]</OutArgument>
        </ue:ReadRange.DataTable>
      </ue:ReadRange>
      <local:LogMessage Level="Info"
                        Message="[&quot;Read &quot; + dt_Transactions.Rows.Count.ToString() + &quot; rows from Excel&quot;]"
                        DisplayName="Log Row Count"
                        sap2010:WorkflowViewState.IdRef="LogMessage_6" />
    </sa:Sequence>
  </ue:ExcelApplicationScope.Body>
</ue:ExcelApplicationScope>
```

**Key points:**
- `ReadRange` MUST be inside an `ExcelApplicationScope`
- `Range=""` reads the entire used range (starting from A1)
- `Range="A1:F100"` reads a specific range
- `AddHeaders="True"` uses the first row as column headers
- `DataTable` output goes in a child element with `OutArgument`
- `SheetName` is the worksheet tab name (not the file name)
- The activity is `ReadRange` (not `ReadExcel`, `ExcelRead`, or `ReadWorksheet`)

---

## Pattern 10: RetryScope Wrapping an HTTP Call

Resilient API call with automatic retry on transient failures.

```xml
<local:RetryScope NumberOfRetries="3"
                  RetryInterval="00:00:05"
                  DisplayName="Retry Invoice Submission"
                  sap2010:WorkflowViewState.IdRef="RetryScope_2">
  <sa:Sequence DisplayName="Submit Invoice with Validation">
    <uw:HttpClient EndPoint="[apiEndpoint]"
                   Method="POST"
                   BodyFormat="application/json"
                   AcceptFormat="JSON"
                   DisplayName="Submit Invoice"
                   sap2010:WorkflowViewState.IdRef="HttpClient_3">
      <uw:HttpClient.Body>
        <InArgument x:TypeArguments="x:String">[invoiceJson]</InArgument>
      </uw:HttpClient.Body>
      <uw:HttpClient.ResponseContent>
        <OutArgument x:TypeArguments="x:String">[responseJson]</OutArgument>
      </uw:HttpClient.ResponseContent>
      <uw:HttpClient.StatusCode>
        <OutArgument x:TypeArguments="System.Net.HttpStatusCode">[httpStatusCode]</OutArgument>
      </uw:HttpClient.StatusCode>
    </uw:HttpClient>
    <!-- Validate response -- throw if not successful to trigger retry -->
    <sa:If Condition="[CInt(httpStatusCode) &gt;= 400]"
           DisplayName="Check HTTP Status"
           sap2010:WorkflowViewState.IdRef="If_1">
      <sa:If.Then>
        <sa:Throw DisplayName="Throw on HTTP Error"
                  sap2010:WorkflowViewState.IdRef="Throw_1">
          <sa:Throw.Exception>
            <InArgument x:TypeArguments="s:Exception">[new Exception("HTTP " + CInt(httpStatusCode).ToString() + ": " + responseJson)]</InArgument>
          </sa:Throw.Exception>
        </sa:Throw>
      </sa:If.Then>
    </sa:If>
  </sa:Sequence>
</local:RetryScope>
```

**Key points:**
- `RetryScope` has `NumberOfRetries` (integer) and `RetryInterval` (TimeSpan format `HH:MM:SS`)
- The activity inside RetryScope will be re-executed if it throws an exception
- Wrap HTTP call + validation in a Sequence so the status check also retries
- Throw an exception on non-200 status codes to trigger the retry
- Consider that 4xx errors (client errors) often should NOT be retried -- only 5xx and network errors

---

## Pattern 11: Assign with DataTable LINQ Expression

Assign the result of a LINQ query on a DataTable to a variable.

```xml
<!-- Filter DataTable rows using LINQ -->
<sa:Assign DisplayName="Filter Active Invoices"
           sap2010:WorkflowViewState.IdRef="Assign_3">
  <sa:Assign.To>
    <OutArgument x:TypeArguments="sd:DataTable">[dt_ActiveInvoices]</OutArgument>
  </sa:Assign.To>
  <sa:Assign.Value>
    <InArgument x:TypeArguments="sd:DataTable">[dt_AllInvoices.AsEnumerable().Where(Function(row) row("Status").ToString() = "Active").CopyToDataTable()]</InArgument>
  </sa:Assign.Value>
</sa:Assign>
```

**VB.NET LINQ expressions (default UiPath language):**
```xml
<!-- Count matching rows -->
<sa:Assign DisplayName="Count Pending Items"
           sap2010:WorkflowViewState.IdRef="Assign_4">
  <sa:Assign.To>
    <OutArgument x:TypeArguments="x:Int32">[pendingCount]</OutArgument>
  </sa:Assign.To>
  <sa:Assign.Value>
    <InArgument x:TypeArguments="x:Int32">[dt_Items.AsEnumerable().Where(Function(r) r("Status").ToString() = "Pending").Count()]</InArgument>
  </sa:Assign.Value>
</sa:Assign>

<!-- Sum a numeric column -->
<sa:Assign DisplayName="Calculate Total Amount"
           sap2010:WorkflowViewState.IdRef="Assign_5">
  <sa:Assign.To>
    <OutArgument x:TypeArguments="x:Double">[totalAmount]</OutArgument>
  </sa:Assign.To>
  <sa:Assign.Value>
    <InArgument x:TypeArguments="x:Double">[dt_Invoices.AsEnumerable().Sum(Function(row) CDbl(row("Amount")))]</InArgument>
  </sa:Assign.Value>
</sa:Assign>

<!-- Get first matching value -->
<sa:Assign DisplayName="Get Customer Email"
           sap2010:WorkflowViewState.IdRef="Assign_6">
  <sa:Assign.To>
    <OutArgument x:TypeArguments="x:String">[customerEmail]</OutArgument>
  </sa:Assign.To>
  <sa:Assign.Value>
    <InArgument x:TypeArguments="x:String">[dt_Customers.AsEnumerable().Where(Function(r) r("CustomerID").ToString() = customerId).First()("Email").ToString()]</InArgument>
  </sa:Assign.Value>
</sa:Assign>
```

**C# LINQ expressions (for C# projects):**
```xml
<!-- Filter with C# lambda -->
<sa:Assign DisplayName="Filter Active Invoices"
           sap2010:WorkflowViewState.IdRef="Assign_7">
  <sa:Assign.To>
    <OutArgument x:TypeArguments="sd:DataTable">[dt_ActiveInvoices]</OutArgument>
  </sa:Assign.To>
  <sa:Assign.Value>
    <InArgument x:TypeArguments="sd:DataTable">[dt_AllInvoices.AsEnumerable().Where(row => row["Status"].ToString() == "Active").CopyToDataTable()]</InArgument>
  </sa:Assign.Value>
</sa:Assign>
```

**Key points:**
- Always use `AsEnumerable()` before LINQ operations on DataTable
- `CopyToDataTable()` converts the LINQ result back to DataTable (throws if empty -- guard with `.Any()` check)
- `Function(row)` is VB.NET lambda syntax; `row =>` is C# lambda syntax
- Do not mix VB.NET and C# syntax within the same project (XL-B005)
- Use `CDbl()`, `CInt()`, `CDate()` for VB.NET type conversion; `Convert.ToDouble()`, etc. for C#

---

## Pattern 12: If with Condition Checking TransactionItem

Conditional logic based on queue transaction item properties.

```xml
<sa:If Condition="[transactionItem IsNot Nothing]"
       DisplayName="Check Transaction Item Exists"
       sap2010:WorkflowViewState.IdRef="If_2">
  <sa:If.Then>
    <sa:Sequence DisplayName="Process Transaction">
      <!-- Extract SpecificContent fields from the queue item -->
      <sa:Assign DisplayName="Get Invoice Number from Queue"
                 sap2010:WorkflowViewState.IdRef="Assign_8">
        <sa:Assign.To>
          <OutArgument x:TypeArguments="x:String">[invoiceNumber]</OutArgument>
        </sa:Assign.To>
        <sa:Assign.Value>
          <InArgument x:TypeArguments="x:String">[transactionItem.SpecificContent("InvoiceNumber").ToString()]</InArgument>
        </sa:Assign.Value>
      </sa:Assign>
      <sa:Assign DisplayName="Get Amount from Queue"
                 sap2010:WorkflowViewState.IdRef="Assign_9">
        <sa:Assign.To>
          <OutArgument x:TypeArguments="x:Double">[invoiceAmount]</OutArgument>
        </sa:Assign.To>
        <sa:Assign.Value>
          <InArgument x:TypeArguments="x:Double">[CDbl(transactionItem.SpecificContent("Amount"))]</InArgument>
        </sa:Assign.Value>
      </sa:Assign>
      <!-- Validate business rules -->
      <sa:If Condition="[invoiceAmount &gt; 1000000]"
             DisplayName="Check Amount Limit"
             sap2010:WorkflowViewState.IdRef="If_3">
        <sa:If.Then>
          <sa:Throw DisplayName="Throw Amount Exceeds Limit"
                    sap2010:WorkflowViewState.IdRef="Throw_2">
            <sa:Throw.Exception>
              <InArgument x:TypeArguments="UiPath.Core.BusinessRuleException">[new UiPath.Core.BusinessRuleException("Invoice amount " + invoiceAmount.ToString("C") + " exceeds the limit of $1,000,000")]</InArgument>
            </sa:Throw.Exception>
          </sa:Throw>
        </sa:If.Then>
      </sa:If>
      <local:LogMessage Level="Info"
                        Message="[&quot;Validated transaction: &quot; + transactionItem.Reference + &quot; Amount: &quot; + invoiceAmount.ToString(&quot;C&quot;)]"
                        DisplayName="Log Validation Success"
                        sap2010:WorkflowViewState.IdRef="LogMessage_7" />
    </sa:Sequence>
  </sa:If.Then>
  <sa:If.Else>
    <local:LogMessage Level="Warn"
                      Message="Transaction item is Nothing -- no more items to process"
                      DisplayName="Log No More Items"
                      sap2010:WorkflowViewState.IdRef="LogMessage_8" />
  </sa:If.Else>
</sa:If>
```

**Key points:**
- `If.Then` and `If.Else` each take exactly ONE child activity (wrap multiples in Sequence)
- Use `IsNot Nothing` (VB.NET) or `!= null` (C#) for null checks
- Access queue item fields via `transactionItem.SpecificContent("FieldName")`
- Use `>` as `&gt;` and `<` as `&lt;` in XML attribute values
- Throw `UiPath.Core.BusinessRuleException` for data validation failures (REFramework will NOT retry)
- Throw or let propagate `System.Exception` for system failures (REFramework WILL retry)

---

## Complete Workflow Template

A full minimal workflow combining several patterns:

```xml
<Activity x:Class="InvoiceProcessing.ProcessTransaction"
          xmlns="http://schemas.uipath.com/workflow/activities"
          xmlns:x="http://schemas.microsoft.com/winfx/2006/xaml"
          xmlns:sap2010="http://schemas.microsoft.com/netfx/2010/xaml/activities/presentation"
          xmlns:scg="clr-namespace:System.Collections.Generic;assembly=mscorlib"
          xmlns:sa="clr-namespace:System.Activities.Statements;assembly=System.Activities"
          xmlns:s="clr-namespace:System.Activities;assembly=System.Activities"
          xmlns:local="clr-namespace:UiPath.Core.Activities;assembly=UiPath.Core.Activities"
          xmlns:ui="clr-namespace:UiPath.UIAutomationNext.Activities;assembly=UiPath.UIAutomationNext.Activities"
          xmlns:uc="clr-namespace:UiPath.Credentials.Activities;assembly=UiPath.Credentials.Activities"
          xmlns:sd="clr-namespace:System.Data;assembly=System.Data"
          xmlns:mc="http://schemas.openxmlformats.org/markup-compatibility/2006"
          sap2010:ExpressionActivityEditor.ExpressionActivityEditor="C#">
  <x:Members>
    <x:Property Name="in_TransactionItem" Type="InArgument(UiPath.Core.QueueItem)" />
    <x:Property Name="in_Config" Type="InArgument(scg:Dictionary(x:String, x:Object))" />
  </x:Members>
  <sa:Sequence DisplayName="Process Transaction">
    <sa:Sequence.Variables>
      <Variable x:TypeArguments="x:String" Name="invoiceNumber" />
      <Variable x:TypeArguments="x:Double" Name="invoiceAmount" />
    </sa:Sequence.Variables>
    <local:LogMessage Level="Info"
                      Message="[&quot;Start ProcessTransaction: &quot; + in_TransactionItem.Reference]"
                      DisplayName="Log Start"
                      sap2010:WorkflowViewState.IdRef="LogMessage_Start" />
    <sa:TryCatch DisplayName="Main Error Handler"
                 sap2010:WorkflowViewState.IdRef="TryCatch_Main">
      <sa:TryCatch.Try>
        <sa:Sequence DisplayName="Business Logic">
          <sa:Assign DisplayName="Get Invoice Number"
                     sap2010:WorkflowViewState.IdRef="Assign_InvNum">
            <sa:Assign.To>
              <OutArgument x:TypeArguments="x:String">[invoiceNumber]</OutArgument>
            </sa:Assign.To>
            <sa:Assign.Value>
              <InArgument x:TypeArguments="x:String">[in_TransactionItem.SpecificContent("InvoiceNumber").ToString()]</InArgument>
            </sa:Assign.Value>
          </sa:Assign>
          <ui:NClick ClickType="CLICK_SINGLE"
                     MouseButton="BTN_LEFT"
                     DisplayName="Click Search Field"
                     sap2010:WorkflowViewState.IdRef="NClick_Search">
            <ui:NClick.Target>
              <ui:Target Selector="&lt;html app='chrome.exe' /&gt;&lt;webctrl tag='input' id='search' /&gt;" />
            </ui:NClick.Target>
          </ui:NClick>
          <ui:NTypeInto Text="[invoiceNumber]"
                        EmptyField="SingleSpace"
                        ClickBeforeTyping="True"
                        DisplayName="Type Invoice Number"
                        sap2010:WorkflowViewState.IdRef="NTypeInto_Search">
            <ui:NTypeInto.Target>
              <ui:Target Selector="&lt;html app='chrome.exe' /&gt;&lt;webctrl tag='input' id='search' /&gt;" />
            </ui:NTypeInto.Target>
          </ui:NTypeInto>
          <ui:NClick ClickType="CLICK_SINGLE"
                     MouseButton="BTN_LEFT"
                     DisplayName="Click Submit"
                     sap2010:WorkflowViewState.IdRef="NClick_Submit">
            <ui:NClick.Target>
              <ui:Target Selector="&lt;html app='chrome.exe' /&gt;&lt;webctrl tag='button' aaname='Submit' /&gt;" />
            </ui:NClick.Target>
          </ui:NClick>
        </sa:Sequence>
      </sa:TryCatch.Try>
      <sa:TryCatch.Catches>
        <sa:Catch x:TypeArguments="UiPath.Core.BusinessRuleException">
          <sa:ActivityAction x:TypeArguments="UiPath.Core.BusinessRuleException">
            <sa:ActivityAction.Argument>
              <DelegateInArgument x:TypeArguments="UiPath.Core.BusinessRuleException"
                                  Name="bizEx" />
            </sa:ActivityAction.Argument>
            <sa:Sequence DisplayName="Handle Business Rule">
              <local:LogMessage Level="Warn"
                                Message="[&quot;BRE: &quot; + bizEx.Message]"
                                DisplayName="Log Business Exception"
                                sap2010:WorkflowViewState.IdRef="LogMessage_BRE" />
              <sa:Rethrow DisplayName="Rethrow BRE"
                          sap2010:WorkflowViewState.IdRef="Rethrow_BRE" />
            </sa:Sequence>
          </sa:ActivityAction>
        </sa:Catch>
        <sa:Catch x:TypeArguments="System.Exception">
          <sa:ActivityAction x:TypeArguments="System.Exception">
            <sa:ActivityAction.Argument>
              <DelegateInArgument x:TypeArguments="System.Exception"
                                  Name="sysEx" />
            </sa:ActivityAction.Argument>
            <sa:Sequence DisplayName="Handle System Error">
              <local:LogMessage Level="Error"
                                Message="[&quot;System error: &quot; + sysEx.Message]"
                                DisplayName="Log System Exception"
                                sap2010:WorkflowViewState.IdRef="LogMessage_SysEx" />
              <sa:Rethrow DisplayName="Rethrow System Exception"
                          sap2010:WorkflowViewState.IdRef="Rethrow_SysEx" />
            </sa:Sequence>
          </sa:ActivityAction>
        </sa:Catch>
      </sa:TryCatch.Catches>
    </sa:TryCatch>
    <local:LogMessage Level="Info"
                      Message="[&quot;End ProcessTransaction: &quot; + in_TransactionItem.Reference]"
                      DisplayName="Log End"
                      sap2010:WorkflowViewState.IdRef="LogMessage_End" />
  </sa:Sequence>
</Activity>
```

---

## Anti-Patterns to Avoid

### 1. Selector as Direct Attribute on NClick/NTypeInto
```xml
<!-- WRONG -->
<ui:NClick Selector="<html /><webctrl id='btn' />" DisplayName="Click" />

<!-- CORRECT -->
<ui:NClick DisplayName="Click">
  <ui:NClick.Target>
    <ui:Target Selector="&lt;html /&gt;&lt;webctrl id='btn' /&gt;" />
  </ui:NClick.Target>
</ui:NClick>
```

### 2. Multiple Activities in If.Then Without Sequence
```xml
<!-- WRONG: Two activities directly in If.Then -->
<sa:If.Then>
  <local:LogMessage Level="Info" Message="Step 1" />
  <local:LogMessage Level="Info" Message="Step 2" />
</sa:If.Then>

<!-- CORRECT: Wrap in Sequence -->
<sa:If.Then>
  <sa:Sequence>
    <local:LogMessage Level="Info" Message="Step 1" />
    <local:LogMessage Level="Info" Message="Step 2" />
  </sa:Sequence>
</sa:If.Then>
```

### 3. ForEach Without ActivityAction Structure
```xml
<!-- WRONG: No ActivityAction wrapper -->
<sa:ForEach x:TypeArguments="x:String" Values="[items]">
  <sa:Sequence>
    <local:LogMessage Level="Info" Message="[item]" />
  </sa:Sequence>
</sa:ForEach>

<!-- CORRECT: Full ActivityAction structure -->
<sa:ForEach x:TypeArguments="x:String" Values="[items]">
  <sa:ActivityAction x:TypeArguments="x:String">
    <sa:ActivityAction.Argument>
      <DelegateInArgument x:TypeArguments="x:String" Name="item" />
    </sa:ActivityAction.Argument>
    <sa:Sequence>
      <local:LogMessage Level="Info" Message="[item]" />
    </sa:Sequence>
  </sa:ActivityAction>
</sa:ForEach>
```

### 4. TryCatch Without Catches Block
```xml
<!-- WRONG: No Catches -->
<sa:TryCatch>
  <sa:TryCatch.Try>
    <local:LogMessage Level="Info" Message="Trying..." />
  </sa:TryCatch.Try>
</sa:TryCatch>

<!-- CORRECT: Include Catches -->
<sa:TryCatch>
  <sa:TryCatch.Try>
    <local:LogMessage Level="Info" Message="Trying..." />
  </sa:TryCatch.Try>
  <sa:TryCatch.Catches>
    <sa:Catch x:TypeArguments="System.Exception">
      <!-- ... handler ... -->
    </sa:Catch>
  </sa:TryCatch.Catches>
</sa:TryCatch>
```

### 5. Unescaped XML Characters in Selectors
```xml
<!-- WRONG: Raw < and > in selector string -->
<ui:Target Selector="<html app='chrome.exe' /><webctrl id='btn' />" />

<!-- CORRECT: Escaped -->
<ui:Target Selector="&lt;html app='chrome.exe' /&gt;&lt;webctrl id='btn' /&gt;" />
```
