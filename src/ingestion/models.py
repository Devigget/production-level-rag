"""Data contracts for financial document ingestion."""

from typing import Any

from pydantic import BaseModel, Field


class FinancialChunk(BaseModel):
    chunk_id: str
    content: str
    chunk_type: str
    source_file: str
    metadata: dict[str, Any] = Field(default_factory=dict)


class IngestionResult(BaseModel):
    source_file: str
    total_chunks: int
    chunks: list[FinancialChunk]


class UnsupportedFileTypeError(ValueError):
    """Raised when the ingestion pipeline receives an unsupported extension."""
