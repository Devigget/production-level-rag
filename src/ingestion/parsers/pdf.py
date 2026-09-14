"""Table-aware PDF parser."""

from pathlib import Path
from typing import List, Union

import pdfplumber

from ..models import FinancialChunk
from .table import dataframe_to_markdown


PathLike = Union[str, Path]


def parse_pdf(file_path: PathLike) -> List[FinancialChunk]:
    """Extract PDF tables as Markdown and retain page metadata.

    Pages without detected tables are emitted as text chunks so no extracted
    narrative content is silently discarded.
    """
    path = Path(file_path)
    chunks: List[FinancialChunk] = []
    with pdfplumber.open(path) as pdf:
        for page_number, page in enumerate(pdf.pages, start=1):
            tables = page.extract_tables() or []
            if tables:
                for table_number, table in enumerate(tables, start=1):
                    if not table:
                        continue
                    headers = table[0]
                    rows = table[1:]
                    columns = [str(value or "") for value in headers]
                    dataframe_rows = [
                        {
                            columns[index]: (row[index] if index < len(row) else "")
                            for index in range(len(columns))
                        }
                        for row in rows
                    ]
                    import pandas as pd

                    dataframe = pd.DataFrame(dataframe_rows, columns=columns)
                    chunks.append(
                        FinancialChunk(
                            chunk_id=f"{path.name}:page-{page_number}:table-{table_number}",
                            content=dataframe_to_markdown(dataframe),
                            chunk_type="table",
                            source_file=str(path),
                            metadata={
                                "page_number": page_number,
                                "table_number": table_number,
                            },
                        )
                    )
            else:
                text = (page.extract_text() or "").strip()
                if text:
                    chunks.append(
                        FinancialChunk(
                            chunk_id=f"{path.name}:page-{page_number}",
                            content=text,
                            chunk_type="text",
                            source_file=str(path),
                            metadata={"page_number": page_number},
                        )
                    )
    return chunks


class PDFParser:
    """Object-oriented facade for PDF parsing."""

    def parse(self, file_path: PathLike) -> List[FinancialChunk]:
        return parse_pdf(file_path)