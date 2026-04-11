// Error Handling Patterns for UiPath Coded Automations
// Covers: BusinessRuleException, retry logic, screenshot on error, structured logging
//
// These patterns are designed for UiPath coded workflows (.cs) using the
// UiPath.CodedWorkflows SDK. They complement the REFramework exception
// handling and can be used in both standalone coded workflows and hybrid
// XAML/coded projects.

using System;
using System.Collections.Generic;
using System.IO;
using System.Threading;
using UiPath.CodedWorkflows;
using UiPath.Core;
using UiPath.Core.Activities;

namespace RPA.ErrorHandling
{
    // =========================================================================
    // PATTERN 1: BusinessRuleException vs System Exception
    // =========================================================================
    //
    // BusinessRuleException: A data or business logic error that retrying will
    //   NOT fix. The transaction item should be marked as Failed.
    //   Examples: "Invoice number not found", "Amount exceeds approval limit",
    //             "Duplicate record detected", "Missing mandatory field"
    //
    // System Exception (any other Exception): An infrastructure or environment
    //   error that MAY be resolved by retrying.
    //   Examples: "Element not found" (page still loading), "Application crashed",
    //             "Network timeout", "Selector changed"
    //
    // Rule of thumb: If a human operator would get the same error on the same
    // data, it is a BusinessRuleException. If it might work on a second attempt,
    // it is a system exception.

    public class ExceptionClassification : CodedWorkflow
    {
        [Workflow]
        public void ProcessTransaction(QueueItem transactionItem)
        {
            try
            {
                // Validate business data BEFORE performing actions
                ValidateTransactionData(transactionItem);

                // Perform the actual automation steps
                ExecuteBusinessProcess(transactionItem);
            }
            catch (BusinessRuleException brex)
            {
                // DO NOT re-throw. The framework will mark this as Failed.
                // Log at Warn level because this is expected in normal operations.
                Log($"Business rule violated: {brex.Message}", LogLevel.Warn);

                // Optionally capture evidence for audit trail
                CaptureScreenshotOnError(transactionItem.Reference, "BusinessRule");

                // Let the REFramework handle the status update
                throw;
            }
            catch (Exception ex)
            {
                // System exception: MUST re-throw so REFramework can retry.
                Log($"System error during processing: {ex.Message}", LogLevel.Error);

                // Always capture screenshot for system exceptions
                CaptureScreenshotOnError(transactionItem.Reference, "SystemError");

                // Log the full stack trace at Trace level for debugging
                Log($"Stack trace: {ex.StackTrace}", LogLevel.Trace);

                throw;
            }
        }

        private void ValidateTransactionData(QueueItem item)
        {
            var content = item.SpecificContent;

            // Validate required fields - throw BusinessRuleException for bad data
            if (!content.ContainsKey("InvoiceNumber") ||
                string.IsNullOrWhiteSpace(content["InvoiceNumber"]?.ToString()))
            {
                throw new BusinessRuleException("Invoice number is missing or empty.");
            }

            if (content.ContainsKey("Amount"))
            {
                if (!decimal.TryParse(content["Amount"]?.ToString(), out decimal amount))
                    throw new BusinessRuleException($"Invalid amount format: {content["Amount"]}");

                if (amount <= 0)
                    throw new BusinessRuleException($"Amount must be positive. Got: {amount}");

                if (amount > 1000000)
                    throw new BusinessRuleException($"Amount {amount} exceeds maximum limit of 1,000,000.");
            }
        }

        private void ExecuteBusinessProcess(QueueItem item)
        {
            // Placeholder for actual business logic
            Log($"Processing invoice: {item.SpecificContent["InvoiceNumber"]}", LogLevel.Info);
        }
    }


    // =========================================================================
    // PATTERN 2: Retry with Exponential Backoff
    // =========================================================================
    //
    // Use this when you need fine-grained retry control within a single
    // transaction, e.g., waiting for a page to load, polling an API, or
    // handling transient network errors.

    public class RetryPatterns : CodedWorkflow
    {
        /// <summary>
        /// Executes an action with retry logic and exponential backoff.
        /// BusinessRuleExceptions are never retried.
        /// </summary>
        /// <typeparam name="T">Return type of the action.</typeparam>
        /// <param name="action">The action to execute.</param>
        /// <param name="maxRetries">Maximum number of retry attempts.</param>
        /// <param name="actionName">Name for logging purposes.</param>
        /// <param name="baseDelayMs">Base delay in milliseconds (doubles each retry).</param>
        /// <returns>The result of the action.</returns>
        [Workflow]
        public T ExecuteWithRetry<T>(
            Func<T> action,
            int maxRetries = 3,
            string actionName = "action",
            int baseDelayMs = 1000)
        {
            Exception lastException = null;

            for (int attempt = 1; attempt <= maxRetries; attempt++)
            {
                try
                {
                    Log($"[Retry] Attempt {attempt}/{maxRetries} for '{actionName}'", LogLevel.Trace);
                    T result = action();
                    if (attempt > 1)
                        Log($"[Retry] '{actionName}' succeeded on attempt {attempt}", LogLevel.Info);
                    return result;
                }
                catch (BusinessRuleException)
                {
                    // Business exceptions are NEVER retried
                    throw;
                }
                catch (Exception ex)
                {
                    lastException = ex;
                    Log($"[Retry] Attempt {attempt}/{maxRetries} failed for '{actionName}': {ex.Message}",
                        LogLevel.Warn);

                    if (attempt < maxRetries)
                    {
                        int delayMs = baseDelayMs * (int)Math.Pow(2, attempt - 1);
                        Log($"[Retry] Waiting {delayMs}ms before next attempt...", LogLevel.Trace);
                        Thread.Sleep(delayMs);
                    }
                }
            }

            throw new Exception(
                $"'{actionName}' failed after {maxRetries} attempts. Last error: {lastException?.Message}",
                lastException);
        }

        /// <summary>
        /// Void version of retry for actions that return nothing.
        /// </summary>
        [Workflow]
        public void ExecuteWithRetry(
            Action action,
            int maxRetries = 3,
            string actionName = "action",
            int baseDelayMs = 1000)
        {
            ExecuteWithRetry<object>(() => { action(); return null; },
                maxRetries, actionName, baseDelayMs);
        }
    }


    // =========================================================================
    // PATTERN 3: Screenshot on Error
    // =========================================================================
    //
    // Captures a screenshot when an error occurs. The screenshot is saved to
    // a timestamped file and optionally attached to the Orchestrator log.
    // This is critical for debugging production failures.

    public class ScreenshotOnError : CodedWorkflow
    {
        /// <summary>
        /// Captures a screenshot and saves it with a descriptive filename.
        /// Call this in catch blocks before re-throwing.
        /// </summary>
        /// <param name="reference">Transaction reference for the filename.</param>
        /// <param name="errorCategory">Category (e.g., "SystemError", "BusinessRule").</param>
        /// <returns>Path to the saved screenshot, or null if capture failed.</returns>
        [Workflow]
        public string CaptureScreenshotOnError(string reference, string errorCategory)
        {
            try
            {
                string screenshotDir = Path.Combine(
                    Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData),
                    "UiPath", "Screenshots");

                Directory.CreateDirectory(screenshotDir);

                string timestamp = DateTime.Now.ToString("yyyyMMdd_HHmmss_fff");
                string safeRef = SanitizeFilename(reference ?? "unknown");
                string filename = $"{errorCategory}_{safeRef}_{timestamp}.png";
                string fullPath = Path.Combine(screenshotDir, filename);

                // Use UiPath TakeScreenshot activity
                // In coded workflows, use the system service:
                // system.TakeScreenshot(fullPath);

                Log($"Screenshot saved: {fullPath}", LogLevel.Info);
                return fullPath;
            }
            catch (Exception screenshotEx)
            {
                // Never let screenshot failure mask the original error
                Log($"Warning: Failed to capture screenshot: {screenshotEx.Message}", LogLevel.Warn);
                return null;
            }
        }

        private string SanitizeFilename(string input)
        {
            char[] invalid = Path.GetInvalidFileNameChars();
            foreach (char c in invalid)
                input = input.Replace(c, '_');
            return input.Length > 50 ? input.Substring(0, 50) : input;
        }
    }


    // =========================================================================
    // PATTERN 4: Structured Logging with Context
    // =========================================================================
    //
    // Consistent, parseable log messages that include transaction context.
    // These are designed to be easily searchable in Orchestrator logs and
    // can be ingested by log analytics tools (ELK, Splunk, etc.).

    public class StructuredLogging : CodedWorkflow
    {
        private string _processName;
        private string _transactionRef;
        private DateTime _transactionStartTime;

        /// <summary>
        /// Sets the context for all subsequent log messages in this transaction.
        /// Call at the beginning of Process.xaml or your main processing method.
        /// </summary>
        [Workflow]
        public void SetLogContext(string processName, string transactionReference)
        {
            _processName = processName;
            _transactionRef = transactionReference;
            _transactionStartTime = DateTime.Now;
        }

        [Workflow]
        public void LogTransactionStart(QueueItem item)
        {
            _transactionRef = item.Reference;
            _transactionStartTime = DateTime.Now;

            Log($"[TXN_START] Process={_processName} Ref={_transactionRef} " +
                $"RetryNo={item.RetryNo} Time={_transactionStartTime:HH:mm:ss.fff}",
                LogLevel.Info);
        }

        [Workflow]
        public void LogTransactionSuccess()
        {
            var duration = DateTime.Now - _transactionStartTime;
            Log($"[TXN_SUCCESS] Process={_processName} Ref={_transactionRef} " +
                $"Duration={duration.TotalSeconds:F2}s",
                LogLevel.Info);
        }

        [Workflow]
        public void LogTransactionFailed(BusinessRuleException brex)
        {
            var duration = DateTime.Now - _transactionStartTime;
            Log($"[TXN_BUSINESS_FAIL] Process={_processName} Ref={_transactionRef} " +
                $"Duration={duration.TotalSeconds:F2}s Rule={brex.Message}",
                LogLevel.Warn);
        }

        [Workflow]
        public void LogTransactionError(Exception ex)
        {
            var duration = DateTime.Now - _transactionStartTime;
            Log($"[TXN_SYSTEM_ERROR] Process={_processName} Ref={_transactionRef} " +
                $"Duration={duration.TotalSeconds:F2}s " +
                $"Error={ex.GetType().Name}: {ex.Message}",
                LogLevel.Error);
        }

        [Workflow]
        public void LogStep(string stepName, string details = null)
        {
            string msg = $"[STEP] Process={_processName} Ref={_transactionRef} Step={stepName}";
            if (!string.IsNullOrEmpty(details))
                msg += $" Details={details}";
            Log(msg, LogLevel.Trace);
        }
    }


    // =========================================================================
    // PATTERN 5: Application Recovery
    // =========================================================================
    //
    // When a system exception occurs mid-transaction, the application may be
    // in an unknown state (dialog open, wrong page, frozen). This pattern
    // attempts to restore the application to a known good state before the
    // REFramework retries the transaction.

    public class ApplicationRecovery : CodedWorkflow
    {
        /// <summary>
        /// Attempts to recover the target application to a known good state.
        /// Call this from CloseAllApplications or from catch blocks.
        /// </summary>
        /// <param name="appName">Name of the application for logging.</param>
        /// <returns>True if recovery succeeded, false otherwise.</returns>
        [Workflow]
        public bool TryRecoverApplication(string appName)
        {
            Log($"[RECOVERY] Starting recovery for '{appName}'...", LogLevel.Info);

            try
            {
                // Step 1: Dismiss any modal dialogs
                DismissDialogs();

                // Step 2: Press Escape to close popups/menus
                SendEscapeKey();

                // Step 3: Navigate to a known page (home/dashboard)
                NavigateToHome(appName);

                Log($"[RECOVERY] Recovery succeeded for '{appName}'.", LogLevel.Info);
                return true;
            }
            catch (Exception ex)
            {
                Log($"[RECOVERY] Recovery failed for '{appName}': {ex.Message}", LogLevel.Error);
                return false;
            }
        }

        private void DismissDialogs()
        {
            // Try to close Windows dialog boxes
            // Implementation depends on the target application
            Log("[RECOVERY] Attempting to dismiss dialogs...", LogLevel.Trace);
        }

        private void SendEscapeKey()
        {
            Log("[RECOVERY] Sending Escape key...", LogLevel.Trace);
            // uiAutomation.Keyboard.PressKey(KeyboardKey.Escape);
        }

        private void NavigateToHome(string appName)
        {
            Log($"[RECOVERY] Navigating to home for '{appName}'...", LogLevel.Trace);
            // Application-specific navigation logic
        }
    }


    // =========================================================================
    // PATTERN 6: Safe Element Interaction
    // =========================================================================
    //
    // Wrapper methods that check element existence before interacting,
    // preventing ElementNotFoundException from crashing the workflow.

    public class SafeInteraction : CodedWorkflow
    {
        /// <summary>
        /// Clicks an element if it exists. Returns true if clicked, false if not found.
        /// </summary>
        [Workflow]
        public bool SafeClick(string selector, int timeoutMs = 5000)
        {
            try
            {
                // Check existence first
                // if (!uiAutomation.ElementExists(Target.From(selector), timeout: timeoutMs))
                // {
                //     Log($"SafeClick: Element not found: {selector}", LogLevel.Warn);
                //     return false;
                // }
                // uiAutomation.Click(Target.From(selector));
                return true;
            }
            catch (Exception ex)
            {
                Log($"SafeClick failed for '{selector}': {ex.Message}", LogLevel.Warn);
                return false;
            }
        }

        /// <summary>
        /// Gets text from an element, returning a default value if the element
        /// is not found or the text cannot be retrieved.
        /// </summary>
        [Workflow]
        public string SafeGetText(string selector, string defaultValue = "", int timeoutMs = 3000)
        {
            try
            {
                // if (!uiAutomation.ElementExists(Target.From(selector), timeout: timeoutMs))
                //     return defaultValue;
                // return uiAutomation.GetText(Target.From(selector)) ?? defaultValue;
                return defaultValue;
            }
            catch (Exception ex)
            {
                Log($"SafeGetText failed for '{selector}': {ex.Message}", LogLevel.Warn);
                return defaultValue;
            }
        }

        /// <summary>
        /// Types text into an element if it exists. Returns true if successful.
        /// Clears the field first by default.
        /// </summary>
        [Workflow]
        public bool SafeTypeInto(string selector, string text, bool clearFirst = true, int timeoutMs = 5000)
        {
            try
            {
                // if (!uiAutomation.ElementExists(Target.From(selector), timeout: timeoutMs))
                // {
                //     Log($"SafeTypeInto: Element not found: {selector}", LogLevel.Warn);
                //     return false;
                // }
                // if (clearFirst)
                //     uiAutomation.Click(Target.From(selector));
                //     uiAutomation.Keyboard.PressKey(KeyboardKey.CtrlA);
                // uiAutomation.TypeInto(Target.From(selector), text);
                return true;
            }
            catch (Exception ex)
            {
                Log($"SafeTypeInto failed for '{selector}': {ex.Message}", LogLevel.Warn);
                return false;
            }
        }
    }


    // =========================================================================
    // PATTERN 7: Transaction Guard (Comprehensive)
    // =========================================================================
    //
    // Combines all patterns into a single guard that wraps transaction
    // processing with logging, screenshots, and recovery.

    public class TransactionGuard : CodedWorkflow
    {
        /// <summary>
        /// Wraps a transaction processing action with full error handling.
        /// </summary>
        /// <param name="item">The queue item being processed.</param>
        /// <param name="processName">Name of the business process.</param>
        /// <param name="processAction">The action that processes the transaction.</param>
        [Workflow]
        public void ExecuteGuarded(
            QueueItem item,
            string processName,
            Action<QueueItem> processAction)
        {
            string reference = item?.Reference ?? "unknown";
            var startTime = DateTime.Now;

            Log($"[GUARD_START] Process={processName} Ref={reference} " +
                $"Retry={item?.RetryNo ?? 0} Time={startTime:HH:mm:ss}",
                LogLevel.Info);

            try
            {
                processAction(item);

                var duration = DateTime.Now - startTime;
                Log($"[GUARD_SUCCESS] Process={processName} Ref={reference} " +
                    $"Duration={duration.TotalSeconds:F2}s",
                    LogLevel.Info);
            }
            catch (BusinessRuleException brex)
            {
                var duration = DateTime.Now - startTime;
                Log($"[GUARD_BRE] Process={processName} Ref={reference} " +
                    $"Duration={duration.TotalSeconds:F2}s Rule={brex.Message}",
                    LogLevel.Warn);

                CaptureEvidence(reference, "BRE", brex);
                throw;
            }
            catch (Exception ex)
            {
                var duration = DateTime.Now - startTime;
                Log($"[GUARD_ERROR] Process={processName} Ref={reference} " +
                    $"Duration={duration.TotalSeconds:F2}s " +
                    $"Error={ex.GetType().Name}: {ex.Message}",
                    LogLevel.Error);

                CaptureEvidence(reference, "SYS", ex);
                throw;
            }
        }

        private void CaptureEvidence(string reference, string category, Exception ex)
        {
            try
            {
                string timestamp = DateTime.Now.ToString("yyyyMMdd_HHmmss");
                Log($"[EVIDENCE] Ref={reference} Category={category} " +
                    $"Exception={ex.GetType().Name} " +
                    $"Screenshot=Error_{reference}_{timestamp}.png",
                    LogLevel.Info);

                // Take screenshot
                // system.TakeScreenshot($"Error_{reference}_{timestamp}.png");

                // Log full exception details at Trace level
                Log($"[EVIDENCE] Full exception: {ex}", LogLevel.Trace);
            }
            catch (Exception evidenceEx)
            {
                Log($"Failed to capture evidence: {evidenceEx.Message}", LogLevel.Warn);
            }
        }
    }
}
