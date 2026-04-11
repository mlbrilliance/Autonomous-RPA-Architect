# UiPath Activity Reference for XAML Code Generation

## Purpose

This document is a comprehensive reference of valid UiPath activity names, their XML namespaces, properties, and enum values. It is designed for RAG retrieval during XAML code generation to prevent LLM hallucinations -- invented activity names, wrong property names, invalid enum values, and missing namespace declarations.

All activities listed here are validated against UiPath Studio 24.10+ and are used by the XAML lint engine (`xaml_lint/known_activities.py`) to detect errors.

---

## XML Namespace Declarations

Every UiPath XAML file must declare the namespaces it uses on the root `<Activity>` element. Missing declarations cause XL-H002 lint errors.

### Required Namespaces

```xml
<Activity
  x:Class="ProjectName.WorkflowName"
  xmlns="http://schemas.uipath.com/workflow/activities"
  xmlns:x="http://schemas.microsoft.com/winfx/2006/xaml"
  xmlns:sap2010="http://schemas.microsoft.com/netfx/2010/xaml/activities/presentation"
  xmlns:scg="clr-namespace:System.Collections.Generic;assembly=mscorlib"
  xmlns:sco="clr-namespace:System.Collections.ObjectModel;assembly=mscorlib"
  xmlns:mc="http://schemas.openxmlformats.org/markup-compatibility/2006"
  xmlns:mca="clr-namespace:Microsoft.CSharp.Activities;assembly=System.Activities"
  xmlns:p="http://schemas.microsoft.com/netfx/2009/xaml/activities"
  >
```

### Activity-Specific Namespaces

| Prefix | URI | When to Declare |
|--------|-----|-----------------|
| `ui` | `clr-namespace:UiPath.UIAutomationNext.Activities;assembly=UiPath.UIAutomationNext.Activities` | Any modern N-prefixed UI activity (NClick, NTypeInto, etc.) |
| `uic` | `clr-namespace:UiPath.UIAutomation.Activities;assembly=UiPath.UIAutomation.Activities` | Classic UI activities (Click, TypeInto, etc.) |
| `local` | `clr-namespace:UiPath.Core.Activities;assembly=UiPath.Core.Activities` | Core activities (LogMessage, Assign, RetryScope, InvokeWorkflowFile, etc.) |
| `sa` | `clr-namespace:System.Activities.Statements;assembly=System.Activities` | Control flow (If, ForEach, While, TryCatch, Sequence, etc.) |
| `s` | `clr-namespace:System.Activities;assembly=System.Activities` | InvokeMethod, other System.Activities types |
| `ue` | `clr-namespace:UiPath.Excel.Activities;assembly=UiPath.Excel.Activities` | ReadRange, WriteRange, ExcelApplicationScope |
| `um` | `clr-namespace:UiPath.Mail.Activities;assembly=UiPath.Mail.Activities` | GetIMAPMail, SendMail, etc. |
| `uw` | `clr-namespace:UiPath.Web.Activities;assembly=UiPath.Web.Activities` | HttpClient, DeserializeJson, SerializeJson |
| `up` | `clr-namespace:UiPath.PDF.Activities;assembly=UiPath.PDF.Activities` | ReadPDFText, ReadPDFWithOCR |
| `uo` | `clr-namespace:UiPath.Core.Activities;assembly=UiPath.OrchestratorActivities` | AddQueueItem, GetTransactionItem, SetTransactionStatus |
| `uc` | `clr-namespace:UiPath.Credentials.Activities;assembly=UiPath.Credentials.Activities` | GetRobotCredential |
| `ucsv` | `clr-namespace:UiPath.CSV.Activities;assembly=UiPath.CSV.Activities` | ReadCSV, WriteCSV |
| `sd` | `clr-namespace:System.Data;assembly=System.Data` | DataTable, DataRow type references |

### Common LLM Namespace Mistakes

- **Inventing prefixes without declaring them.** Every `prefix:ActivityName` must have a matching `xmlns:prefix="..."` on the root element.
- **Using wrong assembly names.** The assembly must match exactly. `UiPath.UIAutomation.Activities` (classic) is different from `UiPath.UIAutomationNext.Activities` (modern).
- **Confusing `local` and `sa`.** `local` is for UiPath.Core.Activities; `sa` is for System.Activities.Statements. Assign is in `sa`; LogMessage is in `local`.

---

## Activity Categories

### 1. UI Automation -- Modern (N-Prefixed)

These are the preferred activities in UiPath Studio 24.10+. They use the `UiPath.UIAutomationNext.Activities` namespace.

#### NClick

**Fully Qualified:** `UiPath.UIAutomationNext.Activities.NClick`
**xmlns:** `clr-namespace:UiPath.UIAutomationNext.Activities;assembly=UiPath.UIAutomationNext.Activities`

| Property | Type | Required | Description |
|----------|------|----------|-------------|
| `DisplayName` | String | Yes | Activity label in designer |
| `Target` | Target (child element) | Yes | UI element target with selector |
| `ClickType` | Enum | No | `CLICK_SINGLE`, `CLICK_DOUBLE`, `CLICK_DOWN`, `CLICK_UP` |
| `MouseButton` | Enum | No | `BTN_LEFT`, `BTN_RIGHT`, `BTN_MIDDLE` |
| `KeyModifiers` | Enum | No | `None`, `Alt`, `Ctrl`, `Shift`, `Win` |
| `CursorPosition` | Enum | No | `Center`, `TopLeft`, `TopRight`, `BottomLeft`, `BottomRight` |
| `OffsetX` | Int32 | No | Horizontal offset from CursorPosition |
| `OffsetY` | Int32 | No | Vertical offset from CursorPosition |
| `InputMode` | Enum | No | `Simulate`, `HardwareEvents`, `ChromiumAPI`, `WindowMessages` |
| `DelayAfter` | Int32 | No | Milliseconds to wait after action |
| `DelayBefore` | Int32 | No | Milliseconds to wait before action |
| `ContinueOnError` | Boolean | No | Continue workflow on error |
| `TimeoutMS` | Int32 | No | Timeout in milliseconds |
| `AlterIfDisabled` | Boolean | No | Attempt click even if element is disabled |

**Common mistakes:** Using `Selector` property directly (should be nested `<ui:NClick.Target>` child element). Using `ClickType="Single"` instead of `"CLICK_SINGLE"`. Using `MouseButton="Left"` instead of `"BTN_LEFT"`.

#### NTypeInto

**Fully Qualified:** `UiPath.UIAutomationNext.Activities.NTypeInto`
**xmlns:** `clr-namespace:UiPath.UIAutomationNext.Activities;assembly=UiPath.UIAutomationNext.Activities`

| Property | Type | Required | Description |
|----------|------|----------|-------------|
| `DisplayName` | String | Yes | Activity label |
| `Target` | Target (child element) | Yes | UI element target with selector |
| `Text` | String | Yes | Text to type |
| `ClickBeforeTyping` | Boolean | No | Click the field before typing |
| `EmptyField` | Enum | No | `None`, `Zero`, `SingleSpace` |
| `DelayBetweenKeys` | Enum | No | `0`, `10`, `20`, `50`, `100` (ms) |
| `InputMode` | Enum | No | `Simulate`, `HardwareEvents`, `ChromiumAPI`, `WindowMessages` |
| `DelayAfter` | Int32 | No | Post-action delay (ms) |
| `DelayBefore` | Int32 | No | Pre-action delay (ms) |
| `ContinueOnError` | Boolean | No | Continue on error |
| `TimeoutMS` | Int32 | No | Timeout (ms) |
| `Activate` | Boolean | No | Activate the target window |

**Common mistakes:** Using `EmptyField="True"` (not a valid value -- use `"SingleSpace"` or `"Zero"`). Using `ClearBeforeTyping` instead of `EmptyField`. Using `Text` as a child element instead of attribute.

#### NGetText

**Fully Qualified:** `UiPath.UIAutomationNext.Activities.NGetText`

| Property | Type | Required | Description |
|----------|------|----------|-------------|
| `DisplayName` | String | Yes | Activity label |
| `Target` | Target (child element) | Yes | UI element target |
| `Value` | OutArgument<String> | Yes | Variable to store extracted text |
| `TimeoutMS` | Int32 | No | Timeout (ms) |
| `DelayAfter` | Int32 | No | Post-action delay (ms) |
| `DelayBefore` | Int32 | No | Pre-action delay (ms) |
| `ContinueOnError` | Boolean | No | Continue on error |

**Common mistakes:** Using `Result` or `Output` instead of `Value`. Forgetting `[brackets]` around the output variable expression.

#### NSelectItem

**Fully Qualified:** `UiPath.UIAutomationNext.Activities.NSelectItem`

| Property | Type | Required | Description |
|----------|------|----------|-------------|
| `DisplayName` | String | Yes | Activity label |
| `Target` | Target (child element) | Yes | Dropdown/list element |
| `Item` | String | Yes | Item value or text to select |
| `TimeoutMS` | Int32 | No | Timeout (ms) |
| `DelayAfter` | Int32 | No | Post-action delay (ms) |
| `DelayBefore` | Int32 | No | Pre-action delay (ms) |
| `ContinueOnError` | Boolean | No | Continue on error |

#### NCheck

**Fully Qualified:** `UiPath.UIAutomationNext.Activities.NCheck`

| Property | Type | Required | Description |
|----------|------|----------|-------------|
| `DisplayName` | String | Yes | Activity label |
| `Target` | Target (child element) | Yes | Checkbox/toggle element |
| `Action` | String | Yes | `"Check"` or `"Uncheck"` |
| `TimeoutMS` | Int32 | No | Timeout (ms) |

#### NHover, NDoubleClick, NRightClick, NKeyboardShortcuts, NMouseScroll, NCheckState, NApplicationCard

All use the same `UiPath.UIAutomationNext.Activities` namespace. See `VALID_PROPERTIES` in `known_activities.py` for their specific property sets.

---

### 2. UI Automation -- Classic

These are the legacy activities. Still supported but not recommended for new development.

| Activity | Namespace |
|----------|-----------|
| `Click` | `UiPath.UIAutomation.Activities` |
| `TypeInto` | `UiPath.UIAutomation.Activities` |
| `GetText` | `UiPath.UIAutomation.Activities` |
| `SelectItem` | `UiPath.UIAutomation.Activities` |
| `Check` | `UiPath.UIAutomation.Activities` |
| `Hover` | `UiPath.UIAutomation.Activities` |
| `DoubleClick` | `UiPath.UIAutomation.Activities` |
| `RightClick` | `UiPath.UIAutomation.Activities` |
| `SetText` | `UiPath.UIAutomation.Activities` |
| `SendHotkey` | `UiPath.UIAutomation.Activities` |
| `GetAttribute` | `UiPath.UIAutomation.Activities` |
| `SetFocus` | `UiPath.UIAutomation.Activities` |
| `WaitElement` | `UiPath.UIAutomation.Activities` |
| `ElementExists` | `UiPath.UIAutomation.Activities` |
| `FindElement` | `UiPath.UIAutomation.Activities` |
| `HighlightElement` | `UiPath.UIAutomation.Activities` |
| `AttachBrowser` | `UiPath.UIAutomation.Activities` |
| `AttachWindow` | `UiPath.UIAutomation.Activities` |
| `OpenBrowser` | `UiPath.UIAutomation.Activities` |
| `OpenApplication` | `UiPath.UIAutomation.Activities` |
| `CloseApplication` | `UiPath.UIAutomation.Activities` |
| `CloseTab` | `UiPath.UIAutomation.Activities` |
| `NavigateTo` | `UiPath.UIAutomation.Activities` |
| `GetFullText` | `UiPath.UIAutomation.Activities` |
| `GetVisibleText` | `UiPath.UIAutomation.Activities` |
| `ImageExists` | `UiPath.UIAutomation.Activities` |
| `FindImage` | `UiPath.UIAutomation.Activities` |
| `ClickImage` | `UiPath.UIAutomation.Activities` |
| `Screenshot` | `UiPath.UIAutomation.Activities` |
| `TakeScreenshot` | `UiPath.UIAutomation.Activities` |
| `ExtractStructuredData` | `UiPath.UIAutomation.Activities` |

**Common mistakes:** Using classic `Click` when modern `NClick` is intended. The properties and target specification differ significantly.

---

### 3. Control Flow

All control flow activities use the `System.Activities.Statements` namespace.

#### If

| Property | Type | Required |
|----------|------|----------|
| `DisplayName` | String | Yes |
| `Condition` | InArgument<Boolean> | Yes |
| `sap2010:WorkflowViewState.IdRef` | String | Yes |

**Nesting rules:** Must contain `<If.Then>` with exactly one child activity. Optionally contains `<If.Else>`. Multiple activities inside Then/Else must be wrapped in a `<Sequence>`.

#### ForEach

| Property | Type | Required |
|----------|------|----------|
| `DisplayName` | String | Yes |
| `Values` | InArgument | Yes |
| `TypeArgument` | .NET type | Yes |

**Nesting rules:** Must contain `<ActivityAction>` with `<DelegateInArgument>` and the loop body. Multiple body activities must be wrapped in a `<Sequence>`.

**Valid TypeArgument values for ForEach:**
- `x:String`, `x:Int32`, `x:Object` (primitive iteration)
- `System.Data.DataRow` or `sd:DataRow` (DataTable row iteration)
- `System.IO.FileInfo` (file iteration)
- `UiPath.Core.QueueItem` (queue item iteration)

#### While / DoWhile

| Property | Type | Required |
|----------|------|----------|
| `DisplayName` | String | Yes |
| `Condition` | InArgument<Boolean> | Yes |

#### Switch

| Property | Type | Required |
|----------|------|----------|
| `DisplayName` | String | Yes |
| `Expression` | InArgument | Yes |
| `TypeArgument` | .NET type | Yes |

#### Sequence

| Property | Type | Required |
|----------|------|----------|
| `DisplayName` | String | Yes |

#### Flowchart, FlowDecision, FlowStep, FlowSwitch

All in `System.Activities.Statements`.

#### StateMachine, State, FinalState

All in `System.Activities.Statements`.

#### Parallel, ParallelForEach, Pick, PickBranch

All in `System.Activities.Statements`.

---

### 4. Data Operations

| Activity | Namespace | Key Properties |
|----------|-----------|---------------|
| `Assign` | `System.Activities.Statements` | `To`, `Value` |
| `MultipleAssign` | `UiPath.Core.Activities` | (child elements) |
| `BuildDataTable` | `UiPath.Core.Activities` | `DataTable`, `TableInfo` |
| `AddDataRow` | `UiPath.Core.Activities` | `DataTable`, `DataRow`, `ArrayRow` |
| `AddDataColumn` | `UiPath.Core.Activities` | |
| `FilterDataTable` | `UiPath.Core.Activities` | `DataTable`, `OutputDataTable`, `FilterRows`, `SelectColumns` |
| `SortDataTable` | `UiPath.Core.Activities` | |
| `JoinDataTables` | `UiPath.Core.Activities` | |
| `LookupDataTable` | `UiPath.Core.Activities` | |
| `MergeDataTable` | `UiPath.Core.Activities` | |
| `OutputDataTable` | `UiPath.Core.Activities` | |
| `RemoveDataColumn` | `UiPath.Core.Activities` | |
| `RemoveDuplicateRows` | `UiPath.Core.Activities` | |

**Common mistakes:** Using `SetVariable` instead of `Assign`. Using `CreateDataTable` instead of `BuildDataTable`.

---

### 5. Error Handling

| Activity | Namespace | Key Properties |
|----------|-----------|---------------|
| `TryCatch` | `System.Activities.Statements` | (child elements: `TryCatch.Try`, `TryCatch.Catches`, `TryCatch.Finally`) |
| `Catch` | `System.Activities.Statements` | `TypeArgument` (exception type) |
| `Throw` | `System.Activities.Statements` | `Exception` |
| `Rethrow` | `System.Activities.Statements` | (none) |
| `RetryScope` | `UiPath.Core.Activities` | `NumberOfRetries`, `RetryInterval` |
| `TerminateWorkflow` | `System.Activities.Statements` | |

**TryCatch nesting rules:**
- Must have `<TryCatch.Try>` containing exactly one activity
- Must have `<TryCatch.Catches>` with at least one `<Catch>`
- Each `<Catch>` requires `TypeArgument` (e.g., `s:Exception`, `UiPath.Core.BusinessRuleException`)
- `<TryCatch.Finally>` is optional

**Common mistakes:** Using `CatchBlock` instead of `Catch`. Omitting `TypeArgument` on Catch. Using `Exception` as the element name instead of `Catch` with a `TypeArgument`.

---

### 6. File System

| Activity | Namespace | Key Properties |
|----------|-----------|---------------|
| `CopyFile` | `UiPath.Core.Activities` (System.Activities assembly) | |
| `MoveFile` | `UiPath.Core.Activities` (System.Activities assembly) | |
| `DeleteFile` | `UiPath.Core.Activities` (System.Activities assembly) | |
| `CreateDirectory` | `UiPath.Core.Activities` (System.Activities assembly) | |
| `PathExists` | `UiPath.Core.Activities` (System.Activities assembly) | |
| `ReadTextFile` | `UiPath.Core.Activities` (System.Activities assembly) | `FileName`, `Content`, `Encoding` |
| `WriteTextFile` | `UiPath.Core.Activities` (System.Activities assembly) | `FileName`, `Text`, `Encoding`, `Append` |
| `AppendLine` | `UiPath.Core.Activities` (System.Activities assembly) | |
| `ReadCSV` | `UiPath.CSV.Activities` | |
| `WriteCSV` | `UiPath.CSV.Activities` | |

**Common mistakes:** Using `ReadFile` instead of `ReadTextFile`. Using `WriteFile` instead of `WriteTextFile`. Using `CreateFolder` instead of `CreateDirectory`.

---

### 7. Excel / Integration

| Activity | Namespace | Key Properties |
|----------|-----------|---------------|
| `ExcelApplicationScope` | `UiPath.Excel.Activities` | |
| `ReadRange` | `UiPath.Excel.Activities` | `SheetName`, `Range`, `DataTable`, `AddHeaders`, `PreserveFormat`, `UseFilter` |
| `WriteRange` | `UiPath.Excel.Activities` | `SheetName`, `StartingCell`, `DataTable`, `AddHeaders` |
| `AppendRange` | `UiPath.Excel.Activities` | |
| `WriteCell` | `UiPath.Excel.Activities` | |
| `ReadCell` | `UiPath.Excel.Activities` | |

**Common mistakes:** Using `ReadExcel` instead of `ReadRange`. Using `WriteExcel` instead of `WriteRange`. Forgetting that `ReadRange`/`WriteRange` must be nested inside an `ExcelApplicationScope`.

---

### 8. Orchestrator

| Activity | Namespace | Key Properties |
|----------|-----------|---------------|
| `AddQueueItem` | `UiPath.Core.Activities` (OrchestratorActivities assembly) | `QueueName`, `ItemInformation`, `Priority`, `Reference`, `DeferDate`, `DueDate` |
| `BulkAddQueueItems` | `UiPath.Core.Activities` (OrchestratorActivities assembly) | |
| `GetQueueItem` | `UiPath.Core.Activities` (OrchestratorActivities assembly) | |
| `GetTransactionItem` | `UiPath.Core.Activities` (OrchestratorActivities assembly) | `QueueName`, `TransactionItem` |
| `SetTransactionStatus` | `UiPath.Core.Activities` (OrchestratorActivities assembly) | `TransactionItem`, `Status`, `ErrorType`, `Reason` |
| `GetRobotAsset` | `UiPath.Core.Activities` (OrchestratorActivities assembly) | |

**Common mistakes:** Using `AddToQueue` instead of `AddQueueItem`. Using `GetQueueTransaction` instead of `GetTransactionItem`. Using `SpecificContent` directly on the activity instead of through `ItemInformation` child element.

---

### 9. HTTP / Web

| Activity | Namespace | Key Properties |
|----------|-----------|---------------|
| `HttpClient` | `UiPath.Web.Activities` | `EndPoint`, `Method`, `AcceptFormat`, `Body`, `BodyFormat`, `Headers`, `ResponseContent`, `ResponseStatus`, `StatusCode`, `ContinueOnError`, `TimeoutMS` |
| `DeserializeJson` | `UiPath.Web.Activities` | `JsonString`, `JsonObject`, `TypeArgument` |
| `SerializeJson` | `UiPath.Web.Activities` | |
| `DeserializeXml` | `UiPath.Web.Activities` | |

**Valid Method enum values:** `GET`, `POST`, `PUT`, `PATCH`, `DELETE`, `HEAD`, `OPTIONS`

**Valid AcceptFormat values:** `ANY`, `JSON`, `XML`, `TEXT`

**Valid BodyFormat values:** `application/json`, `application/xml`, `text/plain`, `multipart/form-data`

**Common mistakes:** Using `HttpRequest` instead of `HttpClient`. Using `Method="Get"` (lowercase) instead of `"GET"`. Using `ResponseBody` instead of `ResponseContent`. Using `Url` instead of `EndPoint`.

---

### 10. Invoke Activities

| Activity | Namespace | Key Properties |
|----------|-----------|---------------|
| `InvokeWorkflowFile` | `UiPath.Core.Activities` | `WorkflowFileName`, `Arguments`, `ContinueOnError`, `IsolatedRuntime`, `UnSafe` |
| `InvokeCode` | `UiPath.Core.Activities` | `Code`, `Language`, `Arguments` |
| `InvokeMethod` | `System.Activities` | |
| `InvokePowerShell` | `UiPath.Core.Activities` | |

**Common mistakes:** Using `FileName` instead of `WorkflowFileName` on InvokeWorkflowFile. Using `FilePath` instead of `WorkflowFileName`. Passing arguments as attributes instead of child elements.

---

### 11. Logging / Misc

| Activity | Namespace | Key Properties |
|----------|-----------|---------------|
| `LogMessage` | `UiPath.Core.Activities` | `Level`, `Message` |
| `Comment` | `UiPath.Core.Activities` | `Text` |
| `CommentOut` | `UiPath.Core.Activities` | |
| `Break` | `System.Activities.Statements` | |
| `Continue` | `UiPath.Core.Activities` | |
| `KillProcess` | `UiPath.Core.Activities` | `ProcessName` |
| `ShouldStop` | `UiPath.Core.Activities` | |
| `Delay` | `UiPath.Core.Activities` | `Duration` |
| `MessageBox` | `UiPath.Core.Activities` | `Text`, `Caption`, `Buttons`, `TopMost`, `ChosenButton` |
| `InputDialog` | `UiPath.Core.Activities` | `Title`, `Label`, `Value`, `Result`, `IsPassword`, `Options` |

**Valid LogLevel values:** `Trace`, `Info`, `Warn`, `Error`, `Fatal`

**Common mistakes:** Using `Log` instead of `LogMessage`. Using `Level="Information"` instead of `"Info"`. Using `Level="Warning"` instead of `"Warn"`. Using `Level="Debug"` (not valid -- use `"Trace"`).

---

### 12. Credentials

| Activity | Namespace | Key Properties |
|----------|-----------|---------------|
| `GetRobotCredential` | `UiPath.Credentials.Activities` | `AssetName`, `Username`, `Password` |

**Important:** `Password` output is `SecureString`, not `String`. To use in TypeInto, convert with `new System.Net.NetworkCredential("", securePassword).Password`.

---

### 13. Mail

| Activity | Namespace | Key Properties |
|----------|-----------|---------------|
| `GetIMAPMail` | `UiPath.Mail.Activities` | `Server`, `Port`, `Email`, `Password`, `MailFolder`, `Top`, `OnlyUnreadMessages`, `Messages`, `SecureConnection` |
| `GetPOP3Mail` | `UiPath.Mail.Activities` | |
| `GetOutlookMail` | `UiPath.Mail.Activities` | |
| `SendMail` | `UiPath.Mail.Activities` | `To`, `Subject`, `Body`, `IsBodyHtml`, `Attachments`, `CC`, `BCC`, `From`, `Port`, `Server`, `SecureConnection` |
| `SendOutlookMail` | `UiPath.Mail.Activities` | |
| `SaveMailAttachments` | `UiPath.Mail.Activities` | |
| `MoveMail` | `UiPath.Mail.Activities` | |

---

### 14. PDF

| Activity | Namespace | Key Properties |
|----------|-----------|---------------|
| `ReadPDFText` | `UiPath.PDF.Activities` | |
| `ReadPDFWithOCR` | `UiPath.PDF.Activities` | |

---

## Enum Value Reference

All valid enum values used across UiPath activities. Using any value not in this list triggers XL-H003.

| Enum Property | Valid Values |
|---------------|-------------|
| `ClickType` | `CLICK_SINGLE`, `CLICK_DOUBLE`, `CLICK_DOWN`, `CLICK_UP` |
| `MouseButton` | `BTN_LEFT`, `BTN_RIGHT`, `BTN_MIDDLE` |
| `InputMode` | `Simulate`, `HardwareEvents`, `ChromiumAPI`, `WindowMessages` |
| `KeyModifiers` | `None`, `Alt`, `Ctrl`, `Shift`, `Win` |
| `FilterOperator` | `EQ`, `NE`, `GT`, `GE`, `LT`, `LE`, `StartsWith`, `EndsWith`, `Contains` |
| `JoinType` | `Inner`, `Left`, `Full` |
| `SortDirection` | `Ascending`, `Descending` |
| `MailFolder` | `INBOX`, `Sent`, `Drafts`, `Trash` |
| `BrowserType` | `Chrome`, `Firefox`, `Edge`, `Chromium` |
| `NClickType` | `Single`, `Double` |
| `Position` / `CursorPosition` | `Center`, `TopLeft`, `TopRight`, `BottomLeft`, `BottomRight` |
| `LogLevel` / `Level` | `Trace`, `Info`, `Warn`, `Error`, `Fatal` |
| `TypeOfRead` | `FullText`, `Native`, `OCR` |
| `CompletionType` | `None`, `Auto`, `AtEnd` |
| `DelayBetweenKeys` | `0`, `10`, `20`, `50`, `100` |
| `EmptyField` | `None`, `Zero`, `SingleSpace` |
| `NewLine` | `LF`, `CRLF`, `Environment` |
| `ExistingSheetAction` | `DoNothing`, `Replace`, `Append` |
| `TransactionStatus` | `Successful`, `Failed`, `Abandoned` |
| `RequestMethod` | `GET`, `POST`, `PUT`, `PATCH`, `DELETE`, `HEAD`, `OPTIONS` |
| `AcceptFormat` | `ANY`, `JSON`, `XML`, `TEXT` |
| `BodyFormat` | `application/json`, `application/xml`, `text/plain`, `multipart/form-data` |

---

## Valid TypeArgument Values

Used in `ForEach`, `Switch`, `Catch`, `DeserializeJson`, and other generic activities.

### Primitive Types (x: prefix)

`x:String`, `x:Int32`, `x:Int64`, `x:Boolean`, `x:Double`, `x:Decimal`, `x:Object`, `x:Byte`, `x:Char`, `x:Single`, `x:Int16`, `x:UInt16`, `x:UInt32`, `x:UInt64`, `x:DateTime`, `x:TimeSpan`, `x:Guid`

### System Types (fully qualified)

`System.String`, `System.Int32`, `System.Int64`, `System.Boolean`, `System.Double`, `System.Decimal`, `System.Object`, `System.DateTime`, `System.TimeSpan`, `System.Guid`, `System.Security.SecureString`, `System.Net.HttpStatusCode`

### Data Types

`DataTable`, `DataRow`, `DataColumn`, `System.Data.DataTable`, `System.Data.DataRow`, `System.Data.DataColumn`

### Collection Types (scg: prefix)

`scg:List`, `scg:Dictionary`, `scg:KeyValuePair` -- used as generics, e.g., `scg:List(x:String)`

### JSON Types

`JObject`, `JArray`, `JToken`, `Newtonsoft.Json.Linq.JObject`, `Newtonsoft.Json.Linq.JArray`, `Newtonsoft.Json.Linq.JToken`

### UiPath Types

`UiPath.Core.QueueItem`

### Common LLM Mistakes

- `x:DataTable` -- WRONG. Use `System.Data.DataTable`
- `x:DataRow` -- WRONG. Use `System.Data.DataRow`
- `x:Array` -- WRONG. Use `scg:List(x:String)` or similar
- `x:List` -- WRONG. Use `scg:List`
- `String` without prefix in TypeArgument -- use `x:String`
- `Integer` -- WRONG. Use `x:Int32`
- `Long` -- WRONG. Use `x:Int64`
- `Bool` -- WRONG. Use `x:Boolean`

---

## Top LLM Hallucination Patterns

### Invented Activity Names

| LLM Generates | Correct Activity |
|---------------|-----------------|
| `ReadExcel` | `ReadRange` (inside `ExcelApplicationScope`) |
| `WriteExcel` | `WriteRange` (inside `ExcelApplicationScope`) |
| `ClickButton` | `NClick` (modern) or `Click` (classic) |
| `SetVariable` | `Assign` |
| `Log` | `LogMessage` |
| `HttpRequest` | `HttpClient` |
| `CreateDataTable` | `BuildDataTable` |
| `ReadFile` | `ReadTextFile` |
| `WriteFile` | `WriteTextFile` |
| `CreateFolder` | `CreateDirectory` |
| `AddToQueue` | `AddQueueItem` |
| `GetQueueTransaction` | `GetTransactionItem` |
| `Wait` | `Delay` or `WaitElement` |
| `Sleep` | `Delay` |
| `Print` | `LogMessage` |
| `ForEachRow` | `ForEach` with `TypeArgument="System.Data.DataRow"` |
| `SwitchCase` | `Switch` |
| `CatchException` | `Catch` (inside TryCatch.Catches) |

### Wrong Property Names

| LLM Uses | Correct Property |
|----------|-----------------|
| `Selector` (on NClick) | `Target` (child element) |
| `FileName` (on InvokeWorkflowFile) | `WorkflowFileName` |
| `FilePath` (on InvokeWorkflowFile) | `WorkflowFileName` |
| `Url` (on HttpClient) | `EndPoint` |
| `ResponseBody` (on HttpClient) | `ResponseContent` |
| `Result` (on NGetText) | `Value` |
| `Output` (on NGetText) | `Value` |
| `ClearBeforeTyping` (on NTypeInto) | `EmptyField` |
| `Input` (on various) | `Text` or `Value` (depends on activity) |
| `SpecificContent` (on AddQueueItem) | `ItemInformation` (child element) |

### Invalid Enum Values

| LLM Uses | Correct Value |
|----------|--------------|
| `ClickType="Single"` | `ClickType="CLICK_SINGLE"` |
| `ClickType="Double"` | `ClickType="CLICK_DOUBLE"` |
| `MouseButton="Left"` | `MouseButton="BTN_LEFT"` |
| `MouseButton="Right"` | `MouseButton="BTN_RIGHT"` |
| `Level="Information"` | `Level="Info"` |
| `Level="Warning"` | `Level="Warn"` |
| `Level="Debug"` | `Level="Trace"` |
| `Method="Get"` | `Method="GET"` |
| `Method="Post"` | `Method="POST"` |
| `EmptyField="True"` | `EmptyField="SingleSpace"` |
| `EmptyField="Clear"` | `EmptyField="SingleSpace"` |
