"""Parsers for CSV and Excel financial tables."""

from pathlib import Path
from typing import List, Union

import pandas as pd

from ..models import FinancialChunk, FinancialRecord


PathLike = Union[str, Path]


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


def _numeric_value(value: object) -> float | None:
    cleaned = str(value).strip().replace(",", "").replace("$", "").replace("%", "")
    if not cleaned:
        return None
    try:
        return float(cleaned)
    except ValueError:
        return None


def _financial_records(dataframe: pd.DataFrame, source_file: str, sheet_name: str) -> list[FinancialRecord]:
    if dataframe.empty or len(dataframe.columns) < 2:
        return []
    metric_column = dataframe.columns[0]
    records: list[FinancialRecord] = []
    for _, row in dataframe.iterrows():
        metric = str(row.get(metric_column, "")).strip()
        if not metric or metric.lower() == "nan":
            continue
        for period in dataframe.columns[1:]:
            raw_value = str(row.get(period, "")).strip()
            if raw_value.lower() == "nan" or not raw_value:
                continue
            records.append(
                FinancialRecord(
                    metric=metric,
                    period=str(period),
                    value=_numeric_value(raw_value),
                    raw_value=raw_value,
                    source_file=source_file,
                    sheet_name=sheet_name,
                )
            )
    return records


def parse_table_file(file_path: PathLike) -> List[FinancialChunk]:
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
                    "row_count": int(len(dataframe)),
                    "column_count": int(len(dataframe.columns)),
                },
                structured_records=_financial_records(dataframe, path.name, str(sheet_name)),
            )
        )
    return chunks


class TableParser:
    """Object-oriented facade for CSV and Excel parsing."""

    def parse(self, file_path: PathLike) -> List[FinancialChunk]:
        return parse_table_file(file_path)