# UiPath Selector Anatomy Guide

## Overview

A UiPath selector is an XML fragment that uniquely identifies a UI element on screen. Selectors are the foundation of UI automation -- every click, type, and read operation uses a selector to find its target element.

Selectors are hierarchical: the first node identifies the top-level window or application, and subsequent child nodes drill down to the specific element.

```xml
<top_level_node attribute='value' />
<child_node attribute='value' />
<target_node attribute='value' />
```

---

## Node Types

### `wnd` -- Windows Desktop Window

Identifies a native Windows window (Win32, WPF, WinForms, UWP).

| Attribute | Description | Example |
|-----------|-------------|---------|
| `app` | Executable filename | `app='notepad.exe'` |
| `cls` | Window class name | `cls='Notepad'` |
| `title` | Window title bar text | `title='Untitled - Notepad'` |
| `name` | UI Automation Name property | `name='Text Editor'` |
| `idx` | Index among sibling windows | `idx='2'` |

```xml
<wnd app='notepad.exe' cls='Notepad' title='*- Notepad' />
```

### `html` -- Web Browser Root

Always the first node for web-based selectors. Identifies the browser process and page.

| Attribute | Description | Example |
|-----------|-------------|---------|
| `app` | Browser executable | `app='chrome.exe'` |
| `title` | Page title | `title='Invoice Portal'` |
| `url` | Page URL (supports wildcards) | `url='https://app.example.com/*'` |

```xml
<html app='chrome.exe' title='Dashboard*' url='https://crm.example.com/*' />
```

### `webctrl` -- Web Element

Identifies an HTML element within a browser page. Must follow an `html` node.

| Attribute | Description | Example |
|-----------|-------------|---------|
| `tag` | HTML tag name | `tag='input'` |
| `id` | Element `id` attribute | `id='username'` |
| `name` | Element `name` attribute | `name='email'` |
| `class` | CSS class (partial match with `*`) | `class='btn-primary'` |
| `aaname` | Accessible/visible name (innerText) | `aaname='Submit'` |
| `type` | Input type attribute | `type='password'` |
| `parentid` | Parent element's `id` | `parentid='loginForm'` |
| `parentclass` | Parent element's CSS class | `parentclass='modal-footer'` |
| `tableRow` | Row index in a table (1-based) | `tableRow='3'` |
| `tableCol` | Column index in a table (1-based) | `tableCol='2'` |
| `idx` | Ordinal index among matches (1-based) | `idx='2'` |
| `href` | Link href pattern | `href='*/invoices'` |
| `css-selector` | Direct CSS selector | `css-selector='[data-testid="save"]'` |
| `isleaf` | Whether element is a leaf node | `isleaf='1'` |
| `visibility` | Visibility state | `visibility='visible'` |

```xml
<html app='chrome.exe' /><webctrl tag='input' id='email' type='text' />
```

### `ctrl` -- UI Automation Control

Identifies a UIA (Microsoft UI Automation) element. Used for desktop apps that expose the UIA tree.

| Attribute | Description | Example |
|-----------|-------------|---------|
| `name` | UIA Name property | `name='Save'` |
| `role` | UIA control type/role | `role='push button'` |
| `automationid` | UIA AutomationId | `automationid='btnSave'` |
| `cls` | UIA ClassName | `cls='Button'` |
| `idx` | Index among matching siblings | `idx='1'` |

```xml
<wnd app='excel.exe' cls='XLMAIN' />
<ctrl name='Sheet1' role='page tab' />
```

### `java` -- Java Application Control

Identifies elements in Java Swing, AWT, or SWT applications. Requires the UiPath Java Bridge extension.

| Attribute | Description | Example |
|-----------|-------------|---------|
| `name` | Component name | `name='OK'` |
| `role` | Java accessibility role | `role='push button'` |
| `cls` | Java class name | `cls='javax.swing.JButton'` |
| `idx` | Index among siblings | `idx='0'` |
| `state` | Component state | `state='enabled,visible'` |

```xml
<wnd cls='SunAwtFrame' />
<java name='Submit' role='push button' cls='javax.swing.JButton' />
```

---

## Wildcards

Wildcards let you match dynamic portions of attribute values.

| Pattern | Meaning | Example |
|---------|---------|---------|
| `*` | Any characters (zero or more) | `title='* - Excel'` |
| `?` | Any single character | `id='btn?'` |

Common wildcard uses:
```xml
<!-- Match any Excel window regardless of filename -->
<wnd app='excel.exe' title='* - Excel' />

<!-- Match URL ignoring query parameters -->
<html app='chrome.exe' url='https://app.example.com/invoices*' />

<!-- Match dynamic CSS classes -->
<webctrl tag='div' class='*container*' />

<!-- Match any dialog class -->
<wnd cls='#32770' title='*' />
```

---

## Best Practices

### 1. Prefer Stable Attributes

**Most stable (use first):**
- `id` -- unique by HTML spec, rarely changes
- `automationid` -- purpose-built for automation
- `name` with `role` -- reliable for labeled controls
- `css-selector` with `data-testid` -- test IDs are automation-friendly

**Moderately stable:**
- `aaname` -- visible label text, may change with localization
- `tag` + `parentid` -- structural but reasonably stable
- `href` with wildcards -- for navigation links

**Fragile (avoid when possible):**
- `idx` -- breaks when elements are added or removed
- `tableRow` / `tableCol` with hardcoded values
- `class` alone -- shared across many elements
- `title` with timestamps or counts

### 2. Use Minimal Selector Depth

Each node in the selector is a point of failure. Remove intermediate nodes that do not contribute to uniqueness.

```xml
<!-- Bad: over-specified, 6 levels deep -->
<html app='chrome.exe' />
<webctrl tag='div' id='root' />
<webctrl tag='div' class='app-container' />
<webctrl tag='form' id='loginForm' />
<webctrl tag='div' class='form-group' />
<webctrl tag='input' id='username' />

<!-- Good: 2 levels, equally unique -->
<html app='chrome.exe' /><webctrl tag='input' id='username' />
```

### 3. Use Wildcards for Dynamic Content

```xml
<!-- Bad: breaks when invoice number changes -->
<wnd title='Invoice INV-2024-001 - SAP' />

<!-- Good: wildcard for the dynamic part -->
<wnd title='Invoice * - SAP' />
```

### 4. Avoid `idx` Unless Necessary

The `idx` attribute depends on the element's position among siblings. Adding or removing any sibling element shifts all indices.

```xml
<!-- Fragile -->
<webctrl tag='button' idx='3' />

<!-- Better: use a distinguishing attribute -->
<webctrl tag='button' aaname='Delete' />
```

If `idx` is unavoidable (e.g., identical buttons in a repeating list), document why and consider using `css-selector` with `:nth-child()` instead.

### 5. Use `aaname` for Visible Labels

The `aaname` (accessible name) attribute corresponds to the visible text label. It is more resilient than auto-generated IDs but may break with UI text changes or localization.

```xml
<!-- Generated ID (fragile) -->
<webctrl tag='button' id='btn_x7k2m' />

<!-- Visible label (resilient) -->
<webctrl tag='button' aaname='Submit Order' />
```

### 6. Use `css-selector` for Modern Web Apps

React, Angular, and Vue apps often generate dynamic IDs and classes. Use `css-selector` with `data-*` attributes when available:

```xml
<html app='chrome.exe' />
<webctrl css-selector='[data-testid="submit-button"]' />
```

### 7. Parameterize Dynamic Selectors

When building selectors programmatically, use string interpolation:

```csharp
// In coded workflow
string selector = $"<html app='chrome.exe' /><webctrl tag='a' aaname='{customerName}' />";
var target = Target.From(selector);
```

---

## Common Patterns

### Web Application Selectors

```xml
<!-- Text input by ID -->
<html app='chrome.exe' /><webctrl tag='input' id='email' />

<!-- Button by visible text -->
<html app='chrome.exe' /><webctrl tag='button' aaname='Submit' />

<!-- Link by partial href -->
<html app='chrome.exe' /><webctrl tag='a' href='*/dashboard' />

<!-- Dropdown select -->
<html app='chrome.exe' /><webctrl tag='select' name='country' />

<!-- Table cell by row and column -->
<html app='chrome.exe' /><webctrl tag='td' tableRow='{{row}}' tableCol='3' />

<!-- Checkbox -->
<html app='chrome.exe' /><webctrl tag='input' type='checkbox' name='agree' />

<!-- React data-testid -->
<html app='chrome.exe' /><webctrl css-selector='[data-testid="save-btn"]' />

<!-- Element inside an iframe -->
<html app='chrome.exe' /><webctrl tag='iframe' id='contentFrame' />
<webctrl tag='input' id='innerField' />
```

### Desktop Application Selectors

```xml
<!-- Button by name and role -->
<wnd app='app.exe' cls='MainWindow' /><ctrl name='Save' role='push button' />

<!-- Text field by automation ID -->
<wnd app='app.exe' /><ctrl automationid='txtAmount' role='editable text' />

<!-- Menu navigation -->
<wnd app='app.exe' /><ctrl name='File' role='menu item' />
<ctrl name='Save As...' role='menu item' />

<!-- Tree view item -->
<wnd app='app.exe' /><ctrl name='Folders' role='tree' />
<ctrl name='Documents' role='tree item' />

<!-- Tab selection -->
<wnd app='app.exe' /><ctrl name='Settings' role='page tab' />

<!-- Dialog box button -->
<wnd cls='#32770' title='Confirm*' /><ctrl name='Yes' role='push button' />
```

### SAP GUI Selectors

```xml
<!-- Transaction code field -->
<wnd app='saplogon.exe' cls='SAP_FRONTEND_SESSION' />
<ctrl automationid='/app/con[0]/ses[0]/wnd[0]/tbar[0]/okcd' />

<!-- Input field by technical name -->
<wnd app='saplogon.exe' cls='SAP_FRONTEND_SESSION' />
<ctrl automationid='/app/con[0]/ses[0]/wnd[0]/usr/txtRSYST-BNAME' />

<!-- Button on toolbar -->
<wnd app='saplogon.exe' cls='SAP_FRONTEND_SESSION' />
<ctrl automationid='/app/con[0]/ses[0]/wnd[0]/tbar[0]/btn[0]' />

<!-- Table cell -->
<wnd app='saplogon.exe' cls='SAP_FRONTEND_SESSION' />
<ctrl automationid='/app/con[0]/ses[0]/wnd[0]/usr/tblSAPLV60ATCTRL_SIMPLE/ctxt[1,0]' />
```

### Citrix / Remote Desktop

Citrix and RDP environments do not expose the remote application's UI tree. Use image-based or OCR targeting instead:

```xml
<!-- Citrix Viewer window (only this level is accessible) -->
<wnd app='wfica32.exe' cls='Afx:*' title='*Remote Desktop*' />
```

For elements inside the remote session, use Computer Vision activities, OCR-based activities, or native Citrix integration.

---

## Debugging Tips

1. **UiExplorer**: Use UiPath's built-in tool to inspect elements and refine selectors interactively.
2. **Highlight**: Validate that a selector matches exactly one element before using it in production.
3. **ElementExists**: Test selectors at runtime with a short timeout before attempting interaction.
4. **Log selectors**: During development, log the selector string on failure to aid debugging.
5. **Indicate on Screen**: Use `IndicateOnScreen` during development to visually verify the target.
6. **Fuzzy selector**: Enable fuzzy matching for selectors that may have minor variations between environments.
7. **Anchors**: Use anchor-based targeting when the target element itself lacks distinguishing attributes but a nearby label is stable.
