"""Data operation activity generators for UiPath XAML.

Generators for Assign, Build Data Table, Add Data Row, Filter, Sort, Join,
and other data manipulation activities.
"""

from __future__ import annotations

from rpa_architect.generators.base import indent, quote_attr, unique_id
from rpa_architect.generators.registry import register_generator


# ---------------------------------------------------------------------------
# Generators
# ---------------------------------------------------------------------------

def gen_assign(
    variable: str,
    value: str,
    display_name: str = "Assign",
) -> str:
    """Generate ``<Assign>`` activity XAML."""
    ref = unique_id()
    return (
        f'<Assign DisplayName="{quote_attr(display_name)}"'
        f' sap2010:WorkflowViewState.IdRef="Assign_{ref}">\n'
        f'  <Assign.To>\n'
        f'    <OutArgument x:TypeArguments="x:Object">[{quote_attr(variable)}]</OutArgument>\n'
        f'  </Assign.To>\n'
        f'  <Assign.Value>\n'
        f'    <InArgument x:TypeArguments="x:Object">[{quote_attr(value)}]</InArgument>\n'
        f'  </Assign.Value>\n'
        f'</Assign>'
    )


def gen_multiple_assign(
    assignments: list[tuple[str, str]],
    display_name: str = "Multiple Assign",
) -> str:
    """Generate ``<ui:MultipleAssign>`` activity XAML.

    Parameters
    ----------
    assignments:
        List of ``(variable, value)`` tuples.
    """
    ref = unique_id()
    assign_parts: list[str] = []
    for var, val in assignments:
        assign_parts.append(
            f'    <ui:AssignExpression To="{quote_attr(var)}"'
            f' Value="[{quote_attr(val)}]" />'
        )
    inner = "\n".join(assign_parts)
    return (
        f'<ui:MultipleAssign DisplayName="{quote_attr(display_name)}"'
        f' sap2010:WorkflowViewState.IdRef="MultipleAssign_{ref}">\n'
        f'  <ui:MultipleAssign.Assignments>\n'
        f'{inner}\n'
        f'  </ui:MultipleAssign.Assignments>\n'
        f'</ui:MultipleAssign>'
    )


def gen_build_data_table(
    columns: list[dict],
    display_name: str = "Build Data Table",
) -> str:
    """Generate ``<ui:BuildDataTable>`` activity XAML.

    Parameters
    ----------
    columns:
        List of dicts with ``name``, ``type`` (default ``System.String``),
        and optional ``default`` keys.
    """
    ref = unique_id()
    col_parts: list[str] = []
    for col in columns:
        col_name = col.get("name", "Column")
        col_type = col.get("type", "System.String")
        col_default = col.get("default", "")
        col_parts.append(
            f'        <ui:DataTableColumn ColumnName="{quote_attr(col_name)}"'
            f' DataType="{quote_attr(col_type)}"'
            f' DefaultValue="{quote_attr(col_default)}" />'
        )
    cols_xml = "\n".join(col_parts)
    return (
        f'<ui:BuildDataTable DisplayName="{quote_attr(display_name)}"'
        f' DataTable="[OutputDataTable]"'
        f' sap2010:WorkflowViewState.IdRef="BuildDataTable_{ref}">\n'
        f'  <ui:BuildDataTable.Columns>\n'
        f'    <scg:List x:TypeArguments="ui:DataTableColumn">\n'
        f'{cols_xml}\n'
        f'    </scg:List>\n'
        f'  </ui:BuildDataTable.Columns>\n'
        f'</ui:BuildDataTable>'
    )


def gen_add_data_row(
    datatable: str,
    values: list[str] | str,
    display_name: str = "Add Data Row",
) -> str:
    """Generate ``<ui:AddDataRow>`` activity XAML.

    Parameters
    ----------
    datatable:
        Variable name of the target DataTable.
    values:
        Either an array expression string (e.g. ``"{{val1, val2}}"``) or a
        list of value expressions.
    """
    ref = unique_id()
    if isinstance(values, list):
        array_expr = "{" + ", ".join(values) + "}"
    else:
        array_expr = values
    return (
        f'<ui:AddDataRow DataTable="[{quote_attr(datatable)}]"'
        f' DisplayName="{quote_attr(display_name)}"'
        f' sap2010:WorkflowViewState.IdRef="AddDataRow_{ref}">\n'
        f'  <ui:AddDataRow.ArrayRow>\n'
        f'    <InArgument x:TypeArguments="scg:IEnumerable(x:Object)">'
        f'[New Object() {quote_attr(array_expr)}]</InArgument>\n'
        f'  </ui:AddDataRow.ArrayRow>\n'
        f'</ui:AddDataRow>'
    )


def gen_add_data_column(
    datatable: str,
    column_name: str,
    column_type: str = "System.String",
    display_name: str = "Add Data Column",
) -> str:
    """Generate ``<ui:AddDataColumn>`` activity XAML."""
    ref = unique_id()
    return (
        f'<ui:AddDataColumn ColumnName="{quote_attr(column_name)}"'
        f' DataTable="[{quote_attr(datatable)}]"'
        f' TypeArgument="{quote_attr(column_type)}"'
        f' DisplayName="{quote_attr(display_name)}"'
        f' sap2010:WorkflowViewState.IdRef="AddDataColumn_{ref}" />'
    )


def gen_filter_data_table(
    datatable: str,
    output: str,
    filters: list[dict],
    display_name: str = "Filter Data Table",
) -> str:
    """Generate ``<ui:FilterDataTable>`` activity XAML.

    Parameters
    ----------
    filters:
        List of dicts with ``column`` (name or index), ``operation``
        (e.g. ``"Equals"``, ``"Contains"``), and ``value``.
    """
    ref = unique_id()
    filter_parts: list[str] = []
    for f in filters:
        col = f.get("column", "")
        op = f.get("operation", "Equals")
        val = f.get("value", "")
        filter_parts.append(
            f'      <ui:FilterOperand Column="{quote_attr(col)}"'
            f' Operand="{quote_attr(op)}"'
            f' Value="{quote_attr(val)}" />'
        )
    filters_xml = "\n".join(filter_parts)
    return (
        f'<ui:FilterDataTable DataTable="[{quote_attr(datatable)}]"'
        f' OutputDataTable="[{quote_attr(output)}]"'
        f' DisplayName="{quote_attr(display_name)}"'
        f' sap2010:WorkflowViewState.IdRef="FilterDataTable_{ref}">\n'
        f'  <ui:FilterDataTable.Filters>\n'
        f'    <scg:List x:TypeArguments="ui:FilterOperand">\n'
        f'{filters_xml}\n'
        f'    </scg:List>\n'
        f'  </ui:FilterDataTable.Filters>\n'
        f'</ui:FilterDataTable>'
    )


def gen_sort_data_table(
    datatable: str,
    column_name: str,
    direction: str = "Ascending",
    output: str = "",
    display_name: str = "Sort Data Table",
) -> str:
    """Generate ``<ui:SortDataTable>`` activity XAML."""
    ref = unique_id()
    out_attr = f' OutputDataTable="[{quote_attr(output)}]"' if output else ""
    return (
        f'<ui:SortDataTable DataTable="[{quote_attr(datatable)}]"'
        f' ColumnName="{quote_attr(column_name)}"'
        f' OrderByDirection="{quote_attr(direction)}"'
        f'{out_attr}'
        f' DisplayName="{quote_attr(display_name)}"'
        f' sap2010:WorkflowViewState.IdRef="SortDataTable_{ref}" />'
    )


def gen_join_data_tables(
    dt1: str,
    dt2: str,
    output: str,
    join_type: str = "Inner",
    dt1_column: str = "",
    dt2_column: str = "",
    display_name: str = "Join Data Tables",
) -> str:
    """Generate ``<ui:JoinDataTables>`` activity XAML."""
    ref = unique_id()
    col_attrs = ""
    if dt1_column:
        col_attrs += f' DataTable1Column="{quote_attr(dt1_column)}"'
    if dt2_column:
        col_attrs += f' DataTable2Column="{quote_attr(dt2_column)}"'
    return (
        f'<ui:JoinDataTables DataTable1="[{quote_attr(dt1)}]"'
        f' DataTable2="[{quote_attr(dt2)}]"'
        f' OutputDataTable="[{quote_attr(output)}]"'
        f' JoinType="{quote_attr(join_type)}"'
        f'{col_attrs}'
        f' DisplayName="{quote_attr(display_name)}"'
        f' sap2010:WorkflowViewState.IdRef="JoinDataTables_{ref}" />'
    )


def gen_lookup_data_table(
    datatable: str,
    lookup_value: str,
    column_name: str,
    target_column: str,
    output: str,
    display_name: str = "Lookup Data Table",
) -> str:
    """Generate ``<ui:LookupDataTable>`` activity XAML."""
    ref = unique_id()
    return (
        f'<ui:LookupDataTable DataTable="[{quote_attr(datatable)}]"'
        f' LookupValue="{quote_attr(lookup_value)}"'
        f' ColumnName="{quote_attr(column_name)}"'
        f' TargetColumnName="{quote_attr(target_column)}"'
        f' CellValue="[{quote_attr(output)}]"'
        f' DisplayName="{quote_attr(display_name)}"'
        f' sap2010:WorkflowViewState.IdRef="LookupDataTable_{ref}" />'
    )


def gen_merge_data_table(
    source: str,
    destination: str,
    display_name: str = "Merge Data Table",
) -> str:
    """Generate ``<ui:MergeDataTable>`` activity XAML."""
    ref = unique_id()
    return (
        f'<ui:MergeDataTable Source="[{quote_attr(source)}]"'
        f' Destination="[{quote_attr(destination)}]"'
        f' MissingSchemaAction="Add"'
        f' DisplayName="{quote_attr(display_name)}"'
        f' sap2010:WorkflowViewState.IdRef="MergeDataTable_{ref}" />'
    )


def gen_output_data_table(
    datatable: str,
    output_variable: str,
    display_name: str = "Output Data Table",
) -> str:
    """Generate ``<ui:OutputDataTable>`` activity XAML."""
    ref = unique_id()
    return (
        f'<ui:OutputDataTable DataTable="[{quote_attr(datatable)}]"'
        f' Text="[{quote_attr(output_variable)}]"'
        f' DisplayName="{quote_attr(display_name)}"'
        f' sap2010:WorkflowViewState.IdRef="OutputDataTable_{ref}" />'
    )


def gen_remove_data_column(
    datatable: str,
    column_name: str,
    display_name: str = "Remove Data Column",
) -> str:
    """Generate ``<ui:RemoveDataColumn>`` activity XAML."""
    ref = unique_id()
    return (
        f'<ui:RemoveDataColumn DataTable="[{quote_attr(datatable)}]"'
        f' ColumnName="{quote_attr(column_name)}"'
        f' DisplayName="{quote_attr(display_name)}"'
        f' sap2010:WorkflowViewState.IdRef="RemoveDataColumn_{ref}" />'
    )


def gen_remove_duplicate_rows(
    datatable: str,
    output: str,
    column_name: str = "",
    display_name: str = "Remove Duplicate Rows",
) -> str:
    """Generate ``<ui:RemoveDuplicateRows>`` activity XAML."""
    ref = unique_id()
    col_attr = f' ColumnName="{quote_attr(column_name)}"' if column_name else ""
    return (
        f'<ui:RemoveDuplicateRows DataTable="[{quote_attr(datatable)}]"'
        f' OutputDataTable="[{quote_attr(output)}]"'
        f'{col_attr}'
        f' DisplayName="{quote_attr(display_name)}"'
        f' sap2010:WorkflowViewState.IdRef="RemoveDuplicateRows_{ref}" />'
    )


def gen_generate_data_table(
    csv_text: str,
    output: str,
    display_name: str = "Generate Data Table",
) -> str:
    """Generate ``<ui:GenerateDataTable>`` activity XAML from CSV text."""
    ref = unique_id()
    return (
        f'<ui:GenerateDataTable InputText="{quote_attr(csv_text)}"'
        f' DataTable="[{quote_attr(output)}]"'
        f' ColumnSeparator=","'
        f' NewLineSeparator="\\n"'
        f' HasHeaders="True"'
        f' DisplayName="{quote_attr(display_name)}"'
        f' sap2010:WorkflowViewState.IdRef="GenerateDataTable_{ref}" />'
    )


def gen_variables_block(
    variables: list[dict],
) -> str:
    """Generate a ``<Sequence.Variables>`` block for variable declarations.

    Parameters
    ----------
    variables:
        List of dicts with ``name``, ``type`` (XAML type like ``x:String``),
        optional ``default``, and optional ``scope``.
    """
    var_parts: list[str] = []
    for v in variables:
        name = v.get("name", "var")
        vtype = v.get("type", "x:String")
        default = v.get("default", "")

        default_attr = ""
        if default:
            default_attr = f' Default="[{quote_attr(default)}]"'

        var_parts.append(
            f'    <Variable x:TypeArguments="{quote_attr(vtype)}"'
            f'{default_attr}'
            f' Name="{quote_attr(name)}" />'
        )

    inner = "\n".join(var_parts)
    return (
        f'<Sequence.Variables>\n'
        f'{inner}\n'
        f'</Sequence.Variables>'
    )


# ---------------------------------------------------------------------------
# Registration
# ---------------------------------------------------------------------------

register_generator("assign", gen_assign, "Assign", "Data Operations",
                   "Assign a value to a variable")
register_generator("multiple_assign", gen_multiple_assign, "Multiple Assign",
                   "Data Operations", "Assign multiple values at once")
register_generator("build_data_table", gen_build_data_table, "Build Data Table",
                   "Data Operations", "Build a DataTable with column definitions")
register_generator("add_data_row", gen_add_data_row, "Add Data Row",
                   "Data Operations", "Add a row to a DataTable")
register_generator("add_data_column", gen_add_data_column, "Add Data Column",
                   "Data Operations", "Add a column to a DataTable")
register_generator("filter_data_table", gen_filter_data_table, "Filter Data Table",
                   "Data Operations", "Filter DataTable rows by conditions")
register_generator("sort_data_table", gen_sort_data_table, "Sort Data Table",
                   "Data Operations", "Sort a DataTable by column")
register_generator("join_data_tables", gen_join_data_tables, "Join Data Tables",
                   "Data Operations", "Join two DataTables")
register_generator("lookup_data_table", gen_lookup_data_table, "Lookup Data Table",
                   "Data Operations", "Look up a value in a DataTable")
register_generator("merge_data_table", gen_merge_data_table, "Merge Data Table",
                   "Data Operations", "Merge a source DataTable into a destination")
register_generator("output_data_table", gen_output_data_table, "Output Data Table",
                   "Data Operations", "Convert a DataTable to a string")
register_generator("remove_data_column", gen_remove_data_column, "Remove Data Column",
                   "Data Operations", "Remove a column from a DataTable")
register_generator("remove_duplicate_rows", gen_remove_duplicate_rows,
                   "Remove Duplicate Rows", "Data Operations",
                   "Remove duplicate rows from a DataTable")
register_generator("generate_data_table", gen_generate_data_table,
                   "Generate Data Table", "Data Operations",
                   "Generate a DataTable from CSV text")
register_generator("variables_block", gen_variables_block, "Variables Block",
                   "Data Operations", "Declare variables for a Sequence scope")
