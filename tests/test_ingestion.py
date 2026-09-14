from pathlib import Path

import pandas as pd
import pytest

from src.ingestion.models import UnsupportedFileTypeError
from src.ingestion.parsers import pdf as pdf_parser
from src.ingestion.pipeline import FinancialIngestionPipeline


@pytest.fixture
def pipeline() -> FinancialIngestionPipeline:
    return FinancialIngestionPipeline()


def test_csv_parsing_preserves_table_and_metadata(pipeline: FinancialIngestionPipeline):
    result = pipeline.ingest(Path("data/samples/sample_pnl.csv"))

    assert result.total_chunks == 1
    chunk = result.chunks[0]
    assert chunk.chunk_type == "table"
    assert "| Revenue |" in chunk.content
    assert "$1200000" in chunk.content
    assert "$1450000" in chunk.content
    assert chunk.metadata["sheet_name"] == "sample_pnl"
    assert chunk.metadata["row_count"] == 3


def test_excel_parsing_preserves_each_sheet_and_metadata(
    pipeline: FinancialIngestionPipeline, tmp_path: Path
):
    workbook = tmp_path / "financials.xlsx"
    with pd.ExcelWriter(workbook, engine="openpyxl") as writer:
        pd.DataFrame({"Line Item": ["Revenue"], "Q1": [1200000]}).to_excel(
            writer, sheet_name="P&L", index=False
        )
        pd.DataFrame({"Account": ["Cash"], "Balance": [500000]}).to_excel(
            writer, sheet_name="Balance Sheet", index=False
        )

    result = pipeline.ingest(workbook)

    assert result.total_chunks == 2
    sheets = {chunk.metadata["sheet_name"]: chunk for chunk in result.chunks}
    assert "| Revenue | 1200000 |" in sheets["P&L"].content
    assert "| Cash | 500000 |" in sheets["Balance Sheet"].content
    assert all(chunk.chunk_type == "table" for chunk in result.chunks)


def test_invalid_extension_is_rejected(pipeline: FinancialIngestionPipeline, tmp_path: Path):
    invalid_file = tmp_path / "financials.txt"
    invalid_file.write_text("not a supported document", encoding="utf-8")

    with pytest.raises(UnsupportedFileTypeError):
        pipeline.ingest(invalid_file)


def test_pdf_table_extraction_is_markdown_and_page_aware(
    pipeline: FinancialIngestionPipeline, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    pdf_path = tmp_path / "report.pdf"

    class FakePage:
        def extract_tables(self):
            return [[["Line Item", "Q1"], ["Revenue", "$1200000"]]]

        def extract_text(self):
            return ""

    class FakePDF:
        pages = [FakePage()]

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc_value, traceback):
            return False

    monkeypatch.setattr(pdf_parser.pdfplumber, "open", lambda path: FakePDF())

    result = pipeline.ingest(pdf_path)

    assert result.total_chunks == 1
    chunk = result.chunks[0]
    assert chunk.chunk_type == "table"
    assert "| Revenue | $1200000 |" in chunk.content
    assert chunk.metadata["page_number"] == 1