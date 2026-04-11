# XAML Lint Rules Reference

## Purpose

This document provides a complete reference of all XAML lint rules implemented in the `xaml_lint` engine. These rules detect hallucinated activities, security vulnerabilities, and best practice violations in LLM-generated UiPath XAML.

The linter is invoked after code generation to catch and fix issues before the XAML reaches UiPath Studio. Each rule has an ID, severity, detection logic, and suggested fix.

---

## Rule Severity Levels

| Severity | Meaning | Action |
|----------|---------|--------|
| **ERROR** | Invalid XAML that will fail to compile or run | Must fix before output |
| **WARNING** | Security vulnerability or credential misuse | Should fix; flag to user |
| **INFO** | Best practice violation; technically valid but poor quality | Suggest improvement |

---

## Hallucination Rules (ERROR)

These rules detect mistakes that LLMs commonly make when generating UiPath XAML. All fire at ERROR severity because the resulting XAML would fail to compile or behave incorrectly.

### XL-H001: Unknown/Hallucinated Activity Names

**Severity:** ERROR
**Category:** HALLUCINATION
**Source:** `rules_hallucination.py::lint_unknown_activities`

**What it detects:** Element names in the XAML that do not match any known UiPath activity in the `VALID_ACTIVITIES` registry. LLMs frequently invent plausible-sounding activity names that do not exist.

**Example of bad XAML:**
```xml
<!-- WRONG: "ReadExcel" is not a real UiPath activity -->
<ReadExcel DisplayName="Read Invoice Data"
           FilePath="C:\Data\invoices.xlsx"
           SheetName="Sheet1" />
```

**How to fix:**
```xml
<!-- CORRECT: Use ReadRange inside ExcelApplicationScope -->
<ue:ExcelApplicationScope DisplayName="Excel Application Scope"
                          WorkbookPath="C:\Data\invoices.xlsx">
  <ue:ExcelApplicationScope.Body>
    <sa:Sequence DisplayName="Excel Operations">
      <ue:ReadRange DisplayName="Read Invoice Data"
                    SheetName="Sheet1"
                    Range=""
                    DataTable="[dt_Invoices]"
                    AddHeaders="True" />
    </sa:Sequence>
  </ue:ExcelApplicationScope.Body>
</ue:ExcelApplicationScope>
```

**Common hallucinated names and corrections:**

| Hallucinated | Correct |
|-------------|---------|
| `ReadExcel` | `ReadRange` (inside `ExcelApplicationScope`) |
| `ClickButton` | `NClick` |
| `SetVariable` | `Assign` |
| `Log` | `LogMessage` |
| `HttpRequest` | `HttpClient` |
| `CreateDataTable` | `BuildDataTable` |
| `AddToQueue` | `AddQueueItem` |
| `Wait` / `Sleep` | `Delay` |
| `ForEachRow` | `ForEach` with `TypeArgument="System.Data.DataRow"` |

---

### XL-H002: Missing xmlns Namespace Declarations

**Severity:** ERROR
**Category:** NAMESPACE
**Source:** `rules_hallucination.py::lint_missing_namespaces`

**What it detects:** Namespace prefixes used in element tags or TypeArgument attributes that are not declared in the root `<Activity>` element's `xmlns:` attributes. LLMs often use namespace prefixes without declaring them.

**Example of bad XAML:**
```xml
<!-- WRONG: "uw" prefix is used but never declared -->
<Activity x:Class="MyProject.Main"
          xmlns="http://schemas.uipath.com/workflow/activities"
          xmlns:x="http://schemas.microsoft.com/winfx/2006/xaml">
  <sa:Sequence>
    <uw:HttpClient EndPoint="https://api.example.com/data"
                   Method="GET" />
  </sa:Sequence>
</Activity>
```

**How to fix:**
```xml
<!-- CORRECT: Declare all xmlns prefixes on the root element -->
<Activity x:Class="MyProject.Main"
          xmlns="http://schemas.uipath.com/workflow/activities"
          xmlns:x="http://schemas.microsoft.com/winfx/2006/xaml"
          xmlns:sa="clr-namespace:System.Activities.Statements;assembly=System.Activities"
          xmlns:uw="clr-namespace:UiPath.Web.Activities;assembly=UiPath.Web.Activities">
  <sa:Sequence>
    <uw:HttpClient EndPoint="https://api.example.com/data"
                   Method="GET" />
  </sa:Sequence>
</Activity>
```

**Well-known valid prefixes that are always accepted:** `x`, `scg`, `sco`, `local`, `mca`, `sap2010`, `mc`, `p`, `s`

---

### XL-H003: Invalid Enum Values

**Severity:** ERROR
**Category:** ENUM
**Source:** `rules_hallucination.py::lint_invalid_enum_values`

**What it detects:** Property values that do not match the known valid enum values for that property. Checks both element attributes and child element text content. Skips expression values (those starting with `[` or `{`).

**Example of bad XAML:**
```xml
<!-- WRONG: "Left" is not a valid MouseButton value -->
<ui:NClick ClickType="Single"
           MouseButton="Left"
           DisplayName="Click Submit" />
```

**How to fix:**
```xml
<!-- CORRECT: Use the proper enum constants -->
<ui:NClick ClickType="CLICK_SINGLE"
           MouseButton="BTN_LEFT"
           DisplayName="Click Submit" />
```

**Most commonly hallucinated enum values:**

| Property | LLM Hallucinates | Correct Value |
|----------|-----------------|---------------|
| `ClickType` | `Single`, `Double`, `Click` | `CLICK_SINGLE`, `CLICK_DOUBLE` |
| `MouseButton` | `Left`, `Right`, `Middle` | `BTN_LEFT`, `BTN_RIGHT`, `BTN_MIDDLE` |
| `Level` (LogMessage) | `Information`, `Warning`, `Debug` | `Info`, `Warn`, `Trace` |
| `Method` (HttpClient) | `Get`, `Post`, `Put` | `GET`, `POST`, `PUT` |
| `EmptyField` | `True`, `False`, `Clear` | `None`, `Zero`, `SingleSpace` |
| `InputMode` | `Default`, `Native`, `API` | `Simulate`, `HardwareEvents`, `ChromiumAPI`, `WindowMessages` |

---

### XL-H004: Wrong Parent-Child Nesting

**Severity:** ERROR
**Category:** NESTING
**Source:** `rules_hallucination.py::lint_wrong_nesting`

**What it detects:** Structural nesting violations in control flow activities. Validates:
- `If.Then` / `If.Else` each contain exactly one child activity
- `ForEach.Body` contains an `ActivityAction` (ideally wrapping a `Sequence`)
- `TryCatch` has both `TryCatch.Try` and `TryCatch.Catches` blocks
- `TryCatch.Try` is not empty

**Example of bad XAML:**
```xml
<!-- WRONG: If.Then has two direct children (must wrap in Sequence) -->
<sa:If Condition="[isValid]" DisplayName="Check Validity">
  <sa:If.Then>
    <local:LogMessage Level="Info" Message="Valid item" />
    <ui:NClick DisplayName="Click Submit" />
  </sa:If.Then>
</sa:If>
```

**How to fix:**
```xml
<!-- CORRECT: Wrap multiple activities in a Sequence -->
<sa:If Condition="[isValid]" DisplayName="Check Validity">
  <sa:If.Then>
    <sa:Sequence DisplayName="Process Valid Item">
      <local:LogMessage Level="Info" Message="Valid item" />
      <ui:NClick DisplayName="Click Submit" />
    </sa:Sequence>
  </sa:If.Then>
</sa:If>
```

**Example of bad TryCatch:**
```xml
<!-- WRONG: Missing TryCatch.Catches -->
<sa:TryCatch DisplayName="Handle Errors">
  <sa:TryCatch.Try>
    <local:LogMessage Level="Info" Message="Trying..." />
  </sa:TryCatch.Try>
  <!-- No Catches block! -->
</sa:TryCatch>
```

**How to fix:**
```xml
<!-- CORRECT: Include both Try and Catches -->
<sa:TryCatch DisplayName="Handle Errors">
  <sa:TryCatch.Try>
    <local:LogMessage Level="Info" Message="Trying..." />
  </sa:TryCatch.Try>
  <sa:TryCatch.Catches>
    <sa:Catch x:TypeArguments="s:Exception">
      <sa:ActivityAction x:TypeArguments="s:Exception">
        <sa:ActivityAction.Argument>
          <DelegateInArgument x:TypeArguments="s:Exception" Name="exception" />
        </sa:ActivityAction.Argument>
        <local:LogMessage Level="Error"
                          Message="[&quot;Error: &quot; + exception.Message]" />
      </sa:ActivityAction>
    </sa:Catch>
  </sa:TryCatch.Catches>
</sa:TryCatch>
```

---

### XL-H005: Non-Existent Activity Properties

**Severity:** ERROR
**Category:** PROPERTY
**Source:** `rules_hallucination.py::lint_nonexistent_properties`

**What it detects:** Attributes on activity elements that are not in the `VALID_PROPERTIES` registry for that activity type. Only checks activities that have a defined property set. Skips framework attributes (`xmlns`, `x:Class`, `x:Name`, etc.).

**Example of bad XAML:**
```xml
<!-- WRONG: "Selector" and "FileName" are not valid properties -->
<ui:NClick Selector="<html /><webctrl id='btn' />"
           DisplayName="Click Button" />

<local:InvokeWorkflowFile FileName="ProcessData.xaml"
                          DisplayName="Process Data" />
```

**How to fix:**
```xml
<!-- CORRECT: Use Target child element for NClick -->
<ui:NClick DisplayName="Click Button">
  <ui:NClick.Target>
    <ui:Target Selector="&lt;html /&gt;&lt;webctrl id='btn' /&gt;" />
  </ui:NClick.Target>
</ui:NClick>

<!-- CORRECT: Use WorkflowFileName for InvokeWorkflowFile -->
<local:InvokeWorkflowFile WorkflowFileName="ProcessData.xaml"
                          DisplayName="Process Data" />
```

**Common wrong property names:**

| Activity | Wrong Property | Correct Property |
|----------|---------------|-----------------|
| `NClick` | `Selector` | `Target` (child element) |
| `NTypeInto` | `ClearBeforeTyping` | `EmptyField` |
| `NGetText` | `Result`, `Output` | `Value` |
| `InvokeWorkflowFile` | `FileName`, `FilePath` | `WorkflowFileName` |
| `HttpClient` | `Url`, `Uri` | `EndPoint` |
| `HttpClient` | `ResponseBody` | `ResponseContent` |
| `AddQueueItem` | `SpecificContent` | `ItemInformation` |
| `LogMessage` | `Text` | `Message` |

---

### XL-H006: Broken ViewState References

**Severity:** ERROR
**Category:** VIEWSTATE
**Source:** `rules_hallucination.py::lint_broken_viewstate`

**What it detects:** `ViewStateData` entries that reference IdRef values with no matching `sap2010:WorkflowViewState.IdRef` attribute on any activity. This happens when LLMs generate ViewState blocks for activities they later renamed or removed.

**Example of bad XAML:**
```xml
<!-- Activity references IdRef "Click_1" -->
<ui:NClick DisplayName="Click Submit"
           sap2010:WorkflowViewState.IdRef="NClick_1" />

<!-- But ViewState references "Click_OLD" which doesn't exist -->
<sap2010:ViewStateData Id="Click_OLD">
  <sap:WorkflowViewStateService.ViewState>
    <scg:Dictionary x:TypeArguments="x:String, x:Object">
      <x:Boolean x:Key="IsExpanded">True</x:Boolean>
    </scg:Dictionary>
  </sap:WorkflowViewStateService.ViewState>
</sap2010:ViewStateData>
```

**How to fix:** Ensure every `ViewStateData Id` matches a `sap2010:WorkflowViewState.IdRef` on an actual activity element. Remove orphaned ViewState entries. Alternatively, regenerate all ViewState blocks from scratch to match the current activity tree.

---

### XL-H007: Invalid TypeArgument Values

**Severity:** ERROR
**Category:** TYPE_ARGUMENT
**Source:** `rules_hallucination.py::lint_invalid_type_arguments`

**What it detects:** `TypeArgument` attribute values that are not valid .NET type names. Checks against a registry of known primitive types, system types, collection types, and UiPath types.

**Example of bad XAML:**
```xml
<!-- WRONG: "x:DataTable" is not valid; x: prefix is for primitives -->
<sa:ForEach x:TypeArguments="x:DataTable"
            Values="[dataTables]"
            DisplayName="For Each Table" />

<!-- WRONG: "Integer" is not a valid .NET type name -->
<sa:ForEach x:TypeArguments="Integer"
            Values="[numbers]"
            DisplayName="For Each Number" />
```

**How to fix:**
```xml
<!-- CORRECT: Use System.Data.DataTable -->
<sa:ForEach x:TypeArguments="System.Data.DataTable"
            Values="[dataTables]"
            DisplayName="For Each Table" />

<!-- CORRECT: Use x:Int32 -->
<sa:ForEach x:TypeArguments="x:Int32"
            Values="[numbers]"
            DisplayName="For Each Number" />
```

**Common invalid TypeArguments:**

| Invalid | Correct |
|---------|---------|
| `x:DataTable` | `System.Data.DataTable` |
| `x:DataRow` | `System.Data.DataRow` |
| `x:Array` | `scg:List(x:String)` |
| `x:List` | `scg:List(x:String)` |
| `Integer` | `x:Int32` |
| `Long` | `x:Int64` |
| `Bool` | `x:Boolean` |
| `x:Exception` | `s:Exception` or `System.Exception` |

---

### XL-H008: Duplicate DisplayName Values

**Severity:** ERROR
**Category:** HALLUCINATION
**Source:** `rules_hallucination.py::lint_duplicate_display_names`

**What it detects:** Multiple activities within the same scope (Sequence, Flowchart, etc.) that share the same `DisplayName` value. This causes ambiguity in the designer and can break ViewState references.

**Example of bad XAML:**
```xml
<sa:Sequence DisplayName="Main">
  <ui:NClick DisplayName="Click Submit" />
  <local:Delay Duration="00:00:02" DisplayName="Wait" />
  <!-- WRONG: Same DisplayName as first NClick -->
  <ui:NClick DisplayName="Click Submit" />
</sa:Sequence>
```

**How to fix:**
```xml
<sa:Sequence DisplayName="Main">
  <ui:NClick DisplayName="Click Submit Button" />
  <local:Delay Duration="00:00:02" DisplayName="Wait for Page Load" />
  <ui:NClick DisplayName="Click Confirm Button" />
</sa:Sequence>
```

**Best practice:** Use descriptive, unique DisplayNames that indicate the purpose of each activity. Include the target element or step number when multiple similar activities exist.

---

## Security Rules (WARNING)

These rules detect security vulnerabilities in the XAML. They fire at WARNING severity because the XAML is technically valid but exposes sensitive data.

### XL-S001: Passwords as String Instead of SecureString

**Severity:** WARNING
**Category:** SECURITY
**Source:** `rules_security.py::lint_string_passwords`

**What it detects:** Variables or arguments with password-like names (`password`, `pwd`, `secret`, `apikey`, `token`, `auth_token`, `client_secret`, `access_key`, `private_key`) that are typed as `String` instead of `System.Security.SecureString`.

**Example of bad XAML:**
```xml
<!-- WRONG: Password variable typed as String -->
<Variable x:TypeArguments="x:String" Name="userPassword" />
```

**How to fix:**
```xml
<!-- CORRECT: Use SecureString type -->
<Variable x:TypeArguments="System.Security.SecureString" Name="userPassword" />
```

---

### XL-S002: Credentials Passed as Workflow Arguments

**Severity:** WARNING
**Category:** CREDENTIAL
**Source:** `rules_security.py::lint_credential_arguments`

**What it detects:** In arguments with credential-like names (matching password/secret patterns) when the workflow does not use `GetRobotCredential`. This indicates credentials are being passed from a caller instead of retrieved securely from Orchestrator.

**Example of bad XAML:**
```xml
<!-- WRONG: Password passed as an In argument -->
<x:Members>
  <x:Property Name="in_Username" Type="InArgument(x:String)" />
  <x:Property Name="in_Password" Type="InArgument(x:String)" />
</x:Members>
```

**How to fix:**
```xml
<!-- CORRECT: Retrieve credentials from Orchestrator inside the workflow -->
<uc:GetRobotCredential AssetName="ApplicationCredential"
                       DisplayName="Get Credential"
                       Username="[username]"
                       Password="[securePassword]" />
```

---

### XL-S003: Hardcoded Secrets/API Keys

**Severity:** WARNING
**Category:** SECURITY
**Source:** `rules_security.py::lint_hardcoded_secrets`

**What it detects:** Literal values in XAML attributes or text content that match patterns for:
- API keys (32+ character alphanumeric strings)
- AWS access keys (`AKIA` prefix)
- Bearer tokens
- Basic auth headers
- JWT tokens (`eyJ` prefix)
- Hex-encoded secrets (32+ hex characters)

Also flags attributes with secret-like names (`password`, `apikey`, `token`, etc.) that contain literal (non-expression) values.

**Example of bad XAML:**
```xml
<!-- WRONG: Hardcoded API key -->
<uw:HttpClient DisplayName="Call API">
  <uw:HttpClient.Headers>
    <scg:Dictionary x:TypeArguments="x:String, x:String">
      <x:String x:Key="Authorization">Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6...</x:String>
    </scg:Dictionary>
  </uw:HttpClient.Headers>
</uw:HttpClient>
```

**How to fix:**
```xml
<!-- CORRECT: Retrieve from Orchestrator Asset -->
<local:GetRobotAsset DisplayName="Get API Key"
                     AssetName="ApiKey"
                     Result="[apiKey]" />
<uw:HttpClient DisplayName="Call API">
  <uw:HttpClient.Headers>
    <scg:Dictionary x:TypeArguments="x:String, x:String">
      <x:String x:Key="Authorization">[&quot;Bearer &quot; + apiKey]</x:String>
    </scg:Dictionary>
  </uw:HttpClient.Headers>
</uw:HttpClient>
```

---

### XL-S004: Plaintext Connection Strings

**Severity:** WARNING
**Category:** SECURITY
**Source:** `rules_security.py::lint_plaintext_connection_strings`

**What it detects:** Database connection strings containing plaintext passwords. Looks for patterns like `Password=xxx` or `Pwd=xxx` combined with connection string indicators (`Server=`, `Data Source=`, `Initial Catalog=`, `Database=`, `Provider=`, `Driver=`, `DSN=`).

**Example of bad XAML:**
```xml
<!-- WRONG: Plaintext password in connection string -->
<sa:Assign DisplayName="Set Connection String">
  <sa:Assign.To>
    <OutArgument x:TypeArguments="x:String">[connectionString]</OutArgument>
  </sa:Assign.To>
  <sa:Assign.Value>
    <InArgument x:TypeArguments="x:String">Server=db.example.com;Database=AppDB;User Id=app_user;Password=P@ssw0rd123;</InArgument>
  </sa:Assign.Value>
</sa:Assign>
```

**How to fix:**
```xml
<!-- CORRECT: Store connection string in Config.xlsx, retrieve password separately -->
<uc:GetRobotCredential AssetName="DatabaseCredential"
                       DisplayName="Get DB Credential"
                       Username="[dbUser]"
                       Password="[dbPassword]" />
<sa:Assign DisplayName="Build Connection String">
  <sa:Assign.To>
    <OutArgument x:TypeArguments="x:String">[connectionString]</OutArgument>
  </sa:Assign.To>
  <sa:Assign.Value>
    <InArgument x:TypeArguments="x:String">[String.Format("Server={0};Database={1};User Id={2};Password={3};", in_Config("DbServer"), in_Config("DbName"), dbUser, New System.Net.NetworkCredential("", dbPassword).Password)]</InArgument>
  </sa:Assign.Value>
</sa:Assign>
```

---

## Best Practice Rules (INFO)

These rules detect patterns that are technically valid but indicate poor quality or maintainability issues.

### XL-B001: Hardcoded URLs

**Severity:** INFO
**Category:** CONFIG
**Source:** `rules_best_practices.py::lint_hardcoded_urls`

**What it detects:** Literal `http://` or `https://` URLs in attribute values or text content. Schema/namespace URLs (e.g., `http://schemas.uipath.com/`, `http://schemas.microsoft.com/`) are excluded.

**Example of bad XAML:**
```xml
<uw:HttpClient EndPoint="https://api.production.example.com/v2/invoices"
               Method="GET"
               DisplayName="Get Invoices" />
```

**How to fix:**
```xml
<!-- Reference URL from Config.xlsx -->
<uw:HttpClient EndPoint="[in_Config(&quot;ApiBaseUrl&quot;) + &quot;/v2/invoices&quot;]"
               Method="GET"
               DisplayName="Get Invoices" />
```

---

### XL-B002: Missing LogMessage Activities

**Severity:** INFO
**Category:** BEST_PRACTICE
**Source:** `rules_best_practices.py::lint_missing_log_messages`

**What it detects:** Workflows that contain zero `LogMessage` activities anywhere in the XAML tree.

**How to fix:** Add `LogMessage` activities at minimum at workflow start and completion. Best practice is to log before and after critical operations, on exceptions, and at key decision points.

```xml
<local:LogMessage Level="Info"
                  Message="[&quot;Starting workflow: ProcessInvoice for &quot; + transactionItem.Reference]"
                  DisplayName="Log Start" />
```

---

### XL-B003: Missing RetryScope on API Calls

**Severity:** INFO
**Category:** BEST_PRACTICE
**Source:** `rules_best_practices.py::lint_missing_retry_scope`

**What it detects:** `HttpClient`, `DeserializeJson`, `SerializeJson`, or `InvokeMethod` activities that are not nested inside a `RetryScope` activity.

**Example of bad XAML:**
```xml
<!-- WRONG: HTTP call without retry protection -->
<uw:HttpClient EndPoint="[apiUrl]"
               Method="GET"
               DisplayName="Call API" />
```

**How to fix:**
```xml
<!-- CORRECT: Wrap in RetryScope -->
<local:RetryScope NumberOfRetries="3"
                  RetryInterval="00:00:05"
                  DisplayName="Retry API Call">
  <uw:HttpClient EndPoint="[apiUrl]"
                 Method="GET"
                 DisplayName="Call API" />
</local:RetryScope>
```

---

### XL-B004: Missing TryCatch Wrapper

**Severity:** INFO
**Category:** BEST_PRACTICE
**Source:** `rules_best_practices.py::lint_missing_try_catch`

**What it detects:** Top-level workflow body (first Sequence, Flowchart, or StateMachine) that does not contain a `TryCatch` as a direct child.

**How to fix:** Wrap the main workflow logic in a TryCatch. The Catch block should log the error and optionally capture a screenshot for debugging.

---

### XL-B005: C# Syntax in VB.NET Expressions

**Severity:** INFO
**Category:** BEST_PRACTICE
**Source:** `rules_best_practices.py::lint_csharp_in_vbnet`

**What it detects:** C# syntax patterns in expression attributes (`Condition`, `Value`, `To`, `Expression`) when the project uses VB.NET (detected by presence of `VisualBasicSettings`/`VisualBasicValue` elements without `CSharpValue`/`CSharpReference`).

**Detected C# patterns:**
- `!=` (VB: `<>`)
- `&&` (VB: `AndAlso`)
- `||` (VB: `OrElse`)
- `var x =` (VB: `Dim x =`)
- `null` (VB: `Nothing`)
- `$"..."` interpolation (VB: `String.Format`)
- `=>` lambda (VB: `Function`/`Sub`)
- `//` comments (VB: `'`)
- `typeof()` (VB: `GetType()`)
- `new Type()` (VB: `New Type()`)

**Example of bad XAML (VB.NET project):**
```xml
<sa:If Condition="[item != null &amp;&amp; item.Status == &quot;Active&quot;]"
       DisplayName="Check Item" />
```

**How to fix:**
```xml
<sa:If Condition="[item IsNot Nothing AndAlso item.Status = &quot;Active&quot;]"
       DisplayName="Check Item" />
```

---

### XL-B006: Placeholder Selectors

**Severity:** INFO
**Category:** BEST_PRACTICE
**Source:** `rules_best_practices.py::lint_placeholder_selectors`

**What it detects:** Selector, Target, or SearchProperties attributes/elements containing placeholder markers: `TODO`, `PLACEHOLDER`, `FIXME`, `XXX`, `CHANGEME`, `{{...}}`, `<REPLACE>`, `[REPLACE]`, `ENTER_VALUE_HERE`, `YOUR_*_HERE`, `FILL_IN`.

**Example of bad XAML:**
```xml
<ui:NClick DisplayName="Click Login">
  <ui:NClick.Target>
    <ui:Target Selector="&lt;html /&gt;&lt;webctrl id='TODO_REPLACE_ME' /&gt;" />
  </ui:NClick.Target>
</ui:NClick>
```

**How to fix:** Replace placeholder selectors with actual UI selectors captured using UiPath's Indicate on Screen feature or the Selector Builder.

---

### XL-B007: Empty Catch Blocks

**Severity:** INFO
**Category:** BEST_PRACTICE
**Source:** `rules_best_practices.py::lint_empty_catch_blocks`

**What it detects:** `Catch` elements inside `TryCatch.Catches` that have no activity content in their body. Empty Catch blocks silently swallow exceptions, making debugging extremely difficult.

**Example of bad XAML:**
```xml
<sa:TryCatch.Catches>
  <sa:Catch x:TypeArguments="s:Exception">
    <sa:ActivityAction x:TypeArguments="s:Exception">
      <sa:ActivityAction.Argument>
        <DelegateInArgument x:TypeArguments="s:Exception" Name="exception" />
      </sa:ActivityAction.Argument>
      <!-- WRONG: Empty Sequence = swallowed exception -->
      <sa:Sequence DisplayName="Handle Exception" />
    </sa:ActivityAction>
  </sa:Catch>
</sa:TryCatch.Catches>
```

**How to fix:**
```xml
<sa:TryCatch.Catches>
  <sa:Catch x:TypeArguments="s:Exception">
    <sa:ActivityAction x:TypeArguments="s:Exception">
      <sa:ActivityAction.Argument>
        <DelegateInArgument x:TypeArguments="s:Exception" Name="exception" />
      </sa:ActivityAction.Argument>
      <sa:Sequence DisplayName="Handle Exception">
        <local:LogMessage Level="Error"
                          Message="[&quot;Error: &quot; + exception.Message + Environment.NewLine + exception.StackTrace]"
                          DisplayName="Log Exception" />
      </sa:Sequence>
    </sa:ActivityAction>
  </sa:Catch>
</sa:TryCatch.Catches>
```

---

### XL-B008: Magic Numbers in Timeouts/Delays

**Severity:** INFO
**Category:** CONFIG
**Source:** `rules_best_practices.py::lint_magic_numbers`

**What it detects:**
- `Delay` activities with hardcoded `Duration` values (e.g., `"00:00:05"`)
- Any activity with a hardcoded numeric `TimeoutMS` attribute
- Expressions containing `TimeSpan.FromSeconds()` / `TimeSpan.FromMilliseconds()` / `TimeSpan.FromMinutes()` with literal numbers

**Example of bad XAML:**
```xml
<local:Delay Duration="00:00:10" DisplayName="Wait for Page" />
<ui:NClick TimeoutMS="60000" DisplayName="Click Submit" />
```

**How to fix:**
```xml
<local:Delay Duration="[TimeSpan.FromSeconds(CDbl(in_Config(&quot;PageLoadWaitSeconds&quot;)))]"
            DisplayName="Wait for Page" />
<ui:NClick TimeoutMS="[CInt(in_Config(&quot;ClickTimeoutMS&quot;))]"
           DisplayName="Click Submit" />
```

---

## Quick Reference Table

| Rule ID | Severity | Category | One-Line Description |
|---------|----------|----------|---------------------|
| XL-H001 | ERROR | Hallucination | Unknown/invented activity name |
| XL-H002 | ERROR | Namespace | Missing xmlns namespace declaration |
| XL-H003 | ERROR | Enum | Invalid enum property value |
| XL-H004 | ERROR | Nesting | Wrong parent-child nesting structure |
| XL-H005 | ERROR | Property | Non-existent property on activity |
| XL-H006 | ERROR | ViewState | Orphaned ViewState reference |
| XL-H007 | ERROR | TypeArgument | Invalid TypeArgument value |
| XL-H008 | ERROR | Hallucination | Duplicate DisplayName in same scope |
| XL-S001 | WARNING | Security | Password variable typed as String |
| XL-S002 | WARNING | Credential | Credentials passed as In arguments |
| XL-S003 | WARNING | Security | Hardcoded secrets or API keys |
| XL-S004 | WARNING | Security | Plaintext password in connection string |
| XL-B001 | INFO | Config | Hardcoded URL (not schema URL) |
| XL-B002 | INFO | Best Practice | No LogMessage activities in workflow |
| XL-B003 | INFO | Best Practice | API call without RetryScope |
| XL-B004 | INFO | Best Practice | Top-level body without TryCatch |
| XL-B005 | INFO | Best Practice | C# syntax in VB.NET expressions |
| XL-B006 | INFO | Best Practice | Placeholder marker in selector |
| XL-B007 | INFO | Best Practice | Empty Catch block (swallowed exception) |
| XL-B008 | INFO | Config | Hardcoded timeout/delay value |

---

## Implementation Details

### Source Files

| File | Contents |
|------|----------|
| `src/rpa_architect/xaml_lint/rules_hallucination.py` | XL-H001 through XL-H008 |
| `src/rpa_architect/xaml_lint/rules_security.py` | XL-S001 through XL-S004 |
| `src/rpa_architect/xaml_lint/rules_best_practices.py` | XL-B001 through XL-B008 |
| `src/rpa_architect/xaml_lint/known_activities.py` | `VALID_ACTIVITIES`, `VALID_NAMESPACES`, `VALID_ENUMS`, `VALID_PROPERTIES` registries |
| `src/rpa_architect/xaml_lint/models.py` | `LintIssue`, `LintResult`, `LintSeverity`, `LintCategory` models |
| `src/rpa_architect/xaml_lint/engine.py` | Lint engine that runs all rules |

### LintIssue Model

Every rule returns a list of `LintIssue` objects:

```python
class LintIssue(BaseModel):
    rule_id: str          # e.g., "XL-H001"
    severity: LintSeverity  # ERROR, WARNING, INFO
    category: LintCategory  # HALLUCINATION, SECURITY, etc.
    message: str          # Human-readable description
    element_name: str     # Activity or element that triggered the rule
    line_number: int      # Line in the XAML file (0 if unknown)
    suggestion: str       # How to fix the issue
```
