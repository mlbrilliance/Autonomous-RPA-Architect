# Odoo Invoice Processing PDD

## Process Overview
- **Name:** OdooInvoiceProcessing
- **Type:** transactional
- **Description:** Process vendor invoices via UiPath Document Understanding and create Vendor Bills in a self-hosted Odoo Community ERP. Each invoice PDF arrives in an Orchestrator queue, is digitised + extracted via the public DU endpoint, normalised by an in-workflow LLM agent, and posted to Odoo via JSON-RPC by a coded C# workflow.

## Systems
| Name | Type | URL | Login Required |
|------|------|-----|----------------|
| Odoo | web | http://localhost:8069 | Yes |

## Credentials
| Name | Type | Orchestrator Path | Description |
|------|------|-------------------|-------------|
| OdooCredential | credential | Shared/OdooLogin | Odoo admin user/password |
| OdooBaseURL | asset | Shared/OdooBaseURL | Public Odoo URL exposed via ngrok |
| DUApiKey | credential | Shared/DUApiKey | UiPath public DU endpoint API key |
| OdooInvoices | queue | Shared/OdooInvoices | Queue of invoice PDFs to process |

## Document Understanding
- **Document Type:** Invoice
- **Endpoint:** https://du.uipath.com/document/invoices
- **API Key Asset:** DUApiKey
- **Confidence Threshold:** 0.8
- **Fields:** VendorName, InvoiceNumber, InvoiceDate, TotalAmount, Currency, LineItems

## Steps
| ID | Type | System | Description | URL |
|----|------|--------|-------------|-----|
| S001 | login_sequence | Odoo | Log into Odoo via /web/login with stored credentials | http://localhost:8069/web/login |
| S002 | navigate | Odoo | Navigate to Accounting then Vendor Bills list | http://localhost:8069/odoo/action-account.action_move_in_invoice_type |
| S003 | extract_data | Odoo | Extract invoice fields from input PDF via Document Understanding subflow |  |
| S004 | transform_data | Odoo | Normalize the vendor name and classify the invoice category via the in-workflow LLM agent (agent-in-workflow) |  |
| S005 | ui_flow | Odoo | Click New, fill the vendor bill form with extracted fields, save the bill |  |
| S006 | api_call | Odoo | Verify the created Vendor Bill exists via Odoo JSON-RPC /web/dataset/call_kw account.move/search_read |  |
| S007 | close_application | Odoo | Log out and close the browser |  |

## Actions
### S001 Actions
| Action | Target | Value | Confidence |
|--------|--------|-------|-----------|
| type_into | Email field | {{odoo_user}} | 0.9 |
| type_into | Password field | {{odoo_pass}} | 0.9 |
| click | Login button |  | 0.85 |

### S005 Actions
| Action | Target | Value | Confidence |
|--------|--------|-------|-----------|
| click | New button |  | 0.85 |
| select_item | Vendor dropdown | {{vendor_name}} | 0.8 |
| type_into | Bill Reference field | {{invoice_number}} | 0.85 |
| type_into | Bill Date field | {{invoice_date}} | 0.85 |
| type_into | Total field | {{total_amount}} | 0.85 |
| click | Save button |  | 0.9 |

## Transactions
### ProcessInvoice
Each transaction processes one invoice PDF from the OdooInvoices queue: digitise → extract → validate → create vendor bill → verify.

## Business Rules
| ID | Condition | Outcome | Reason | Parameters |
|----|-----------|---------|--------|------------|
| BR001 | Duplicate invoice number from same vendor already exists in Odoo | business_exception | Avoid double-billing the same vendor | {} |
| BR002 | Extraction confidence below 0.8 | route | Send to human validation via Action Center | {"route_to": "ValidationQueue"} |
| BR003 | Total amount exceeds 10000 | escalate | High-value invoices require manager approval | {"route_to": "ManagerApprovalQueue"} |

## Configuration
| Name | Value |
|------|-------|
| MaxRetryNumber | 3 |
| LogLevel | Info |
| OrchestratorQueueName | OdooInvoices |
| ConfidenceThreshold | 0.8 |
| OdooEndpoint | http://localhost:8069 |
| DUEndpoint | https://du.uipath.com/document/invoices |

## Exception Handling
- **System Exception:** Network failures, Odoo unreachable, DU endpoint timeout — retry up to MaxRetryNumber times then escalate.
- **Business Exception:** Duplicate invoice, missing required fields, currency not supported — log and continue with the next queue item.
