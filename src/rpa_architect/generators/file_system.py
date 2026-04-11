"""File-system activity generators for UiPath XAML.

Generators for Copy File, Move File, Delete File, Create Directory, Path Exists,
Read/Write Text File, and Read/Write CSV.
"""

from __future__ import annotations

from rpa_architect.generators.base import quote_attr, unique_id
from rpa_architect.generators.registry import register_generator


# ---------------------------------------------------------------------------
# Generators
# ---------------------------------------------------------------------------

def gen_copy_file(
    source: str,
    destination: str,
    overwrite: bool = True,
    display_name: str = "Copy File",
) -> str:
    """Generate ``<ui:CopyFile>`` activity XAML."""
    ref = unique_id()
    ow = "True" if overwrite else "False"
    return (
        f'<ui:CopyFile Source="{quote_attr(source)}"'
        f' Destination="{quote_attr(destination)}"'
        f' Overwrite="{ow}"'
        f' DisplayName="{quote_attr(display_name)}"'
        f' sap2010:WorkflowViewState.IdRef="CopyFile_{ref}" />'
    )


def gen_move_file(
    source: str,
    destination: str,
    overwrite: bool = True,
    display_name: str = "Move File",
) -> str:
    """Generate ``<ui:MoveFile>`` activity XAML."""
    ref = unique_id()
    ow = "True" if overwrite else "False"
    return (
        f'<ui:MoveFile Source="{quote_attr(source)}"'
        f' Destination="{quote_attr(destination)}"'
        f' Overwrite="{ow}"'
        f' DisplayName="{quote_attr(display_name)}"'
        f' sap2010:WorkflowViewState.IdRef="MoveFile_{ref}" />'
    )


def gen_delete_file(
    path: str,
    display_name: str = "Delete File",
) -> str:
    """Generate ``<ui:DeleteFileOrFolder>`` activity XAML."""
    ref = unique_id()
    return (
        f'<ui:DeleteFileOrFolder Path="{quote_attr(path)}"'
        f' DisplayName="{quote_attr(display_name)}"'
        f' sap2010:WorkflowViewState.IdRef="DeleteFileOrFolder_{ref}" />'
    )


def gen_create_directory(
    path: str,
    display_name: str = "Create Directory",
) -> str:
    """Generate ``<ui:CreateDirectory>`` activity XAML."""
    ref = unique_id()
    return (
        f'<ui:CreateDirectory DirectoryPath="{quote_attr(path)}"'
        f' DisplayName="{quote_attr(display_name)}"'
        f' sap2010:WorkflowViewState.IdRef="CreateDirectory_{ref}" />'
    )


def gen_path_exists(
    path: str,
    output: str,
    display_name: str = "Path Exists",
) -> str:
    """Generate ``<ui:PathExists>`` activity XAML."""
    ref = unique_id()
    return (
        f'<ui:PathExists Path="{quote_attr(path)}"'
        f' PathType="File"'
        f' Exists="[{quote_attr(output)}]"'
        f' DisplayName="{quote_attr(display_name)}"'
        f' sap2010:WorkflowViewState.IdRef="PathExists_{ref}" />'
    )


def gen_read_text_file(
    path: str,
    output: str,
    encoding: str = "UTF-8",
    display_name: str = "Read Text File",
) -> str:
    """Generate ``<ui:ReadTextFile>`` activity XAML."""
    ref = unique_id()
    return (
        f'<ui:ReadTextFile FileName="{quote_attr(path)}"'
        f' Encoding="{quote_attr(encoding)}"'
        f' Content="[{quote_attr(output)}]"'
        f' DisplayName="{quote_attr(display_name)}"'
        f' sap2010:WorkflowViewState.IdRef="ReadTextFile_{ref}" />'
    )


def gen_write_text_file(
    path: str,
    text: str,
    encoding: str = "UTF-8",
    display_name: str = "Write Text File",
) -> str:
    """Generate ``<ui:WriteTextFile>`` activity XAML."""
    ref = unique_id()
    return (
        f'<ui:WriteTextFile FileName="{quote_attr(path)}"'
        f' Encoding="{quote_attr(encoding)}"'
        f' Text="{quote_attr(text)}"'
        f' DisplayName="{quote_attr(display_name)}"'
        f' sap2010:WorkflowViewState.IdRef="WriteTextFile_{ref}" />'
    )


def gen_read_csv(
    path: str,
    output: str,
    delimiter: str = ",",
    display_name: str = "Read CSV",
) -> str:
    """Generate ``<ui:ReadCSVFile>`` activity XAML."""
    ref = unique_id()
    return (
        f'<ui:ReadCSVFile FilePath="{quote_attr(path)}"'
        f' Delimiter="{quote_attr(delimiter)}"'
        f' DataTable="[{quote_attr(output)}]"'
        f' IncludeColumnNames="True"'
        f' DisplayName="{quote_attr(display_name)}"'
        f' sap2010:WorkflowViewState.IdRef="ReadCSVFile_{ref}" />'
    )


def gen_write_csv(
    path: str,
    datatable: str,
    delimiter: str = ",",
    display_name: str = "Write CSV",
) -> str:
    """Generate ``<ui:WriteCSVFile>`` activity XAML."""
    ref = unique_id()
    return (
        f'<ui:WriteCSVFile FilePath="{quote_attr(path)}"'
        f' Delimiter="{quote_attr(delimiter)}"'
        f' DataTable="[{quote_attr(datatable)}]"'
        f' IncludeColumnNames="True"'
        f' DisplayName="{quote_attr(display_name)}"'
        f' sap2010:WorkflowViewState.IdRef="WriteCSVFile_{ref}" />'
    )


# ---------------------------------------------------------------------------
# Registration
# ---------------------------------------------------------------------------

register_generator("copy_file", gen_copy_file, "Copy File", "File System",
                   "Copy a file to a new location")
register_generator("move_file", gen_move_file, "Move File", "File System",
                   "Move a file to a new location")
register_generator("delete_file", gen_delete_file, "Delete File", "File System",
                   "Delete a file or folder")
register_generator("create_directory", gen_create_directory, "Create Directory",
                   "File System", "Create a directory")
register_generator("path_exists", gen_path_exists, "Path Exists", "File System",
                   "Check if a path exists")
register_generator("read_text_file", gen_read_text_file, "Read Text File",
                   "File System", "Read a text file into a string variable")
register_generator("write_text_file", gen_write_text_file, "Write Text File",
                   "File System", "Write text to a file")
register_generator("read_csv", gen_read_csv, "Read CSV", "File System",
                   "Read a CSV file into a DataTable")
register_generator("write_csv", gen_write_csv, "Write CSV", "File System",
                   "Write a DataTable to a CSV file")
