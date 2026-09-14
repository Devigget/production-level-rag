"""Unified financial document ingestion pipeline."""

from pathlib import Path
from typing import Union

from PIL import Image

from .models import FinancialChunk, IngestionResult, UnsupportedFileTypeError
from .parsers.pdf import parse_pdf
from .parsers.table import parse_table_file


PathLike = Union[str, Path]
SUPPORTED_EXTENSIONS = {".csv", ".jpeg", ".pdf", ".png", ".xlsx"}


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
        else:
            chunks = [_image_metadata_chunk(path)]
        return IngestionResult(
            source_file=str(path),
            total_chunks=len(chunks),
            chunks=chunks,
        )

    def parse(self, file_path: PathLike) -> IngestionResult:
        """Alias for ingest for callers that use parser terminology."""
        return self.ingest(file_path)


def _image_metadata_chunk(path: Path) -> FinancialChunk:
    with Image.open(path) as image:
        metadata = {
            "format": image.format,
            "width": image.width,
            "height": image.height,
            "mode": image.mode,
        }
    return FinancialChunk(
        chunk_id=path.name,
        content=f"Receipt image: {path.name}",
        chunk_type="receipt_metadata",
        source_file=str(path),
        metadata=metadata,
    )