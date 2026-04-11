# DMN Decision Table Patterns

DMN (Decision Model and Notation) provides a standardized way to define business rules as decision tables. UiPath Maestro uses DMN for rule-based routing, classification, validation, and escalation decisions.

---

## Decision Table Structure

A DMN decision table consists of:
- **Input columns**: conditions to evaluate (the "when")
- **Output columns**: values to return when conditions match (the "then")
- **Hit policy**: how to handle multiple matching rules
- **Rules**: rows in the table, each mapping inputs to outputs

```xml
<decision id="invoiceApproval" name="Invoice Approval Rules">
  <decisionTable id="dt_1" hitPolicy="FIRST">
    <input id="input_amount" label="Amount">
      <inputExpression typeRef="number">
        <text>amount</text>
      </inputExpression>
    </input>
    <input id="input_vendor" label="Vendor Category">
      <inputExpression typeRef="string">
        <text>vendorCategory</text>
      </inputExpression>
    </input>
    <output id="output_action" label="Action" name="action" typeRef="string"/>
    <output id="output_approver" label="Approver" name="approver" typeRef="string"/>

    <rule id="rule1">
      <inputEntry><text>&lt; 500</text></inputEntry>
      <inputEntry><text>-</text></inputEntry>
      <outputEntry><text>"auto_approve"</text></outputEntry>
      <outputEntry><text>"system"</text></outputEntry>
    </rule>
    <rule id="rule2">
      <inputEntry><text>[500..5000]</text></inputEntry>
      <inputEntry><text>"preferred"</text></inputEntry>
      <outputEntry><text>"auto_approve"</text></outputEntry>
      <outputEntry><text>"system"</text></outputEntry>
    </rule>
    <rule id="rule3">
      <inputEntry><text>[500..10000]</text></inputEntry>
      <inputEntry><text>-</text></inputEntry>
      <outputEntry><text>"manager_review"</text></outputEntry>
      <outputEntry><text>"department_manager"</text></outputEntry>
    </rule>
    <rule id="rule4">
      <inputEntry><text>&gt; 10000</text></inputEntry>
      <inputEntry><text>-</text></inputEntry>
      <outputEntry><text>"vp_review"</text></outputEntry>
      <outputEntry><text>"vp_finance"</text></outputEntry>
    </rule>
  </decisionTable>
</decision>
```

---

## Hit Policies

### Single-Hit Policies

Only one rule fires per evaluation. Use when rules should be mutually exclusive.

| Policy | Code | Behavior |
|--------|------|----------|
| Unique | `U` | Exactly one rule must match. Error if zero or multiple match. |
| Any | `A` | Multiple rules may match, but all must produce the same output. |
| First | `F` | Rules evaluated top-to-bottom. First matching rule wins. |
| Priority | `P` | All matching rules evaluated. Highest priority output returned. |

**UNIQUE (U)** -- strictest policy. Use for mappings that should never overlap:

```xml
<decisionTable hitPolicy="UNIQUE">
  <input label="Payment Method">
    <inputExpression typeRef="string"><text>paymentMethod</text></inputExpression>
  </input>
  <output label="Processor" name="processor" typeRef="string"/>

  <rule>
    <inputEntry><text>"credit_card"</text></inputEntry>
    <outputEntry><text>"PaymentProcessor_CC"</text></outputEntry>
  </rule>
  <rule>
    <inputEntry><text>"bank_transfer"</text></inputEntry>
    <outputEntry><text>"PaymentProcessor_Bank"</text></outputEntry>
  </rule>
  <rule>
    <inputEntry><text>"check"</text></inputEntry>
    <outputEntry><text>"PaymentProcessor_Check"</text></outputEntry>
  </rule>
</decisionTable>
```

**FIRST (F)** -- most common for business rules. Put specific rules first, catch-all last:

```xml
<decisionTable hitPolicy="FIRST">
  <rule>
    <!-- Most specific rule first -->
    <inputEntry><text>"VIP"</text></inputEntry>
    <inputEntry><text>&gt; 50000</text></inputEntry>
    <outputEntry><text>"executive_approval"</text></outputEntry>
  </rule>
  <rule>
    <inputEntry><text>-</text></inputEntry>
    <inputEntry><text>&gt; 50000</text></inputEntry>
    <outputEntry><text>"vp_approval"</text></outputEntry>
  </rule>
  <rule>
    <!-- Catch-all rule last -->
    <inputEntry><text>-</text></inputEntry>
    <inputEntry><text>-</text></inputEntry>
    <outputEntry><text>"auto_approve"</text></outputEntry>
  </rule>
</decisionTable>
```

### Multi-Hit Policies

Multiple rules can fire. Use when you need to collect all applicable results.

| Policy | Code | Behavior |
|--------|------|----------|
| Collect | `C` | All matching rules fire. Outputs collected as a list. |
| Collect+ | `C+` | Sum of all matching numeric outputs. |
| Collect< | `C<` | Minimum of all matching numeric outputs. |
| Collect> | `C>` | Maximum of all matching numeric outputs. |
| Collect# | `C#` | Count of matching rules. |
| Rule Order | `R` | All matching rules, returned in table order. |
| Output Order | `O` | All matching rules, sorted by output value. |

**COLLECT (C)** -- gather all applicable tags or required checks:

```xml
<decisionTable hitPolicy="COLLECT">
  <input label="Amount">
    <inputExpression typeRef="number"><text>amount</text></inputExpression>
  </input>
  <input label="Vendor Country">
    <inputExpression typeRef="string"><text>vendorCountry</text></inputExpression>
  </input>
  <output label="Required Check" name="check" typeRef="string"/>

  <rule>
    <inputEntry><text>&gt; 5000</text></inputEntry>
    <inputEntry><text>-</text></inputEntry>
    <outputEntry><text>"budget_check"</text></outputEntry>
  </rule>
  <rule>
    <inputEntry><text>-</text></inputEntry>
    <inputEntry><text>not("US", "CA")</text></inputEntry>
    <outputEntry><text>"foreign_vendor_check"</text></outputEntry>
  </rule>
  <rule>
    <inputEntry><text>&gt; 25000</text></inputEntry>
    <inputEntry><text>-</text></inputEntry>
    <outputEntry><text>"executive_approval"</text></outputEntry>
  </rule>
</decisionTable>
<!-- For amount=30000, country="UK": ["budget_check", "foreign_vendor_check", "executive_approval"] -->
```

---

## Input/Output Types

### Input Expression Types

| Type | Examples | FEEL Syntax |
|------|----------|-------------|
| `number` | 100, 5000.50 | `< 1000`, `[1000..5000]`, `> 10000` |
| `string` | "approved" | `"value"`, `not("x","y")` |
| `boolean` | true, false | `true`, `false` |
| `date` | 2024-01-15 | `< date("2024-06-01")` |

### FEEL Range Syntax

```
< 100           less than 100
<= 100          less than or equal to 100
> 100           greater than 100
>= 100          greater than or equal to 100
[100..500]      between 100 and 500, inclusive on both ends
(100..500)      between 100 and 500, exclusive on both ends
[100..500)      100 inclusive, 500 exclusive
-               any value (wildcard / don't care)
not(100)        anything except 100
not("a","b")    anything except "a" or "b"
"exact"         exact string match
```

---

## Common Business Rule Examples

### Invoice Routing Decision

```
| Amount      | Department | Vendor Status | -> Action        | -> Approver      |
|-------------|-----------|---------------|------------------|------------------|
| < 500       | -         | -             | auto_approve     | system           |
| [500..5000] | -         | "preferred"   | auto_approve     | system           |
| [500..5000] | -         | -             | manager_review   | dept_manager     |
| (5000..25K] | -         | -             | director_review  | director         |
| > 25000     | -         | -             | vp_review        | vp_finance       |
| -           | "Legal"   | -             | legal_review     | legal_dept       |
```

### Exception Classification

```
| Error Code  | Message Contains     | -> Type    | -> Retry | -> Action       |
|-------------|---------------------|------------|----------|-----------------|
| "TIMEOUT"   | -                   | system     | 3        | retry           |
| "NOT_FOUND" | -                   | business   | 0        | skip            |
| "DUPLICATE" | -                   | business   | 0        | skip            |
| "AUTH_*"    | -                   | system     | 1        | relogin_retry   |
| -           | "connection refused"| system     | 3        | retry           |
| -           | "invalid format"    | business   | 0        | flag_review     |
| -           | -                   | system     | 1        | escalate        |
```

### SLA Escalation

```
| Priority | Age (hours) | -> SLA Status | -> Escalation Level |
|----------|------------|---------------|---------------------|
| "High"   | < 4        | on_track      | none                |
| "High"   | [4..8]     | at_risk       | manager             |
| "High"   | > 8        | breached      | director            |
| "Normal" | < 24       | on_track      | none                |
| "Normal" | [24..48]   | at_risk       | manager             |
| "Normal" | > 48       | breached      | director            |
| "Low"    | < 72       | on_track      | none                |
| "Low"    | >= 72      | at_risk       | manager             |
```

### Document Type Routing

```
| Doc Type    | Language | Page Count | -> Extraction Model | -> Review Required |
|-------------|----------|-----------|--------------------|--------------------|
| "invoice"   | "en"     | <= 2      | invoice_simple_v3  | false              |
| "invoice"   | "en"     | > 2       | invoice_complex_v3 | false              |
| "invoice"   | not("en")| -         | invoice_multi_v3   | true               |
| "po"        | -        | -         | po_standard_v2     | false              |
| "contract"  | -        | -         | contract_v1        | true               |
| -           | -        | -         | generic_v1         | true               |
```
