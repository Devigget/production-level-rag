"""Unified financial document ingestion pipeline."""

from pathlib import Path
from typing import Union

from .models import FinancialChunk, IngestionResult, UnsupportedFileTypeError
from .parsers.document import parse_docx_file, parse_text_file
from .parsers.image import parse_image
from .parsers.pdf import parse_pdf
from .parsers.table import parse_table_file


PathLike = Union[str, Path]
SUPPORTED_EXTENSIONS = {".csv", ".docx", ".jpeg", ".jpg", ".pdf", ".png", ".txt", ".xlsx"}


class FinancialIngestionPipeline:
    """Route supported financial files to their format-specific parser."""

    def ingest(self, file_path: PathLike) -> IngestionResult:
        path = Path(file_path)
        extension = path.suffix.lower()
        if extension not in SUPPORTED_EXTENSIONS:
            supported = ", ".join(sorted(SUPPORTED_EXTENSIONS))
            raise UnsupportedFileTypeError(
                f"Unsupported file type '{path.suffix or '<none>'}'. "
                f"Supported types: {supported}"
            )

        if extension == ".pdf":
            chunks = parse_pdf(path)
        elif extension in {".csv", ".xlsx"}:
            chunks = parse_table_file(path)
        elif extension == ".txt":
            chunks = parse_text_file(path)
        elif extension == ".docx":
            chunks = parse_docx_file(path)
        else:
            chunks = parse_image(path)
        return IngestionResult(
            source_file=str(path),
            total_chunks=len(chunks),
            chunks=chunks,
        )

    def parse(self, file_path: PathLike) -> IngestionResult:
        """Alias for ingest for callers that use parser terminology."""
        return self.ingest(file_path)
