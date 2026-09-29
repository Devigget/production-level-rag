# Spec 02: Hybrid Graph & Vector Storage Engine

## 1. Goal & Scope
Build the structured, dense vector, and property graph storage and indexing engine:
- **Vector Store (Qdrant)**:
  - Generate dense embeddings for all `FinancialChunk` objects.
  - Store embeddings with serialized chunk payloads, indexed with UUIDv5 hashes.
  - Support strict multi-store tenant isolation by tagging points with `store_id` and executing filtered similarity searches.
  - Support both local in-memory (`:memory:`) operation for deterministic testing and remote Qdrant service deployment.
- **Structured Store (`StructuredFinancialStore`)**:
  - In-memory deterministic store indexing normalized `FinancialRecord` tuples `(source_file, sheet_name, metric, period)`.
  - Enables exact numerical retrieval for Power BI dashboard datasets and deterministic KPI comparisons.
- **Graph Store (Neo4j)**:
  - Extract financial entities, line items, and temporal relationships from Markdown tables and narrative chunks.
  - Maintain a tenant-aware graph hierarchy:
    `(:Store)-[:HAS_DOCUMENT]->(:Document)-[:REPORTED_METRIC]->(:Metric)-[:HAS_VALUE]->(:Period)`
  - Register document metadata (`register_document`) and link unstructured entities (`link_unstructured_entities`) during ingestion and on system startup (`startup_sync_graph`).
- **Unified Indexing Coordinator (`FinancialIndexer`)**:
  - Orchestrate simultaneous indexing across Qdrant, Neo4j, and the structured record store.

## 2. Target File Tree
- `src/indexing/config.py`             # IndexingSettings (Qdrant & Neo4j credentials, model dimensions)
- `src/indexing/vector_store.py`       # VectorStore client wrapper (HashEmbedder, upsert, payload filtering, search)
- `src/indexing/graph_extractor.py`    # Entity and relationship extraction logic from tables and narrative chunks
- `src/indexing/graph_store.py`        # Neo4j client wrapper (parameterized Cypher queries, registration, linking)
- `src/indexing/indexer.py`            # FinancialIndexer coordinator class
- `src/retrieval/structured_search.py` # StructuredFinancialStore indexing normalized records
- `tests/test_indexing.py`             # 5-test verification suite with in-memory Qdrant & mocked Neo4j

## 3. Data Contracts & Interfaces
Use Pydantic v2:

```python
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field

class GraphEntity(BaseModel):
    name: str
    category: str  # "Company", "Vendor", "Metric", "Quarter", "Document", "Department"

class GraphRelation(BaseModel):
    source_entity: str
    target_entity: str
    relationship_type: str  # "REPORTED_METRIC", "HAS_VALUE", "DEFINES", "MENTIONS", "RELATED"
    properties: Dict[str, Any] = Field(default_factory=dict)

class ExtractedGraphData(BaseModel):
    entities: List[GraphEntity]
    relations: List[GraphRelation]

class IndexingSummary(BaseModel):
    chunks_indexed: int
    structured_records_indexed: int
    entities_indexed: int
    relations_indexed: int
```

## 4. Graph Schema & Vector Storage Details

### 4.1. Neo4j Property Graph Schema
```mermaid
graph TD
    Store["(:Store {id, name})"]
    Doc["(:Document {id, filename, store_id, file_type, total_chunks})"]
    Metric["(:Metric {name, store_id, category})"]
    FinEntity["(:FinancialEntity {name, category, store_id})"]
    Quarter["(:Quarter / :Period {name, store_id})"]

    Store -->|HAS_DOCUMENT| Doc
    Store -->|CONTAINS| Metric
    Store -->|CONTAINS| FinEntity
    Doc -->|REPORTED_METRIC| Metric
    Doc -->|DEFINES| Metric
    Doc -->|MENTIONS| FinEntity
    Metric -->|HAS_VALUE {value, numeric_value, doc_id, store_id}| Quarter
    FinEntity -->|RELATED {type, doc_id, store_id}| FinEntity
```

### 4.2. Document Registration & Unstructured Linking
1. **Document Registration (`register_document`)**:
   Merges `(:Store {id: $store_id})`, `(:Document {id: $doc_id})`, and creates the `[:HAS_DOCUMENT]` link with file metadata (`filename`, `total_chunks`, `chunk_types`, `uploaded_at`).
2. **Entity Scoping & Linking (`link_unstructured_entities`)**:
   Matches entities extracted from the source document, sets their `store_id`, links them into `(:Store)-[:CONTAINS]->(target)`, and maps document provenance relationships (`[:REPORTED_METRIC]`, `[:DEFINES]`, `[:MENTIONS]`).

### 4.3. Qdrant Vector Payload Schema
Points are inserted into the Qdrant collection with UUIDv5 derived from the chunk ID:
```json
{
  "id": "uuid-v5-chunk-id",
  "vector": [0.042, -0.015, "..."],
  "payload": {
    "store_id": "store-123",
    "doc_id": "doc-456",
    "chunk": {
      "chunk_id": "sample_pnl.csv:P&L:row-0",
      "content": "Store: Retail | Row: 0 | Metric: Revenue | Q1 2025: $1,200,000",
      "chunk_type": "table",
      "source_file": "sample_pnl.csv",
      "metadata": { "sheet_name": "P&L", "row_index": 0 }
    }
  }
}
```
Queries specifying `store_id` apply a Qdrant `FieldCondition(key="store_id", match=MatchValue(value=store_id))` to enforce strict tenant boundary filtering.

### 4.4. Embedding Architecture
- **Production**: `sentence-transformers/all-MiniLM-L6-v2` (384 dimensions) loaded via injected embedder.
- **Offline / Test Mode**: `HashEmbedder` generates deterministic normalized vectors using SHA-256 token hashing, avoiding external model downloads during automated testing.

## 5. Verification & Acceptance Criteria
Verified by **5 passing tests** in `tests/test_indexing.py`:
1. `test_vector_store_uses_in_memory_qdrant`: Validates Qdrant collection creation, payload storage, and similarity search in `:memory:` mode.
2. `test_graph_extractor_extracts_metrics_and_quarters`: Validates entity and relation extraction from Markdown tables.
3. `test_graph_store_uses_mocked_neo4j_driver`: Validates parameterized Cypher execution for entities and relations using a mocked Neo4j driver.
4. `test_indexer_combines_vector_and_graph_layers`: Validates end-to-end coordination through `FinancialIndexer`.
5. `test_graph_store_registers_document_and_links_unstructured`: Validates store registration, document linking, and entity scoping in Neo4j.