"""Integration activity generators for UiPath XAML.

Generators for Excel, Email (IMAP/SMTP), PDF, and Database activities.
"""

from __future__ import annotations

from rpa_architect.generators.base import indent, quote_attr, unique_id
from rpa_architect.generators.registry import register_generator


# ---------------------------------------------------------------------------
# Excel generators
# ---------------------------------------------------------------------------

def gen_read_range(
    workbook_path: str,
    sheet: str,
    range_str: str,
    output: str,
    display_name: str = "Read Range",
) -> str:
    """Generate ``<ui:ReadRange>`` activity XAML (Excel scope not needed in modern)."""
    ref = unique_id()
    return (
        f'<ui:ReadRange WorkbookPath="{quote_attr(workbook_path)}"'
        f' SheetName="{quote_attr(sheet)}"'
        f' Range="{quote_attr(range_str)}"'
        f' DataTable="[{quote_attr(output)}]"'
        f' AddHeaders="True"'
        f' PreserveFormat="True"'
        f' DisplayName="{quote_attr(display_name)}"'
        f' sap2010:WorkflowViewState.IdRef="ReadRange_{ref}" />'
    )


def gen_write_range(
    workbook_path: str,
    sheet: str,
    datatable: str,
    range_str: str = "A1",
    display_name: str = "Write Range",
) -> str:
    """Generate ``<ui:WriteRange>`` activity XAML."""
    ref = unique_id()
    return (
        f'<ui:WriteRange WorkbookPath="{quote_attr(workbook_path)}"'
        f' SheetName="{quote_attr(sheet)}"'
        f' StartingCell="{quote_attr(range_str)}"'
        f' DataTable="[{quote_attr(datatable)}]"'
        f' AddHeaders="True"'
        f' DisplayName="{quote_attr(display_name)}"'
        f' sap2010:WorkflowViewState.IdRef="WriteRange_{ref}" />'
    )


def gen_append_range(
    workbook_path: str,
    sheet: str,
    datatable: str,
    display_name: str = "Append Range",
) -> str:
    """Generate ``<ui:AppendRange>`` activity XAML."""
    ref = unique_id()
    return (
        f'<ui:AppendRange WorkbookPath="{quote_attr(workbook_path)}"'
        f' SheetName="{quote_attr(sheet)}"'
        f' DataTable="[{quote_attr(datatable)}]"'
        f' DisplayName="{quote_attr(display_name)}"'
        f' sap2010:WorkflowViewState.IdRef="AppendRange_{ref}" />'
    )


def gen_write_cell(
    workbook_path: str,
    sheet: str,
    cell: str,
    value: str,
    display_name: str = "Write Cell",
) -> str:
    """Generate ``<ui:WriteCell>`` activity XAML."""
    ref = unique_id()
    return (
        f'<ui:WriteCell WorkbookPath="{quote_attr(workbook_path)}"'
        f' SheetName="{quote_attr(sheet)}"'
        f' Cell="{quote_attr(cell)}"'
        f' Value="{quote_attr(value)}"'
        f' DisplayName="{quote_attr(display_name)}"'
        f' sap2010:WorkflowViewState.IdRef="WriteCell_{ref}" />'
    )


# ---------------------------------------------------------------------------
# Email generators
# ---------------------------------------------------------------------------

def gen_get_imap_mail(
    server: str,
    port: int,
    username: str,
    password_var: str,
    output: str,
    folder: str = "INBOX",
    display_name: str = "Get IMAP Mail",
) -> str:
    """Generate ``<ui:GetIMAPMailMessages>`` activity XAML."""
    ref = unique_id()
    return (
        f'<ui:GetIMAPMailMessages Server="{quote_attr(server)}"'
        f' Port="{port}"'
        f' SecureConnection="Auto"'
        f' Email="{quote_attr(username)}"'
        f' Password="[{quote_attr(password_var)}]"'
        f' MailFolder="{quote_attr(folder)}"'
        f' Top="30"'
        f' OnlyUnreadMessages="True"'
        f' MarkAsRead="False"'
        f' Messages="[{quote_attr(output)}]"'
        f' DisplayName="{quote_attr(display_name)}"'
        f' sap2010:WorkflowViewState.IdRef="GetIMAPMailMessages_{ref}" />'
    )


def gen_send_mail(
    to: str,
    subject: str,
    body: str,
    smtp_server: str = "",
    smtp_port: int = 587,
    display_name: str = "Send SMTP Mail",
) -> str:
    """Generate ``<ui:SendSmtpMailMessage>`` activity XAML."""
    ref = unique_id()
    server_attr = ""
    if smtp_server:
        server_attr = (
            f' Server="{quote_attr(smtp_server)}"'
            f' Port="{smtp_port}"'
        )
    return (
        f'<ui:SendSmtpMailMessage To="{quote_attr(to)}"'
        f' Subject="{quote_attr(subject)}"'
        f' Body="{quote_attr(body)}"'
        f'{server_attr}'
        f' IsBodyHtml="False"'
        f' SecureConnection="Auto"'
        f' DisplayName="{quote_attr(display_name)}"'
        f' sap2010:WorkflowViewState.IdRef="SendSmtpMailMessage_{ref}" />'
    )


def gen_save_mail_attachments(
    mail_var: str,
    folder_path: str,
    display_name: str = "Save Mail Attachments",
) -> str:
    """Generate ``<ui:SaveMailAttachments>`` activity XAML."""
    ref = unique_id()
    return (
        f'<ui:SaveMailAttachments Mail="[{quote_attr(mail_var)}]"'
        f' FolderPath="{quote_attr(folder_path)}"'
        f' DisplayName="{quote_attr(display_name)}"'
        f' sap2010:WorkflowViewState.IdRef="SaveMailAttachments_{ref}" />'
    )


# ---------------------------------------------------------------------------
# PDF generators
# ---------------------------------------------------------------------------

def gen_read_pdf_text(
    file_path: str,
    output: str,
    display_name: str = "Read PDF Text",
) -> str:
    """Generate ``<ui:ReadPDFText>`` activity XAML."""
    ref = unique_id()
    return (
        f'<ui:ReadPDFText FileName="{quote_attr(file_path)}"'
        f' Text="[{quote_attr(output)}]"'
        f' Range="All"'
        f' DisplayName="{quote_attr(display_name)}"'
        f' sap2010:WorkflowViewState.IdRef="ReadPDFText_{ref}" />'
    )


def gen_read_pdf_with_ocr(
    file_path: str,
    output: str,
    ocr_engine: str = "UiPath Screen OCR",
    display_name: str = "Read PDF With OCR",
) -> str:
    """Generate ``<ui:ReadPDFWithOCR>`` activity XAML."""
    ref = unique_id()
    return (
        f'<ui:ReadPDFWithOCR FileName="{quote_attr(file_path)}"'
        f' Text="[{quote_attr(output)}]"'
        f' OCREngine="{quote_attr(ocr_engine)}"'
        f' Range="All"'
        f' DisplayName="{quote_attr(display_name)}"'
        f' sap2010:WorkflowViewState.IdRef="ReadPDFWithOCR_{ref}" />'
    )


# ---------------------------------------------------------------------------
# Database generators
# ---------------------------------------------------------------------------

def gen_database_connect(
    connection_string: str,
    provider: str,
    output: str,
    display_name: str = "Connect",
) -> str:
    """Generate ``<ui:DatabaseConnect>`` activity XAML."""
    ref = unique_id()
    return (
        f'<ui:DatabaseConnect ConnectionString="{quote_attr(connection_string)}"'
        f' ProviderName="{quote_attr(provider)}"'
        f' DatabaseConnection="[{quote_attr(output)}]"'
        f' DisplayName="{quote_attr(display_name)}"'
        f' sap2010:WorkflowViewState.IdRef="DatabaseConnect_{ref}" />'
    )


def gen_execute_query(
    connection: str,
    sql: str,
    output: str,
    display_name: str = "Execute Query",
) -> str:
    """Generate ``<ui:ExecuteQuery>`` activity XAML."""
    ref = unique_id()
    return (
        f'<ui:ExecuteQuery ExistingDbConnection="[{quote_attr(connection)}]"'
        f' Sql="{quote_attr(sql)}"'
        f' DataTable="[{quote_attr(output)}]"'
        f' TimeoutMS="30000"'
        f' DisplayName="{quote_attr(display_name)}"'
        f' sap2010:WorkflowViewState.IdRef="ExecuteQuery_{ref}" />'
    )


def gen_execute_non_query(
    connection: str,
    sql: str,
    output: str = "",
    display_name: str = "Execute Non Query",
) -> str:
    """Generate ``<ui:ExecuteNonQuery>`` activity XAML."""
    ref = unique_id()
    out_attr = f' AffectedRecords="[{quote_attr(output)}]"' if output else ""
    return (
        f'<ui:ExecuteNonQuery ExistingDbConnection="[{quote_attr(connection)}]"'
        f' Sql="{quote_attr(sql)}"'
        f'{out_attr}'
        f' TimeoutMS="30000"'
        f' DisplayName="{quote_attr(display_name)}"'
        f' sap2010:WorkflowViewState.IdRef="ExecuteNonQuery_{ref}" />'
    )


# ---------------------------------------------------------------------------
# Registration
# ---------------------------------------------------------------------------

register_generator("read_range", gen_read_range, "Read Range", "Integrations",
                   "Read data from an Excel range into a DataTable")
register_generator("write_range", gen_write_range, "Write Range", "Integrations",
                   "Write a DataTable to an Excel range")
register_generator("append_range", gen_append_range, "Append Range", "Integrations",
                   "Append a DataTable to the end of an Excel sheet")
register_generator("write_cell", gen_write_cell, "Write Cell", "Integrations",
                   "Write a value to a specific Excel cell")
register_generator("get_imap_mail", gen_get_imap_mail, "Get IMAP Mail", "Integrations",
                   "Retrieve emails from an IMAP mail server")
register_generator("send_mail", gen_send_mail, "Send SMTP Mail", "Integrations",
                   "Send an email via SMTP")
register_generator("save_mail_attachments", gen_save_mail_attachments,
                   "Save Mail Attachments", "Integrations",
                   "Save attachments from a mail message to a folder")
register_generator("read_pdf_text", gen_read_pdf_text, "Read PDF Text", "Integrations",
                   "Extract text from a PDF file")
register_generator("read_pdf_with_ocr", gen_read_pdf_with_ocr, "Read PDF With OCR",
                   "Integrations", "Extract text from a PDF using OCR")
register_generator("database_connect", gen_database_connect, "Connect", "Integrations",
                   "Connect to a database")
register_generator("execute_query", gen_execute_query, "Execute Query", "Integrations",
                   "Execute a SQL query and return results as a DataTable")
register_generator("execute_non_query", gen_execute_non_query, "Execute Non Query",
                   "Integrations", "Execute a SQL command (INSERT, UPDATE, DELETE)")
