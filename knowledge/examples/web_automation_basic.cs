// Web Automation Basic Example
// Demonstrates: Open browser, navigate, login, extract data, close browser
// Pattern: Complete coded workflow with error handling

using System;
using System.Data;
using System.Collections.Generic;
using UiPath.CodedWorkflows;
using UiPath.UIAutomationNext.API.Contracts;
using UiPath.UIAutomationNext.API.Models;

namespace InvoiceBot.CodedWorkflows
{
    public class WebAutomationBasic : CodedWorkflow
    {
        [Service] IUiAutomationAppService uiAutomation;
        [Service] ISystemService system;

        /// <summary>
        /// Main workflow: logs into a web application, extracts invoice data,
        /// and returns it as a DataTable.
        /// </summary>
        /// <param name="appUrl">URL of the invoice management application</param>
        /// <param name="credentialName">Orchestrator credential name for login</param>
        /// <returns>DataTable containing extracted invoice records</returns>
        [Workflow]
        public DataTable ExtractInvoiceData(string appUrl, string credentialName)
        {
            DataTable result = null;

            try
            {
                system.Log("Starting web automation for invoice extraction.", LogLevel.Info);

                // Step 1: Open browser and navigate
                OpenBrowserAndNavigate(appUrl);

                // Step 2: Login with Orchestrator credentials
                LoginToApplication(credentialName);

                // Step 3: Navigate to invoices page
                NavigateToInvoices();

                // Step 4: Extract invoice data
                result = ExtractInvoiceTable();

                system.Log($"Successfully extracted {result.Rows.Count} invoice records.", LogLevel.Info);
            }
            catch (BusinessRuleException)
            {
                // Business exceptions are not retried - re-throw as-is
                throw;
            }
            catch (Exception ex)
            {
                system.Log($"System error during web automation: {ex.Message}", LogLevel.Error);

                // Take screenshot for debugging
                TakeScreenshotOnError("WebAutomation_Error");

                throw; // Re-throw for REFramework retry logic
            }
            finally
            {
                // Step 5: Always close browser
                CloseBrowser();
            }

            return result;
        }

        private void OpenBrowserAndNavigate(string url)
        {
            system.Log($"Opening browser and navigating to: {url}", LogLevel.Info);

            // Use the browser service to open Chrome
            var browserTarget = Target.From(
                "<html app='chrome.exe' />"
            );

            // Navigate to URL by typing into address bar or using Open Browser activity
            // In coded workflows, we typically use the URL parameter directly
            uiAutomation.TypeInto(
                Target.From("<wnd app='chrome.exe' cls='Chrome_WidgetWin_1' /><ctrl name='Address and search bar' role='text' />"),
                url + "[k(enter)]",
                new TypeIntoOptions { EmptyField = true }
            );

            // Wait for page to load
            system.Delay(2000);

            system.Log("Browser opened and navigated successfully.", LogLevel.Info);
        }

        private void LoginToApplication(string credentialName)
        {
            system.Log("Attempting login...", LogLevel.Info);

            // Retrieve credentials from Orchestrator
            var credential = system.GetCredential(credentialName);

            // Check if login page is displayed
            var loginForm = Target.From(
                "<html app='chrome.exe' /><webctrl tag='form' id='loginForm' />"
            );

            if (!uiAutomation.ElementExists(loginForm, new ElementExistsOptions { Timeout = 5000 }))
            {
                system.Log("Login form not found - may already be logged in.", LogLevel.Warn);
                return;
            }

            // Enter username
            uiAutomation.TypeInto(
                Target.From("<html app='chrome.exe' /><webctrl tag='input' id='username' />"),
                credential.Username,
                new TypeIntoOptions { EmptyField = true }
            );

            // Enter password
            uiAutomation.TypeInto(
                Target.From("<html app='chrome.exe' /><webctrl tag='input' id='password' />"),
                credential.Password.ToString(),
                new TypeIntoOptions { EmptyField = true }
            );

            // Click login button
            uiAutomation.Click(
                Target.From("<html app='chrome.exe' /><webctrl tag='button' id='loginBtn' />")
            );

            // Wait for dashboard to load (confirms successful login)
            var dashboard = Target.From(
                "<html app='chrome.exe' /><webctrl tag='div' id='dashboard' />"
            );

            bool loggedIn = uiAutomation.WaitForElement(dashboard,
                new WaitForElementOptions { Timeout = 15000 });

            if (!loggedIn)
            {
                // Check for error message
                var errorMsg = Target.From(
                    "<html app='chrome.exe' /><webctrl tag='div' class='login-error' />"
                );

                if (uiAutomation.ElementExists(errorMsg, new ElementExistsOptions { Timeout = 2000 }))
                {
                    string errorText = uiAutomation.GetText(errorMsg);
                    throw new BusinessRuleException($"Login failed: {errorText}");
                }

                throw new Exception("Login failed: dashboard did not appear within timeout.");
            }

            system.Log("Login successful.", LogLevel.Info);
        }

        private void NavigateToInvoices()
        {
            system.Log("Navigating to Invoices section...", LogLevel.Info);

            // Click on Invoices menu item
            uiAutomation.Click(
                Target.From("<html app='chrome.exe' /><webctrl tag='a' aaname='Invoices' />")
            );

            // Wait for invoice list to load
            var invoiceTable = Target.From(
                "<html app='chrome.exe' /><webctrl tag='table' id='invoiceGrid' />"
            );

            bool loaded = uiAutomation.WaitForElement(invoiceTable,
                new WaitForElementOptions { Timeout = 10000 });

            if (!loaded)
            {
                throw new Exception("Invoice table did not load within 10 seconds.");
            }

            system.Log("Invoice page loaded successfully.", LogLevel.Info);
        }

        private DataTable ExtractInvoiceTable()
        {
            system.Log("Extracting invoice data from table...", LogLevel.Info);

            var tableTarget = Target.From(
                "<html app='chrome.exe' /><webctrl tag='table' id='invoiceGrid' />"
            );

            // Use ExtractData for structured table extraction
            DataTable data = uiAutomation.ExtractData(tableTarget);

            if (data == null || data.Rows.Count == 0)
            {
                throw new BusinessRuleException("No invoice data found in the table.");
            }

            // Validate extracted data has expected columns
            var requiredColumns = new[] { "InvoiceNumber", "Vendor", "Amount", "Date", "Status" };
            foreach (var col in requiredColumns)
            {
                if (!data.Columns.Contains(col))
                {
                    system.Log($"Warning: Expected column '{col}' not found in extracted data.", LogLevel.Warn);
                }
            }

            return data;
        }

        private void CloseBrowser()
        {
            try
            {
                system.Log("Closing browser...", LogLevel.Info);

                // Close Chrome gracefully
                var browser = Target.From(
                    "<wnd app='chrome.exe' cls='Chrome_WidgetWin_1' />"
                );

                if (uiAutomation.ElementExists(browser, new ElementExistsOptions { Timeout = 2000 }))
                {
                    // Use keyboard shortcut to close
                    uiAutomation.Click(browser);
                    // Alt+F4 to close
                    uiAutomation.TypeInto(browser, "[k(alt)][k(f4)]");
                }

                system.Log("Browser closed.", LogLevel.Info);
            }
            catch (Exception ex)
            {
                // Don't let cleanup failures mask the original error
                system.Log($"Warning: Error closing browser: {ex.Message}", LogLevel.Warn);
            }
        }

        private void TakeScreenshotOnError(string screenshotName)
        {
            try
            {
                // In production, use TakeScreenshot activity
                system.Log($"Screenshot requested: {screenshotName}", LogLevel.Info);
            }
            catch
            {
                // Ignore screenshot errors
            }
        }
    }
}
