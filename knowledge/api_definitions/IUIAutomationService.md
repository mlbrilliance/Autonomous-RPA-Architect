# IUIAutomationService API Reference

> **Namespace:** `UiPath.UIAutomationNext.API.Contracts`
> **Injection:** `[Service] IUiAutomationAppService uiAutomation`

The primary service for interacting with UI elements in UiPath coded workflows.
Injected via the `[Service]` attribute on a field in a `CodedWorkflow` class.

---

## Methods

### Click

Clicks a UI element identified by a selector or `IScreenTarget`.

```csharp
void Click(
    IScreenTarget target,
    ClickOptions? options = null
);
```

**Parameters:**
| Parameter | Type | Description |
|-----------|------|-------------|
| `target` | `IScreenTarget` | Target element (from `FindElement` or built via `Target.From(selector)`) |
| `options` | `ClickOptions?` | Optional: click type (single/double), mouse button, modifier keys |

**Example:**
```csharp
[Service] IUiAutomationAppService uiAutomation;

[Workflow]
public void ClickLoginButton()
{
    var target = Target.From("<html app='chrome.exe' /><webctrl tag='button' id='loginBtn' />");
    uiAutomation.Click(target);
}
```

---

### TypeInto

Types text into a UI element. Supports special keys via bracket notation `[k(enter)]`.

```csharp
void TypeInto(
    IScreenTarget target,
    string text,
    TypeIntoOptions? options = null
);
```

**Parameters:**
| Parameter | Type | Description |
|-----------|------|-------------|
| `target` | `IScreenTarget` | Target input element |
| `text` | `string` | Text to type. Use `[k(enter)]` for special keys |
| `options` | `TypeIntoOptions?` | Optional: emptyField (clear before typing), delayBetweenKeys |

**Example:**
```csharp
[Workflow]
public void EnterCredentials(string username, string password)
{
    var userField = Target.From("<webctrl tag='input' name='username' />");
    var passField = Target.From("<webctrl tag='input' name='password' />");

    uiAutomation.TypeInto(userField, username, new TypeIntoOptions { EmptyField = true });
    uiAutomation.TypeInto(passField, password, new TypeIntoOptions { EmptyField = true });
}
```

---

### GetText

Extracts text content from a UI element.

```csharp
string GetText(
    IScreenTarget target,
    GetTextOptions? options = null
);
```

**Parameters:**
| Parameter | Type | Description |
|-----------|------|-------------|
| `target` | `IScreenTarget` | Target element to read text from |
| `options` | `GetTextOptions?` | Optional: extraction method (FullText, Native, OCR) |

**Example:**
```csharp
[Workflow]
public string ReadInvoiceNumber()
{
    var target = Target.From("<webctrl tag='span' id='invoiceNum' />");
    return uiAutomation.GetText(target);
}
```

---

### GetAttribute

Retrieves a specific attribute value from a UI element.

```csharp
string GetAttribute(
    IScreenTarget target,
    string attributeName
);
```

**Parameters:**
| Parameter | Type | Description |
|-----------|------|-------------|
| `target` | `IScreenTarget` | Target element |
| `attributeName` | `string` | Attribute name (e.g., "value", "class", "innertext", "checked") |

**Example:**
```csharp
[Workflow]
public bool IsCheckboxChecked()
{
    var target = Target.From("<webctrl tag='input' type='checkbox' id='agree' />");
    var value = uiAutomation.GetAttribute(target, "checked");
    return value == "true";
}
```

---

### ElementExists

Checks whether a UI element exists on screen within an optional timeout.

```csharp
bool ElementExists(
    IScreenTarget target,
    ElementExistsOptions? options = null
);
```

**Parameters:**
| Parameter | Type | Description |
|-----------|------|-------------|
| `target` | `IScreenTarget` | Target element to check |
| `options` | `ElementExistsOptions?` | Optional: timeout in milliseconds |

**Example:**
```csharp
[Workflow]
public bool IsErrorDisplayed()
{
    var target = Target.From("<webctrl tag='div' class='error-message' />");
    return uiAutomation.ElementExists(target, new ElementExistsOptions { Timeout = 3000 });
}
```

---

### ExtractData

Extracts structured data from a repeating UI pattern (e.g., a table).

```csharp
DataTable ExtractData(
    IScreenTarget target,
    ExtractDataOptions? options = null
);
```

**Parameters:**
| Parameter | Type | Description |
|-----------|------|-------------|
| `target` | `IScreenTarget` | Target container element (e.g., table) |
| `options` | `ExtractDataOptions?` | Optional: extraction metadata, max rows, pagination |

**Example:**
```csharp
[Workflow]
public DataTable ScrapeInvoiceTable()
{
    var target = Target.From("<webctrl tag='table' id='invoiceGrid' />");
    return uiAutomation.ExtractData(target);
}
```

---

### Hover

Moves the mouse cursor over a UI element without clicking.

```csharp
void Hover(
    IScreenTarget target,
    HoverOptions? options = null
);
```

**Parameters:**
| Parameter | Type | Description |
|-----------|------|-------------|
| `target` | `IScreenTarget` | Target element to hover over |
| `options` | `HoverOptions?` | Optional: offset position |

**Example:**
```csharp
[Workflow]
public void HoverToShowTooltip()
{
    var target = Target.From("<webctrl tag='span' class='info-icon' />");
    uiAutomation.Hover(target);
    // Wait for tooltip to appear
    System.Threading.Thread.Sleep(500);
}
```

---

### Check / Uncheck

Sets a checkbox or toggle to the checked/unchecked state.

```csharp
void Check(IScreenTarget target);
void Uncheck(IScreenTarget target);
```

**Example:**
```csharp
[Workflow]
public void AcceptTerms()
{
    var target = Target.From("<webctrl tag='input' type='checkbox' id='terms' />");
    uiAutomation.Check(target);
}
```

---

### SelectItem

Selects an item from a dropdown or list control.

```csharp
void SelectItem(
    IScreenTarget target,
    string item
);
```

**Parameters:**
| Parameter | Type | Description |
|-----------|------|-------------|
| `target` | `IScreenTarget` | Target dropdown/list element |
| `item` | `string` | Item text to select |

**Example:**
```csharp
[Workflow]
public void SelectCountry(string country)
{
    var target = Target.From("<webctrl tag='select' name='country' />");
    uiAutomation.SelectItem(target, country);
}
```

---

### WaitForElement

Waits until a UI element appears or vanishes, with a configurable timeout.

```csharp
bool WaitForElement(
    IScreenTarget target,
    WaitForElementOptions? options = null
);
```

**Parameters:**
| Parameter | Type | Description |
|-----------|------|-------------|
| `target` | `IScreenTarget` | Target element to wait for |
| `options` | `WaitForElementOptions?` | Optional: timeout (ms), waitForVanish (bool) |

**Returns:** `true` if element appeared (or vanished) within the timeout.

**Example:**
```csharp
[Workflow]
public void WaitForPageLoad()
{
    var spinner = Target.From("<webctrl tag='div' class='loading-spinner' />");
    uiAutomation.WaitForElement(spinner, new WaitForElementOptions
    {
        Timeout = 30000,
        WaitForVanish = true
    });
}
```

---

### FindElement

Locates a UI element and returns a reference that can be used with other methods.

```csharp
IScreenTarget FindElement(
    IScreenTarget target,
    FindElementOptions? options = null
);
```

**Parameters:**
| Parameter | Type | Description |
|-----------|------|-------------|
| `target` | `IScreenTarget` | Selector-based target to locate |
| `options` | `FindElementOptions?` | Optional: timeout, search scope |

**Example:**
```csharp
[Workflow]
public void InteractWithDynamicElement()
{
    var container = Target.From("<webctrl tag='div' id='results' />");
    var element = uiAutomation.FindElement(container);

    // Use the resolved element for subsequent actions
    uiAutomation.Click(element);
    var text = uiAutomation.GetText(element);
}
```

---

## Common Patterns

### Browser Login Flow

```csharp
[Service] IUiAutomationAppService uiAutomation;
[Service] ISystemService system;

[Workflow]
public void LoginToWebApp(string url, string credentialName)
{
    var cred = system.GetCredential(credentialName);

    // Navigate (use browser service for open/navigate)
    uiAutomation.TypeInto(
        Target.From("<webctrl tag='input' id='email' />"),
        cred.Username,
        new TypeIntoOptions { EmptyField = true }
    );

    uiAutomation.TypeInto(
        Target.From("<webctrl tag='input' id='password' />"),
        cred.Password.ToString(),
        new TypeIntoOptions { EmptyField = true }
    );

    uiAutomation.Click(
        Target.From("<webctrl tag='button' id='submit' />")
    );

    // Wait for dashboard
    uiAutomation.WaitForElement(
        Target.From("<webctrl tag='div' id='dashboard' />"),
        new WaitForElementOptions { Timeout = 15000 }
    );
}
```

### Data Extraction with Validation

```csharp
[Workflow]
public DataTable ExtractAndValidateTable()
{
    var tableTarget = Target.From("<webctrl tag='table' class='data-grid' />");

    if (!uiAutomation.ElementExists(tableTarget, new ElementExistsOptions { Timeout = 5000 }))
    {
        throw new BusinessRuleException("Data table not found on page.");
    }

    var data = uiAutomation.ExtractData(tableTarget);

    if (data.Rows.Count == 0)
    {
        throw new BusinessRuleException("No data rows found in table.");
    }

    return data;
}
```
