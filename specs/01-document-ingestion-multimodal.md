# Spec 01: Multimodal Financial Document Ingestion

## 1. Goal & Scope
Build the ingestion layer for financial documents.
- Supported file types: `.pdf` (financial reports), `.xlsx`/`.csv` (balance sheets, P&L tables), `.png`/`.jpeg` (receipt scans).
- The pipeline parses raw files into structured Markdown tables and semantic text chunks while preserving numerical relationships and sheet/page metadata.

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
    # metadata keys: page_number, sheet_name, fiscal_quarter, fiscal_year

class IngestionResult(BaseModel):
    source_file: str
    total_chunks: int
    chunks: List[FinancialChunk]