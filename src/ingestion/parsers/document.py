"""Parsers for plain-text and Word documents."""

from pathlib import Path
from typing import List, Union

from docx import Document

from ..models import FinancialChunk


PathLike = Union[str, Path]


def parse_text_file(file_path: PathLike) -> List[FinancialChunk]:
    """Read a UTF-8 text document as a searchable content chunk."""
    path = Path(file_path)
    content = path.read_text(encoding="utf-8-sig").strip()
    if not content:
        return []
    return [
        FinancialChunk(
            chunk_id=path.name,
            content=content,
            chunk_type="text",
            source_file=str(path),
        )
    ]


def parse_docx_file(file_path: PathLike) -> List[FinancialChunk]:
    """Extract non-empty paragraphs from a Word document as searchable text."""
    path = Path(file_path)
    document = Document(path)
    paragraphs = [paragraph.text.strip() for paragraph in document.paragraphs]
    content = "\n".join(paragraph for paragraph in paragraphs if paragraph)
    if not content:
        return []
    return [
        FinancialChunk(
            chunk_id=path.name,
            content=content,
            chunk_type="text",
            source_file=str(path),
        )
    ]


class DocumentParser:
    """Object-oriented facade for plain-text and Word parsing."""

    def parse(self, file_path: PathLike) -> List[FinancialChunk]:
        suffix = Path(file_path).suffix.lower()
        if suffix == ".txt":
            return parse_text_file(file_path)
        if suffix == ".docx":
            return parse_docx_file(file_path)
        raise ValueError(f"Unsupported document extension: {suffix}")