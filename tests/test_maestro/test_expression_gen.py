"""Tests for JavaScript expression generation."""

from __future__ import annotations

import pytest

from rpa_architect.maestro.expression_gen import generate_expression


class TestSimpleComparison:
    @pytest.mark.parametrize(
        "condition,expected",
        [
            ("amount > 10000", "amount > 10000"),
            ("count >= 5", "count >= 5"),
            ("value < 100", "value < 100"),
            ("total <= 0", "total <= 0"),
        ],
    )
    def test_simple_comparison(self, condition: str, expected: str) -> None:
        result = generate_expression(condition)
        assert result == expected


class TestStringComparison:
    def test_contains(self) -> None:
        result = generate_expression("status contains approved")
        assert "includes" in result

    def test_starts_with(self) -> None:
        result = generate_expression("name starts with INV")
        assert "startsWith" in result

    def test_ends_with(self) -> None:
        result = generate_expression("filename ends with .pdf")
        assert "endsWith" in result


class TestNullCheck:
    def test_is_null(self) -> None:
        result = generate_expression("value is null")
        assert "=== null" in result

    def test_is_not_null(self) -> None:
        result = generate_expression("value is not null")
        assert "!== null" in result

    def test_is_empty(self) -> None:
        result = generate_expression("value is empty")
        assert '=== ""' in result


class TestComplexCondition:
    def test_and_or(self) -> None:
        result = generate_expression("amount > 10000 and status is not null")
        assert "&&" in result
        assert "!== null" in result

    def test_variable_substitution(self) -> None:
        result = generate_expression(
            "invoice amount > 10000",
            variables={"invoice amount": "invoiceAmount"},
        )
        assert "invoiceAmount" in result

    def test_greater_than_word(self) -> None:
        result = generate_expression("amount greater than 10000")
        assert ">" in result

    def test_less_than_word(self) -> None:
        result = generate_expression("count less than 5")
        assert "<" in result
