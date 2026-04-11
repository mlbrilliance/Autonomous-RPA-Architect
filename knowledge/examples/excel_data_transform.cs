// Excel Data Transformation Example
// Demonstrates: Read Excel, transform data, write results
// Pattern: IExcelService usage with data manipulation

using System;
using System.Data;
using System.Linq;
using System.Collections.Generic;
using UiPath.CodedWorkflows;
using UiPath.Excel.Activities.API;

namespace InvoiceBot.CodedWorkflows
{
    public class ExcelDataTransform : CodedWorkflow
    {
        [Service] IExcelService excel;
        [Service] ISystemService system;

        /// <summary>
        /// Reads raw invoice data from Excel, applies transformations and
        /// business rules, then writes a cleaned summary to a new sheet.
        /// </summary>
        /// <param name="inputPath">Path to the input Excel file</param>
        /// <param name="outputPath">Path to the output Excel file</param>
        /// <returns>Number of records processed</returns>
        [Workflow]
        public int TransformInvoiceReport(string inputPath, string outputPath)
        {
            system.Log($"Starting Excel transformation: {inputPath}", LogLevel.Info);

            // Step 1: Read raw data
            DataTable rawData = ReadSourceData(inputPath);
            system.Log($"Read {rawData.Rows.Count} rows from input file.", LogLevel.Info);

            if (rawData.Rows.Count == 0)
            {
                throw new BusinessRuleException("Input file contains no data rows.");
            }

            // Step 2: Validate and clean data
            DataTable cleanedData = CleanAndValidate(rawData);
            system.Log($"After cleaning: {cleanedData.Rows.Count} valid rows.", LogLevel.Info);

            // Step 3: Apply transformations
            DataTable transformedData = ApplyTransformations(cleanedData);

            // Step 4: Generate summary
            DataTable summaryData = GenerateSummary(transformedData);

            // Step 5: Write results
            WriteOutputFiles(outputPath, transformedData, summaryData);

            system.Log($"Transformation complete. {transformedData.Rows.Count} records written.",
                LogLevel.Info);

            return transformedData.Rows.Count;
        }

        private DataTable ReadSourceData(string inputPath)
        {
            // Check which sheets are available
            var sheets = excel.GetWorksheetNames(inputPath);
            system.Log($"Available sheets: {string.Join(", ", sheets)}", LogLevel.Trace);

            // Try common sheet names
            string targetSheet = sheets.FirstOrDefault(s =>
                s.Equals("Data", StringComparison.OrdinalIgnoreCase) ||
                s.Equals("Invoices", StringComparison.OrdinalIgnoreCase) ||
                s.Equals("RawData", StringComparison.OrdinalIgnoreCase) ||
                s.Equals("Sheet1", StringComparison.OrdinalIgnoreCase)
            );

            if (targetSheet == null)
            {
                targetSheet = sheets.First();
                system.Log($"Using first available sheet: {targetSheet}", LogLevel.Warn);
            }

            return excel.ReadRange(inputPath, targetSheet, "",
                new ReadRangeOptions { HasHeaders = true });
        }

        private DataTable CleanAndValidate(DataTable rawData)
        {
            // Clone structure for clean data
            DataTable cleaned = rawData.Clone();

            int skippedCount = 0;

            foreach (DataRow row in rawData.Rows)
            {
                // Skip rows with missing invoice number
                string invoiceNum = row["InvoiceNumber"]?.ToString()?.Trim();
                if (string.IsNullOrEmpty(invoiceNum))
                {
                    skippedCount++;
                    continue;
                }

                // Skip rows with invalid amounts
                if (!decimal.TryParse(row["Amount"]?.ToString(), out decimal amount) || amount <= 0)
                {
                    system.Log($"Skipping invoice {invoiceNum}: invalid amount.", LogLevel.Warn);
                    skippedCount++;
                    continue;
                }

                // Skip rows with invalid dates
                if (!DateTime.TryParse(row["InvoiceDate"]?.ToString(), out _))
                {
                    system.Log($"Skipping invoice {invoiceNum}: invalid date.", LogLevel.Warn);
                    skippedCount++;
                    continue;
                }

                // Clean text fields - trim whitespace
                DataRow cleanRow = cleaned.NewRow();
                foreach (DataColumn col in rawData.Columns)
                {
                    var value = row[col];
                    if (value is string strValue)
                    {
                        cleanRow[col.ColumnName] = strValue.Trim();
                    }
                    else
                    {
                        cleanRow[col.ColumnName] = value;
                    }
                }

                cleaned.Rows.Add(cleanRow);
            }

            if (skippedCount > 0)
            {
                system.Log($"Skipped {skippedCount} invalid rows during cleaning.", LogLevel.Warn);
            }

            return cleaned;
        }

        private DataTable ApplyTransformations(DataTable data)
        {
            // Add calculated columns
            if (!data.Columns.Contains("TaxAmount"))
                data.Columns.Add("TaxAmount", typeof(decimal));

            if (!data.Columns.Contains("TotalWithTax"))
                data.Columns.Add("TotalWithTax", typeof(decimal));

            if (!data.Columns.Contains("Category"))
                data.Columns.Add("Category", typeof(string));

            if (!data.Columns.Contains("ProcessingDate"))
                data.Columns.Add("ProcessingDate", typeof(string));

            decimal defaultTaxRate = 0.08m; // 8% default tax rate

            foreach (DataRow row in data.Rows)
            {
                decimal amount = Convert.ToDecimal(row["Amount"]);

                // Calculate tax
                decimal taxRate = data.Columns.Contains("TaxRate")
                    ? (decimal.TryParse(row["TaxRate"]?.ToString(), out decimal tr) ? tr / 100 : defaultTaxRate)
                    : defaultTaxRate;

                decimal taxAmount = Math.Round(amount * taxRate, 2);
                row["TaxAmount"] = taxAmount;
                row["TotalWithTax"] = amount + taxAmount;

                // Categorize by amount
                row["Category"] = amount switch
                {
                    > 50000 => "Enterprise",
                    > 10000 => "Large",
                    > 1000 => "Medium",
                    _ => "Small"
                };

                // Add processing timestamp
                row["ProcessingDate"] = DateTime.Now.ToString("yyyy-MM-dd HH:mm:ss");
            }

            return data;
        }

        private DataTable GenerateSummary(DataTable detailData)
        {
            // Create summary table
            DataTable summary = new DataTable();
            summary.Columns.Add("Category", typeof(string));
            summary.Columns.Add("InvoiceCount", typeof(int));
            summary.Columns.Add("TotalAmount", typeof(decimal));
            summary.Columns.Add("TotalWithTax", typeof(decimal));
            summary.Columns.Add("AverageAmount", typeof(decimal));

            // Group by Category
            var groups = detailData.AsEnumerable()
                .GroupBy(r => r["Category"]?.ToString() ?? "Unknown")
                .OrderByDescending(g => g.Sum(r => Convert.ToDecimal(r["TotalWithTax"])));

            foreach (var group in groups)
            {
                DataRow summaryRow = summary.NewRow();
                summaryRow["Category"] = group.Key;
                summaryRow["InvoiceCount"] = group.Count();
                summaryRow["TotalAmount"] = group.Sum(r => Convert.ToDecimal(r["Amount"]));
                summaryRow["TotalWithTax"] = group.Sum(r => Convert.ToDecimal(r["TotalWithTax"]));
                summaryRow["AverageAmount"] = Math.Round(
                    group.Average(r => Convert.ToDecimal(r["Amount"])), 2);
                summary.Rows.Add(summaryRow);
            }

            // Add grand total row
            DataRow totalRow = summary.NewRow();
            totalRow["Category"] = "GRAND TOTAL";
            totalRow["InvoiceCount"] = detailData.Rows.Count;
            totalRow["TotalAmount"] = detailData.AsEnumerable()
                .Sum(r => Convert.ToDecimal(r["Amount"]));
            totalRow["TotalWithTax"] = detailData.AsEnumerable()
                .Sum(r => Convert.ToDecimal(r["TotalWithTax"]));
            totalRow["AverageAmount"] = Math.Round(
                detailData.AsEnumerable().Average(r => Convert.ToDecimal(r["Amount"])), 2);
            summary.Rows.Add(totalRow);

            return summary;
        }

        private void WriteOutputFiles(string outputPath, DataTable details, DataTable summary)
        {
            // Prepare output workbook
            var existingSheets = new List<string>();
            try
            {
                existingSheets = excel.GetWorksheetNames(outputPath);
            }
            catch
            {
                // File may not exist yet - that's fine, WriteRange will create it
            }

            // Write detailed results
            if (!existingSheets.Contains("Details"))
            {
                try { excel.CreateWorksheet(outputPath, "Details"); } catch { /* may auto-create */ }
            }
            excel.WriteRange(outputPath, "Details", details, "A1",
                new WriteRangeOptions { IncludeHeaders = true });

            // Write summary
            if (!existingSheets.Contains("Summary"))
            {
                try { excel.CreateWorksheet(outputPath, "Summary"); } catch { /* may auto-create */ }
            }
            excel.WriteRange(outputPath, "Summary", summary, "A1",
                new WriteRangeOptions { IncludeHeaders = true });

            system.Log($"Output written to: {outputPath}", LogLevel.Info);
        }
    }
}
