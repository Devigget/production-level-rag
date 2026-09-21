"""Data contracts for financial document ingestion."""

from typing import Any, Dict, List

from pydantic import BaseModel, Field


class FinancialRecord(BaseModel):
    metric: str
    period: str
    value: float | None = None
    raw_value: str = ""
    source_file: str
    sheet_name: str | None = None
    metadata: Dict[str, Any] = Field(default_factory=dict)


class FinancialChunk(BaseModel):
    chunk_id: str
    content: str
    chunk_type: str
    source_file: str
    metadata: Dict[str, Any] = Field(default_factory=dict)
    structured_records: List[FinancialRecord] = Field(default_factory=list)


class IngestionResult(BaseModel):
    source_file: str
    total_chunks: int
    chunks: List[FinancialChunk]


class UnsupportedFileTypeError(ValueError):
    """Raised when the ingestion pipeline receives an unsupported extension."""
