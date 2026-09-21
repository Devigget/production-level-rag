# Spec 01: Multimodal Financial Document Ingestion

## 1. Goal & Scope
Build the ingestion layer for financial documents and a Power BI-ready financial data contract.
- Supported file types: `.pdf` (financial reports), `.xlsx`/`.csv` (balance sheets, P&L tables), `.png`/`.jpeg` (receipt scans).
- The pipeline parses raw files into structured Markdown tables, normalized financial records, and semantic text chunks while preserving numerical relationships and sheet/page metadata.
- Normalized records are the source for dashboard measures; Markdown/text chunks are evidence for narrative retrieval.

## 2. Target File Tree
- `src/ingestion/models.py`        # Ingestion data schemas
- `src/ingestion/parsers/pdf.py`   # Table-aware PDF parser
- `src/ingestion/parsers/table.py` # Excel/CSV sheet extraction
- `src/ingestion/pipeline.py`      # Unified orchestrator class
- `tests/test_ingestion.py`        # Verification test suite

## 3. Data Contracts & Interfaces
Use Pydantic v2:

```python
from pydantic import BaseModel, Field
from typing import List, Dict, Any, Optional

class FinancialChunk(BaseModel):
    chunk_id: str
    content: str  # Markdown text or Markdown table representation
    chunk_type: str  # "table", "text", or "receipt_metadata"
    source_file: str
    metadata: Dict[str, Any] = Field(default_factory=dict)
    structured_records: List[FinancialRecord] = Field(default_factory=list)
    # metadata keys: page_number, sheet_name, fiscal_quarter, fiscal_year

class FinancialRecord(BaseModel):
    metric: str
    period: str
    value: Optional[float]
    raw_value: str
    source_file: str
    sheet_name: Optional[str] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)

class IngestionResult(BaseModel):
    source_file: str
    total_chunks: int
    chunks: List[FinancialChunk]