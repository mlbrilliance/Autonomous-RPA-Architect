# IExcelService API Reference

> **Namespace:** `UiPath.Excel.Activities.API`
> **Injection:** `[Service] IExcelService excel`

Provides Excel file operations for UiPath coded workflows. Works with `.xlsx`
files via the UiPath Excel Activities package. All operations are performed
on workbooks opened via the `Use Excel File` scope or equivalent coded pattern.

---

## Methods

### ReadRange

Reads a range of cells from an Excel worksheet into a `DataTable`.

```csharp
DataTable ReadRange(
    string workbookPath,
    string sheetName,
    string range = "",
    ReadRangeOptions? options = null
);
```

**Parameters:**
| Parameter | Type | Description |
|-----------|------|-------------|
| `workbookPath` | `string` | Full path to the Excel file |
| `sheetName` | `string` | Worksheet name |
| `range` | `string` | Cell range (e.g., "A1:D100"). Empty = entire used range |
| `options` | `ReadRangeOptions?` | Optional: hasHeaders (bool), preserveFormat (bool) |

**Example:**
```csharp
[Service] IExcelService excel;

[Workflow]
public DataTable ReadInvoiceData(string filePath)
{
    return excel.ReadRange(
        filePath,
        "Invoices",
        "A1:F100",
        new ReadRangeOptions { HasHeaders = true }
    );
}
```

---

### WriteRange

Writes a `DataTable` to a specified location in an Excel worksheet.

```csharp
void WriteRange(
    string workbookPath,
    string sheetName,
    DataTable data,
    string startCell = "A1",
    WriteRangeOptions? options = null
);
```

**Parameters:**
| Parameter | Type | Description |
|-----------|------|-------------|
| `workbookPath` | `string` | Full path to the Excel file |
| `sheetName` | `string` | Target worksheet name |
| `data` | `DataTable` | Data to write |
| `startCell` | `string` | Top-left cell for the output (default "A1") |
| `options` | `WriteRangeOptions?` | Optional: includeHeaders (bool) |

**Example:**
```csharp
[Workflow]
public void WriteResults(string filePath, DataTable results)
{
    excel.WriteRange(
        filePath,
        "Results",
        results,
        "A1",
        new WriteRangeOptions { IncludeHeaders = true }
    );
}
```

---

### InsertColumn

Inserts a new column at the specified position in a worksheet.

```csharp
void InsertColumn(
    string workbookPath,
    string sheetName,
    int columnIndex,
    string columnName = ""
);
```

**Parameters:**
| Parameter | Type | Description |
|-----------|------|-------------|
| `workbookPath` | `string` | Full path to the Excel file |
| `sheetName` | `string` | Worksheet name |
| `columnIndex` | `int` | Zero-based column index for insertion |
| `columnName` | `string` | Optional header name for the new column |

**Example:**
```csharp
[Workflow]
public void AddStatusColumn(string filePath)
{
    excel.InsertColumn(filePath, "Invoices", 6, "ProcessingStatus");
}
```

---

### DeleteColumn

Deletes a column from a worksheet by index or name.

```csharp
void DeleteColumn(
    string workbookPath,
    string sheetName,
    int columnIndex
);
```

**Example:**
```csharp
[Workflow]
public void RemoveTempColumn(string filePath)
{
    excel.DeleteColumn(filePath, "Invoices", 7); // Remove column H (0-indexed = 7)
}
```

---

### FilterTable

Applies a filter to a table or range in the worksheet.

```csharp
DataTable FilterTable(
    string workbookPath,
    string sheetName,
    string columnName,
    string filterValue
);
```

**Parameters:**
| Parameter | Type | Description |
|-----------|------|-------------|
| `workbookPath` | `string` | Full path to the Excel file |
| `sheetName` | `string` | Worksheet name |
| `columnName` | `string` | Column to filter on |
| `filterValue` | `string` | Value or expression to filter by |

**Example:**
```csharp
[Workflow]
public DataTable GetPendingInvoices(string filePath)
{
    return excel.FilterTable(filePath, "Invoices", "Status", "Pending");
}
```

---

### GetWorksheetNames

Returns a list of all worksheet names in the workbook.

```csharp
List<string> GetWorksheetNames(string workbookPath);
```

**Example:**
```csharp
[Workflow]
public void ListAllSheets(string filePath)
{
    var sheets = excel.GetWorksheetNames(filePath);
    foreach (var sheet in sheets)
    {
        system.Log($"Found worksheet: {sheet}");
    }
}
```

---

### CreateWorksheet

Creates a new worksheet in an existing workbook.

```csharp
void CreateWorksheet(
    string workbookPath,
    string sheetName
);
```

**Example:**
```csharp
[Workflow]
public void PrepareOutputWorkbook(string filePath)
{
    var existingSheets = excel.GetWorksheetNames(filePath);

    if (!existingSheets.Contains("Results"))
    {
        excel.CreateWorksheet(filePath, "Results");
    }

    if (!existingSheets.Contains("ErrorLog"))
    {
        excel.CreateWorksheet(filePath, "ErrorLog");
    }
}
```

---

## Common Patterns

### Read, Transform, Write

```csharp
[Service] IExcelService excel;
[Service] ISystemService system;

[Workflow]
public void TransformInvoiceData(string inputPath, string outputPath)
{
    // Read source data
    var sourceData = excel.ReadRange(inputPath, "RawData", "",
        new ReadRangeOptions { HasHeaders = true });

    system.Log($"Read {sourceData.Rows.Count} rows from input.");

    // Transform: add calculated columns
    sourceData.Columns.Add("TotalWithTax", typeof(decimal));

    foreach (DataRow row in sourceData.Rows)
    {
        decimal amount = Convert.ToDecimal(row["Amount"]);
        decimal taxRate = Convert.ToDecimal(row["TaxRate"]);
        row["TotalWithTax"] = amount * (1 + taxRate / 100);
    }

    // Write results
    excel.WriteRange(outputPath, "ProcessedData", sourceData, "A1",
        new WriteRangeOptions { IncludeHeaders = true });

    system.Log($"Wrote {sourceData.Rows.Count} rows to output.");
}
```

### Multi-Sheet Processing

```csharp
[Workflow]
public void ProcessAllSheets(string filePath)
{
    var sheets = excel.GetWorksheetNames(filePath);
    var allData = new DataTable();
    bool headersSet = false;

    foreach (var sheet in sheets)
    {
        if (sheet.StartsWith("_") || sheet == "Summary")
            continue;

        var sheetData = excel.ReadRange(filePath, sheet, "",
            new ReadRangeOptions { HasHeaders = true });

        if (!headersSet && sheetData.Columns.Count > 0)
        {
            allData = sheetData.Clone();
            headersSet = true;
        }

        foreach (DataRow row in sheetData.Rows)
        {
            allData.ImportRow(row);
        }

        system.Log($"Sheet '{sheet}': {sheetData.Rows.Count} rows");
    }

    // Write consolidated data
    excel.CreateWorksheet(filePath, "Summary");
    excel.WriteRange(filePath, "Summary", allData, "A1",
        new WriteRangeOptions { IncludeHeaders = true });
}
```
