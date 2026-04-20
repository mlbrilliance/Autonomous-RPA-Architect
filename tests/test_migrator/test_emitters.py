"""Emitters: ProcessIR → generated Python project (main.py, process, tests)."""

from __future__ import annotations

import ast
from pathlib import Path

from rpa_architect.ir.schema import (
    DataContract,
    DataField,
    ProcessIR,
    Step,
    Transaction,
    UIAction,
)
from rpa_architect.migrator.emitter import emit_project


def _ir() -> ProcessIR:
    return ProcessIR(
        process_name="InvoiceProcessing",
        transactions=[
            Transaction(
                name="ProcessInvoice",
                input_contract=DataContract(
                    fields=[
                        DataField(name="InvoiceNumber", type="String"),
                        DataField(name="Amount", type="Decimal"),
                    ]
                ),
                steps=[
                    Step(
                        id="S001",
                        type="ui_flow",
                        actions=[
                            UIAction(
                                action="type_into",
                                target="Invoice Number",
                                value="{invoice_number}",
                                selector_hint="<webctrl id='invoice-num'/>",
                            ),
                            UIAction(
                                action="click",
                                target="Submit",
                                selector_hint="<webctrl id='submit'/>",
                            ),
                            UIAction(
                                action="get_text",
                                target="Confirmation Message",
                                selector_hint="<webctrl id='confirmation'/>",
                            ),
                        ],
                    )
                ],
            )
        ],
    )


class TestEmitProject:
    def test_creates_expected_files(self, tmp_path: Path) -> None:
        emit_project(_ir(), tmp_path)
        assert (tmp_path / "main.py").exists()
        assert (tmp_path / "processes" / "process_invoice.py").exists()
        assert (tmp_path / "tests" / "test_parity_process_invoice.py").exists()
        assert (tmp_path / "pyproject.toml").exists()
        assert (tmp_path / "README.md").exists()

    def test_main_py_is_valid_python(self, tmp_path: Path) -> None:
        emit_project(_ir(), tmp_path)
        ast.parse((tmp_path / "main.py").read_text())

    def test_process_py_is_valid_python(self, tmp_path: Path) -> None:
        emit_project(_ir(), tmp_path)
        ast.parse((tmp_path / "processes" / "process_invoice.py").read_text())

    def test_process_py_contains_playwright_calls(self, tmp_path: Path) -> None:
        emit_project(_ir(), tmp_path)
        content = (tmp_path / "processes" / "process_invoice.py").read_text()
        assert "async def process_invoice(" in content
        assert "page.locator('#invoice-num')" in content
        assert "page.locator('#submit').click()" in content
        assert "text_content()" in content

    def test_test_parity_is_valid_python(self, tmp_path: Path) -> None:
        emit_project(_ir(), tmp_path)
        ast.parse((tmp_path / "tests" / "test_parity_process_invoice.py").read_text())

    def test_test_parity_contains_fingerprint_assertion(self, tmp_path: Path) -> None:
        emit_project(_ir(), tmp_path)
        content = (tmp_path / "tests" / "test_parity_process_invoice.py").read_text()
        assert "def test_" in content
        # Selectors from the original XAML must survive into the parity test
        assert "invoice-num" in content or "submit" in content or "confirmation" in content

    def test_pyproject_mentions_playwright(self, tmp_path: Path) -> None:
        emit_project(_ir(), tmp_path)
        content = (tmp_path / "pyproject.toml").read_text()
        assert "playwright" in content.lower()

    def test_multi_transaction_project(self, tmp_path: Path) -> None:
        ir = ProcessIR(
            process_name="Multi",
            transactions=[
                Transaction(
                    name="TxA",
                    steps=[Step(id="S1", type="ui_flow", actions=[
                        UIAction(action="click", target="A", selector_hint="<webctrl id='a'/>"),
                    ])],
                ),
                Transaction(
                    name="TxB",
                    steps=[Step(id="S1", type="ui_flow", actions=[
                        UIAction(action="click", target="B", selector_hint="<webctrl id='b'/>"),
                    ])],
                ),
            ],
        )
        emit_project(ir, tmp_path)
        assert (tmp_path / "processes" / "process_tx_a.py").exists()
        assert (tmp_path / "processes" / "process_tx_b.py").exists()
