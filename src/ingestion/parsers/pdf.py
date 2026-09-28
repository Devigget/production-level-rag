"""Table-aware and layout-preserving PDF parser."""

from pathlib import Path
from typing import List, Union

import pandas as pd
import pdfplumber

from ..models import FinancialChunk
from .document import recursive_character_sentence_chunking
from .table import dataframe_to_markdown

PathLike = Union[str, Path]


def parse_pdf(
    file_path: PathLike,
    store_id: str = "default",
    doc_id: str = "",
) -> List[FinancialChunk]:
    """Extract PDF tables as Markdown and narrative text as text chunks, retaining page metadata.

    Both structured tables and narrative content (e.g., titles, preparer metadata,
    summaries, commentary) are preserved on each page.
    """
    path = Path(file_path)
    chunks: List[FinancialChunk] = []
    with pdfplumber.open(path) as pdf:
        for page_number, page in enumerate(pdf.pages, start=1):
            table_bboxes = []
            if hasattr(page, "find_tables"):
                try:
                    found_tables = page.find_tables() or []
                    table_bboxes = [t.bbox for t in found_tables if hasattr(t, "bbox")]
                except Exception:
                    table_bboxes = []

            # 1. Extract tables as structured Markdown chunks
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
                    dataframe = pd.DataFrame(dataframe_rows, columns=columns)
                    chunks.append(
                        FinancialChunk(
                            chunk_id=f"{path.name}:page-{page_number}:table-{table_number}",
                            content=dataframe_to_markdown(dataframe),
                            chunk_type="table",
                            source_file=str(path),
                            store_id=store_id,
                            doc_id=doc_id,
                            source_type="tabular",
                            metadata={
                                "page_number": page_number,
                                "table_number": table_number,
                                "store_id": store_id,
                                "doc_id": doc_id,
                            },
                        )
                    )

            # 2. Extract narrative text from page (excluding table bounding boxes to avoid duplicate data)
            text = ""
            if table_bboxes and hasattr(page, "filter"):
                def not_in_table(obj: dict) -> bool:
                    x0, top, x1, bottom = obj["x0"], obj["top"], obj["x1"], obj["bottom"]
                    for bx0, btop, bx1, bbottom in table_bboxes:
                        if not (x1 <= bx0 or x0 >= bx1 or bottom <= btop or top >= bbottom):
                            return False
                    return True

                try:
                    filtered_page = page.filter(not_in_table)
                    text = (filtered_page.extract_text() or "").strip()
                except Exception:
                    text = ""

            # Fallback to full page text if table filtering yielded nothing or wasn't applicable
            if not text:
                raw_page_text = (page.extract_text() or "").strip()
                # If there are no tables, or if raw text has content when filtering yielded nothing
                if not tables or not table_bboxes:
                    text = raw_page_text

            if text:
                text_pieces = recursive_character_sentence_chunking(text)
                for idx, piece in enumerate(text_pieces):
                    chunk_id = (
                        f"{path.name}:page-{page_number}"
                        if len(text_pieces) == 1
                        else f"{path.name}:page-{page_number}:chunk-{idx}"
                    )
                    chunks.append(
                        FinancialChunk(
                            chunk_id=chunk_id,
                            content=piece,
                            chunk_type="text",
                            source_file=str(path),
                            store_id=store_id,
                            doc_id=doc_id,
                            source_type="unstructured",
                            metadata={
                                "page_number": page_number,
                                "store_id": store_id,
                                "doc_id": doc_id,
                                "chunk_index": idx,
                            },
                        )
                    )
    return chunks


class PDFParser:
    """Object-oriented facade for PDF parsing."""

    def parse(
        self,
        file_path: PathLike,
        store_id: str = "default",
        doc_id: str = "",
    ) -> List[FinancialChunk]:
        return parse_pdf(file_path, store_id=store_id, doc_id=doc_id)