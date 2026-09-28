"""Parsers for plain-text and Word documents with recursive character/sentence chunking."""

from __future__ import annotations

import re
from pathlib import Path
from typing import List, Union

from docx import Document

from ..models import FinancialChunk

PathLike = Union[str, Path]


def recursive_character_sentence_chunking(
    text: str,
    target_chunk_chars: int = 2000,  # ~400-500 tokens
    overlap_chars: int = 250,        # ~10-15% overlap
) -> list[str]:
    """Recursively split text into coherent chunks by paragraph, sentence, and space."""
    clean_text = text.strip()
    if not clean_text or len(clean_text) <= target_chunk_chars:
        return [clean_text] if clean_text else []

    paragraphs = re.split(r"\n\s*\n", clean_text)
    chunks: list[str] = []
    current_chunk = ""

    for para in paragraphs:
        para = para.strip()
        if not para:
            continue
        if len(para) > target_chunk_chars:
            # Paragraph itself is too large, split by sentences
            sentences = re.split(r"(?<=[.?!])\s+", para)
            for sentence in sentences:
                if len(current_chunk) + len(sentence) + 1 <= target_chunk_chars:
                    current_chunk = f"{current_chunk} {sentence}".strip()
                else:
                    if current_chunk:
                        chunks.append(current_chunk)
                        # Retain overlap from end of current chunk
                        overlap = current_chunk[-overlap_chars:] if len(current_chunk) > overlap_chars else ""
                        current_chunk = f"{overlap} {sentence}".strip()
                    else:
                        chunks.append(sentence[:target_chunk_chars])
                        current_chunk = sentence[target_chunk_chars - overlap_chars:]
        else:
            if len(current_chunk) + len(para) + 2 <= target_chunk_chars:
                current_chunk = f"{current_chunk}\n\n{para}".strip()
            else:
                if current_chunk:
                    chunks.append(current_chunk)
                    overlap = current_chunk[-overlap_chars:] if len(current_chunk) > overlap_chars else ""
                    current_chunk = f"{overlap}\n\n{para}".strip()
                else:
                    current_chunk = para

    if current_chunk:
        chunks.append(current_chunk)

    return chunks


def parse_text_file(
    file_path: PathLike,
    store_id: str = "default",
    doc_id: str = "",
) -> List[FinancialChunk]:
    """Read a UTF-8 text document with recursive sentence/character chunking."""
    path = Path(file_path)
    content = path.read_text(encoding="utf-8-sig").strip()
    if not content:
        return []

    text_chunks = recursive_character_sentence_chunking(content)
    if len(text_chunks) == 1:
        return [
            FinancialChunk(
                chunk_id=path.name,
                content=text_chunks[0],
                chunk_type="text",
                source_file=str(path),
                store_id=store_id,
                doc_id=doc_id,
                source_type="unstructured",
                metadata={"store_id": store_id, "doc_id": doc_id, "chunk_index": 0},
            )
        ]

    chunks = []
    for idx, piece in enumerate(text_chunks):
        chunks.append(
            FinancialChunk(
                chunk_id=f"{path.name}:chunk-{idx}",
                content=piece,
                chunk_type="text",
                source_file=str(path),
                store_id=store_id,
                doc_id=doc_id,
                source_type="unstructured",
                metadata={"store_id": store_id, "doc_id": doc_id, "chunk_index": idx},
            )
        )
    return chunks


def parse_docx_file(
    file_path: PathLike,
    store_id: str = "default",
    doc_id: str = "",
) -> List[FinancialChunk]:
    """Extract non-empty paragraphs from a Word document with recursive chunking."""
    path = Path(file_path)
    document = Document(path)
    paragraphs = [paragraph.text.strip() for paragraph in document.paragraphs]
    content = "\n".join(paragraph for paragraph in paragraphs if paragraph)
    if not content:
        return []

    text_chunks = recursive_character_sentence_chunking(content)
    if len(text_chunks) == 1:
        return [
            FinancialChunk(
                chunk_id=path.name,
                content=text_chunks[0],
                chunk_type="text",
                source_file=str(path),
                store_id=store_id,
                doc_id=doc_id,
                source_type="unstructured",
                metadata={"store_id": store_id, "doc_id": doc_id, "chunk_index": 0},
            )
        ]

    chunks = []
    for idx, piece in enumerate(text_chunks):
        chunks.append(
            FinancialChunk(
                chunk_id=f"{path.name}:chunk-{idx}",
                content=piece,
                chunk_type="text",
                source_file=str(path),
                store_id=store_id,
                doc_id=doc_id,
                source_type="unstructured",
                metadata={"store_id": store_id, "doc_id": doc_id, "chunk_index": idx},
            )
        )
    return chunks


class DocumentParser:
    """Object-oriented facade for plain-text and Word parsing."""

    def parse(
        self,
        file_path: PathLike,
        store_id: str = "default",
        doc_id: str = "",
    ) -> List[FinancialChunk]:
        suffix = Path(file_path).suffix.lower()
        if suffix == ".txt":
            return parse_text_file(file_path, store_id=store_id, doc_id=doc_id)
        if suffix == ".docx":
            return parse_docx_file(file_path, store_id=store_id, doc_id=doc_id)
        raise ValueError(f"Unsupported document extension: {suffix}")