// Queue Processing Example
// Demonstrates: Get queue item, process transaction, set status
// Pattern: REFramework-compatible queue-based transaction processing

using System;
using System.Collections.Generic;
using UiPath.CodedWorkflows;

namespace InvoiceBot.CodedWorkflows
{
    public class QueueProcessing : CodedWorkflow
    {
        [Service] ISystemService system;

        // Configuration constants (in production, read from Config.xlsx)
        private const int MaxRetryNumber = 3;
        private const string QueueName = "InvoiceProcessingQueue";

        /// <summary>
        /// Dispatcher: reads invoice data from a source and populates the queue.
        /// Called during the Init/Dispatcher phase of REFramework.
        /// </summary>
        /// <param name="invoiceRecords">DataTable of invoices to enqueue</param>
        /// <returns>Number of items added to the queue</returns>
        [Workflow]
        public int DispatchInvoices(System.Data.DataTable invoiceRecords)
        {
            int count = 0;

            system.Log($"Dispatching {invoiceRecords.Rows.Count} invoices to queue '{QueueName}'.",
                LogLevel.Info);

            foreach (System.Data.DataRow row in invoiceRecords.Rows)
            {
                try
                {
                    var content = new Dictionary<string, object>
                    {
                        { "InvoiceNumber", row["InvoiceNumber"]?.ToString() ?? "" },
                        { "VendorName", row["VendorName"]?.ToString() ?? "" },
                        { "Amount", Convert.ToDecimal(row["Amount"]) },
                        { "InvoiceDate", row["InvoiceDate"]?.ToString() ?? "" },
                        { "Currency", row["Currency"]?.ToString() ?? "USD" },
                        { "Department", row["Department"]?.ToString() ?? "" }
                    };

                    // Validate before enqueueing
                    ValidateInvoiceData(content);

                    system.AddQueueItem(QueueName, content, new AddQueueItemOptions
                    {
                        Priority = DeterminePriority(content),
                        Reference = content["InvoiceNumber"].ToString()
                    });

                    count++;
                }
                catch (BusinessRuleException brex)
                {
                    system.Log(
                        $"Skipping invalid invoice '{row["InvoiceNumber"]}': {brex.Message}",
                        LogLevel.Warn);
                }
                catch (Exception ex)
                {
                    system.Log(
                        $"Error dispatching invoice '{row["InvoiceNumber"]}': {ex.Message}",
                        LogLevel.Error);
                    throw; // System error - stop dispatching
                }
            }

            system.Log($"Dispatched {count} of {invoiceRecords.Rows.Count} invoices.", LogLevel.Info);
            return count;
        }

        /// <summary>
        /// Performer: gets a transaction item from the queue and processes it.
        /// Called during the Process phase of REFramework.
        /// </summary>
        /// <returns>The queue item that was processed, or null if queue is empty</returns>
        [Workflow]
        public QueueItem GetTransaction()
        {
            var item = system.GetQueueItem(QueueName);

            if (item == null)
            {
                system.Log("No more items in queue. Processing complete.", LogLevel.Info);
                return null;
            }

            system.Log(
                $"Retrieved transaction: {item.Reference} (Retry #{item.RetryNo})",
                LogLevel.Info);

            return item;
        }

        /// <summary>
        /// Processes a single transaction item. This is the main business logic.
        /// </summary>
        /// <param name="transactionItem">Queue item to process</param>
        [Workflow]
        public void ProcessTransaction(QueueItem transactionItem)
        {
            string invoiceNumber = transactionItem.SpecificContent["InvoiceNumber"].ToString();
            decimal amount = Convert.ToDecimal(transactionItem.SpecificContent["Amount"]);
            string vendor = transactionItem.SpecificContent["VendorName"].ToString();

            system.Log($"Processing invoice {invoiceNumber} from {vendor} for {amount:C}",
                LogLevel.Info);

            try
            {
                // Step 1: Validate invoice data
                ValidateForProcessing(transactionItem);

                // Step 2: Check for duplicates (business rule)
                CheckForDuplicates(invoiceNumber);

                // Step 3: Apply business rules
                ApplyBusinessRules(invoiceNumber, amount, vendor);

                // Step 4: Enter invoice into ERP system
                EnterInvoiceInERP(transactionItem);

                // Step 5: Mark as successful
                system.SetTransactionStatus(transactionItem, TransactionStatus.Success);
                system.Log($"Invoice {invoiceNumber} processed successfully.", LogLevel.Info);
            }
            catch (BusinessRuleException brex)
            {
                // Business exception: do NOT retry
                system.Log($"Business exception for {invoiceNumber}: {brex.Message}",
                    LogLevel.Warn);

                system.SetTransactionStatus(transactionItem, TransactionStatus.Failed,
                    new SetTransactionStatusOptions
                    {
                        Reason = $"Business Rule: {brex.Message}"
                    });

                // Do NOT re-throw business exceptions - they should not trigger retry
            }
            catch (Exception ex)
            {
                // System exception: WILL retry up to MaxRetryNumber
                system.Log($"System exception for {invoiceNumber}: {ex.Message}",
                    LogLevel.Error);

                system.SetTransactionStatus(transactionItem, TransactionStatus.ApplicationException,
                    new SetTransactionStatusOptions
                    {
                        Reason = $"System Error: {ex.Message}"
                    });

                // Re-throw so REFramework handles retry logic
                throw;
            }
        }

        // --- Private helper methods ---

        private void ValidateInvoiceData(Dictionary<string, object> data)
        {
            if (string.IsNullOrWhiteSpace(data["InvoiceNumber"]?.ToString()))
                throw new BusinessRuleException("Invoice number is required.");

            if (Convert.ToDecimal(data["Amount"]) <= 0)
                throw new BusinessRuleException("Invoice amount must be greater than zero.");

            if (string.IsNullOrWhiteSpace(data["VendorName"]?.ToString()))
                throw new BusinessRuleException("Vendor name is required.");
        }

        private void ValidateForProcessing(QueueItem item)
        {
            // Additional validation at processing time
            if (!item.SpecificContent.ContainsKey("InvoiceNumber"))
                throw new BusinessRuleException("Queue item missing InvoiceNumber field.");

            if (!item.SpecificContent.ContainsKey("Amount"))
                throw new BusinessRuleException("Queue item missing Amount field.");
        }

        private void CheckForDuplicates(string invoiceNumber)
        {
            // In a real implementation, check ERP or database for existing invoice
            system.Log($"Checking for duplicate invoice: {invoiceNumber}", LogLevel.Trace);
            // bool isDuplicate = CheckERPForInvoice(invoiceNumber);
            // if (isDuplicate)
            //     throw new BusinessRuleException($"Duplicate invoice: {invoiceNumber}");
        }

        private void ApplyBusinessRules(string invoiceNumber, decimal amount, string vendor)
        {
            // Rule 1: Invoices over $10,000 need manager approval
            if (amount > 10000)
            {
                system.Log(
                    $"Invoice {invoiceNumber} exceeds $10,000 threshold. Routing to approval.",
                    LogLevel.Info);
                // Route to approval queue or flag for manual review
            }

            // Rule 2: Blocked vendors
            var blockedVendors = new HashSet<string> { "BLOCKED_VENDOR_1", "BLOCKED_VENDOR_2" };
            if (blockedVendors.Contains(vendor.ToUpperInvariant()))
            {
                throw new BusinessRuleException(
                    $"Vendor '{vendor}' is blocked. Invoice {invoiceNumber} cannot be processed.");
            }
        }

        private void EnterInvoiceInERP(QueueItem item)
        {
            // In a real implementation, this would interact with SAP/Oracle/etc.
            system.Log("Entering invoice into ERP system...", LogLevel.Info);

            // Simulate ERP entry
            system.Delay(1000);

            system.Log("Invoice entered into ERP successfully.", LogLevel.Info);
        }

        private QueueItemPriority DeterminePriority(Dictionary<string, object> data)
        {
            decimal amount = Convert.ToDecimal(data["Amount"]);

            if (amount > 50000)
                return QueueItemPriority.High;
            if (amount > 10000)
                return QueueItemPriority.Normal;

            return QueueItemPriority.Low;
        }
    }
}
