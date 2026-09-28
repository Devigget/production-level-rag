"""Unified financial document ingestion pipeline with store-scoped dual-path processing."""

from pathlib import Path
from typing import Union

import pandas as pd

from .models import FinancialChunk, IngestionResult, UnsupportedFileTypeError
from .parsers.document import parse_docx_file, parse_text_file
from .parsers.image import parse_image
from .parsers.pdf import parse_pdf
from .parsers.table import parse_table_file
from .parsers.tabular_pipeline import extract_tabular_vector_chunks

PathLike = Union[str, Path]
SUPPORTED_EXTENSIONS = {".csv", ".docx", ".jpeg", ".jpg", ".pdf", ".png", ".txt", ".xls", ".xlsx"}


class FinancialIngestionPipeline:
    """Route supported financial files to their format-specific parser with store isolation."""

    def ingest(
        self,
        file_path: PathLike,
        store_id: str = "default",
        store_name: str = "Main Store",
        doc_id: str = "",
        dual_path: bool = False,
    ) -> IngestionResult:
        path = Path(file_path)
        extension = path.suffix.lower()
        if extension not in SUPPORTED_EXTENSIONS:
            supported = ", ".join(sorted(SUPPORTED_EXTENSIONS))
            raise UnsupportedFileTypeError(
                f"Unsupported file type '{path.suffix or '<none>'}'. "
                f"Supported types: {supported}"
            )

        chunks: list[FinancialChunk] = []

        if extension in {".csv", ".xlsx", ".xls"}:
            if dual_path:
                # Tabular Dual Path: Header-Injected Row Serialization + Table Overview
                if extension == ".csv":
                    sheets = {path.stem: pd.read_csv(path)}
                elif extension in {".xlsx", ".xls"}:
                    engine = "openpyxl" if extension == ".xlsx" else None
                    sheets = pd.read_excel(path, sheet_name=None, engine=engine)
                for sheet_name, df in sheets.items():
                    sheet_chunks = extract_tabular_vector_chunks(
                        df,
                        store_id=store_id,
                        store_name=store_name,
                        doc_id=doc_id,
                        source_file=path.name,
                        sheet_name=str(sheet_name),
                    )
                    chunks.extend(sheet_chunks)
            else:
                chunks = parse_table_file(path)
        elif extension == ".pdf":
            chunks = parse_pdf(path, store_id=store_id, doc_id=doc_id)
        elif extension == ".txt":
            chunks = parse_text_file(path, store_id=store_id, doc_id=doc_id)
        elif extension == ".docx":
            chunks = parse_docx_file(path, store_id=store_id, doc_id=doc_id)
        else:
            chunks = parse_image(path)

        for chunk in chunks:
            chunk.store_id = store_id
            chunk.doc_id = doc_id
            chunk.metadata.setdefault("store_id", store_id)
            chunk.metadata.setdefault("doc_id", doc_id)

        return IngestionResult(
            source_file=str(path),
            total_chunks=len(chunks),
            chunks=chunks,
        )

    def parse(self, file_path: PathLike, **kwargs) -> IngestionResult:
        """Alias for ingest for callers that use parser terminology."""
        return self.ingest(file_path, **kwargs)
