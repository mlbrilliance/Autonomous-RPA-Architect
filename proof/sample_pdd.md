# Process Definition Document

## Process Overview

- **Name:** WebInteractionAutomation
- **Type:** transactional
- **Description:** Automated interaction with the-internet.herokuapp.com test pages — clicks buttons, toggles checkboxes, selects dropdowns, types into inputs, and reads text results. Designed as a REFramework queue performer that processes each page interaction as a transaction item.

## Systems

| Name | Type | URL | Login Required |
|------|------|-----|----------------|
| TheInternet | web | https://the-internet.herokuapp.com | No |

## Credentials

*(No credentials required for this public test site.)*

## Transactions

### InteractWithTestPages

**Input Contract:**

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| PageName | String | Yes | Name of the test page to interact with |
| ActionType | String | Yes | Type of UI action to perform |

**Output Contract:**

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| Status | String | Yes | Result of the interaction (Success/Failed) |
| ExtractedText | String | No | Any text extracted during the interaction |

## Steps

| ID | Type | System | Description | URL |
|----|------|--------|-------------|-----|
| S001 | navigate | TheInternet | Click the Add Element button on the add/remove elements page | https://the-internet.herokuapp.com/add_remove_elements/ |
| S002 | ui_flow | TheInternet | Toggle checkboxes on the checkboxes page | https://the-internet.herokuapp.com/checkboxes |
| S003 | ui_flow | TheInternet | Select an option from the dropdown page | https://the-internet.herokuapp.com/dropdown |
| S004 | ui_flow | TheInternet | Type a number into the input field | https://the-internet.herokuapp.com/inputs |
| S005 | ui_flow | TheInternet | Type text and read the result on the key presses page | https://the-internet.herokuapp.com/key_presses |

## Actions

### S001 Actions

| Action | Target | Value | Confidence |
|--------|--------|-------|------------|
| click | Add Element | | 0.5 |

### S002 Actions

| Action | Target | Value | Confidence |
|--------|--------|-------|------------|
| check | checkbox 1 | | 0.5 |
| check | checkbox 2 | | 0.5 |

### S003 Actions

| Action | Target | Value | Confidence |
|--------|--------|-------|------------|
| select_item | Dropdown | Option 1 | 0.5 |

### S004 Actions

| Action | Target | Value | Confidence |
|--------|--------|-------|------------|
| type_into | Number Input | 42 | 0.5 |

### S005 Actions

| Action | Target | Value | Confidence |
|--------|--------|-------|------------|
| type_into | Input Field | Hello World | 0.5 |
| get_text | Result | | 0.5 |

## Business Rules

*(No business rules for this demonstration process.)*

## Configuration

| Name | Value |
|------|-------|
| MaxRetryNumber | 3 |
| LogLevel | Info |
| OrchestratorQueueName | WebInteraction_Queue |
| MaxConsecutiveSystemExceptions | 3 |

## Exception Handling

- **System Exception:** Raised on page load timeout or element not found after retries.
- **Business Exception:** Raised if an expected UI element is missing from the page structure.
