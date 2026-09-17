"""Parsers for CSV and Excel financial tables."""

from pathlib import Path

import pandas as pd

from ..models import FinancialChunk

PathLike = str | Path


def dataframe_to_markdown(dataframe: pd.DataFrame) -> str:
    """Render a dataframe as a stable Markdown table without an index column."""
    normalized = dataframe.fillna("").astype(str)
    headers = [str(column) for column in normalized.columns]
    lines = [
        "| " + " | ".join(_escape_cell(header) for header in headers) + " |",
        "| " + " | ".join("---" for _ in headers) + " |",
    ]
    lines.extend(
        "| " + " | ".join(_escape_cell(value) for value in row) + " |"
        for row in normalized.itertuples(index=False, name=None)
    )
    return "\n".join(lines)


def _escape_cell(value: object) -> str:
    return str(value).replace("|", "\\|").replace("\n", " ")


def parse_table_file(file_path: PathLike) -> list[FinancialChunk]:
    """Parse a CSV or workbook into one Markdown table chunk per sheet."""
    path = Path(file_path)
    suffix = path.suffix.lower()
    if suffix == ".csv":
        sheets = {path.stem: pd.read_csv(path)}
    elif suffix == ".xlsx":
        sheets = pd.read_excel(path, sheet_name=None, engine="openpyxl")
    else:
        raise ValueError(f"Unsupported table extension: {path.suffix}")

    chunks = []
    for sheet_name, dataframe in sheets.items():
        chunks.append(
            FinancialChunk(
                chunk_id=f"{path.name}:{sheet_name}",
                content=dataframe_to_markdown(dataframe),
                chunk_type="table",
                source_file=str(path),
                metadata={
                    "sheet_name": str(sheet_name),
                    "row_count": len(dataframe),
                    "column_count": len(dataframe.columns),
                },
            )
        )
    return chunks


class TableParser:
    """Object-oriented facade for CSV and Excel parsing."""

    def parse(self, file_path: PathLike) -> list[FinancialChunk]:
        return parse_table_file(file_path)