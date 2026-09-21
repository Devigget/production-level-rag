# Spec 02: Hybrid Graph & Vector Storage Engine

## 1. Goal & Scope
Build the structured, vector, and optional graph indexing layer:
- **Vector Store (Qdrant)**: Embed and store `FinancialChunk` text/tables for dense semantic retrieval.
- **Structured Store**: Persist normalized metric-period-value records for deterministic KPI retrieval and Power BI datasets.
- **Graph Store (Neo4j)**: Extract financial entities, line items, and relationships from chunks, persisting them into a property graph for optional cross-hop queries.
- Graph indexing must not be treated as proof that every query needs GraphRAG; graph retrieval is selected by query intent.
- Connects directly downstream from Spec 01's output (`FinancialChunk`).

## 2. Target File Tree
- `src/indexing/config.py`          # Connection settings (Qdrant & Neo4j credentials)
- `src/indexing/vector_store.py`    # Qdrant client wrapper (upsert, embed, search)
- `src/indexing/graph_extractor.py` # Extraction logic: text/tables -> financial entities & triples
- `src/indexing/graph_store.py`     # Neo4j client wrapper (Cypher queries, node/edge ingestion)
- `src/indexing/indexer.py`         # Unified indexing coordinator
- `tests/test_indexing.py`          # Verification suite with mocks/in-memory instances

## 3. Data Contracts & Interfaces
Use Pydantic v2:

```python
from pydantic import BaseModel, Field
from typing import List, Optional

class GraphEntity(BaseModel):
    name: str
    category: str  # e.g., "Company", "Vendor", "Metric", "Quarter", "Department"

class GraphRelation(BaseModel):
    source_entity: str
    target_entity: str
    relationship_type: str  # e.g., "REPORTED_METRIC", "HAS_EXPENSE", "PART_OF"
    properties: dict = Field(default_factory=dict)

class ExtractedGraphData(BaseModel):
    entities: List[GraphEntity]
    relations: List[GraphRelation]