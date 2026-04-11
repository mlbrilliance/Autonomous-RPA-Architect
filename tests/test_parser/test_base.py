"""Tests for the parser base models and protocol."""

from __future__ import annotations

from pathlib import Path

import pytest

from rpa_architect.parser.base import PddContent, PddParser, PddSection, PddTable


class TestPddContentCreation:
    """Test PddContent model creation."""

    def test_pdd_content_creation(self, sample_pdd_content: PddContent) -> None:
        assert len(sample_pdd_content.sections) == 3
        assert len(sample_pdd_content.tables) == 1
        assert sample_pdd_content.images == []
        assert "title" in sample_pdd_content.metadata

    def test_pdd_content_empty(self) -> None:
        content = PddContent()
        assert content.sections == []
        assert content.tables == []
        assert content.images == []
        assert content.metadata == {}


class TestPddSectionCreation:
    """Test PddSection model creation."""

    def test_pdd_section_creation(self) -> None:
        section = PddSection(
            title="Process Overview",
            content="This process handles invoice processing.",
            level=1,
            page_number=1,
        )
        assert section.title == "Process Overview"
        assert section.content == "This process handles invoice processing."
        assert section.level == 1
        assert section.page_number == 1

    def test_pdd_section_defaults(self) -> None:
        section = PddSection(title="Test", content="Content")
        assert section.level == 1
        assert section.page_number == 0

    def test_pdd_section_level_bounds(self) -> None:
        """Level must be between 1 and 6."""
        section = PddSection(title="Deep", content="Nested", level=6)
        assert section.level == 6

        with pytest.raises(Exception):
            PddSection(title="Invalid", content="Bad", level=0)

        with pytest.raises(Exception):
            PddSection(title="Invalid", content="Bad", level=7)


class TestPddTableCreation:
    """Test PddTable model creation."""

    def test_pdd_table_creation(self) -> None:
        table = PddTable(
            headers=["Field", "Type", "Required"],
            rows=[
                ["InvoiceNumber", "String", "Yes"],
                ["Amount", "Decimal", "Yes"],
            ],
            caption="Invoice Fields",
            page_number=2,
        )
        assert table.headers == ["Field", "Type", "Required"]
        assert len(table.rows) == 2
        assert table.caption == "Invoice Fields"
        assert table.page_number == 2

    def test_pdd_table_defaults(self) -> None:
        table = PddTable()
        assert table.headers == []
        assert table.rows == []
        assert table.caption == ""
        assert table.page_number == 0


class TestParserProtocol:
    """Verify PddParser protocol is properly defined."""

    def test_parser_protocol(self) -> None:
        """A class implementing parse(Path) -> PddContent satisfies PddParser."""

        class MockParser:
            def parse(self, path: Path) -> PddContent:
                return PddContent(
                    sections=[PddSection(title="Test", content="Content")],
                )

        parser = MockParser()
        assert isinstance(parser, PddParser)

    def test_non_conforming_class(self) -> None:
        """A class without parse() does not satisfy PddParser."""

        class BadParser:
            def read(self, path: str) -> str:
                return ""

        parser = BadParser()
        assert not isinstance(parser, PddParser)

    def test_protocol_parse_returns_pdd_content(self) -> None:
        """Protocol implementor actually returns PddContent."""

        class SimpleParser:
            def parse(self, path: Path) -> PddContent:
                return PddContent(
                    sections=[PddSection(title="Parsed", content="From file")],
                    metadata={"source": str(path)},
                )

        parser = SimpleParser()
        result = parser.parse(Path("/tmp/test.docx"))
        assert isinstance(result, PddContent)
        assert len(result.sections) == 1
