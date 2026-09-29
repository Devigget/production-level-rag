# Spec 10: Intelligent Query Routing & Dual-Path Tabular Cypher Blueprinting

## 1. Goal & Scope
Build the financial query routing engine and dual-path tabular graph compilation pipeline:
- **Intelligent Query Routing (`QueryRouter`)**:
  - Automatically classify user questions into one of three execution paths:
    1. `ROUTE_VECTOR` (`"VECTOR_SEARCH"`): Purely qualitative, semantic, descriptive, or policy-related questions (e.g., depreciation policy, audit notes, executive overview).
    2. `ROUTE_GRAPH` (`"GRAPH_TRAVERSAL"`): Multi-hop entity queries, cross-quarter comparisons, strongest/weakest quarter rankings, and structural relationship traversals.
    3. `ROUTE_HYBRID` (`"HYBRID"`): Queries requiring both quantitative financial metrics from tables and qualitative context/commentary from narrative notes.
- **Dynamic Cypher Query Generation**:
  - Compile store-bounded Cypher queries on the fly based on query semantics (e.g., detecting superlatives like "strongest quarter" and sorting by `coalesce(r.numeric_value, 0) DESC`).
- **Dual-Path Tabular Processing Pipeline**:
  - Raw financial spreadsheets (`.xlsx`, `.xls`, `.csv`) are processed along two complementary paths:
    - **Path 1 (Vector Retrieval)**: Header-injected row serialization ensuring dense vector embeddings retain row index, store context, and column headers.
    - **Path 2 (Graph Ingestion)**: Schema blueprint profiling via LLM (with deterministic heuristic fallback) compiling into parameterized Cypher batch `MERGE` statements.
- **Graph Schema Alignment**: Formal alignment with the property graph schema documented in `docs/NEO4J_QUERIES.md`.

## 2. Target File Tree
- `src/retrieval/router.py`                   # QueryRouter classification and dynamic Cypher generation
- `src/ingestion/parsers/tabular_pipeline.py` # Header-injected serialization and Cypher blueprint compiler
- `docs/NEO4J_QUERIES.md`                    # Comprehensive Cypher catalog & reference guide
- `src/retrieval/graph_search.py`            # GraphSearcher execution engine
- `tests/test_store_rag.py`                  # Verification suite for router classification & dynamic Cypher
- `tests/test_retrieval.py`                  # Graph traversal and multi-hop expansion tests

## 3. Data Contracts & Interfaces
Use Python typing and Pydantic v2:

```python
from typing import Any, Callable, Dict, List, Optional, Tuple
from pydantic import BaseModel, Field

# Query Routing Constants
ROUTE_VECTOR = "VECTOR_SEARCH"
ROUTE_GRAPH = "GRAPH_TRAVERSAL"
ROUTE_HYBRID = "HYBRID"

class SchemaBlueprint(BaseModel):
    entity_label: str = "Metric"
    key_column: str
    category_label: Optional[str] = None
    relationship_name: Optional[str] = None
    metric_edges: List[Dict[str, Any]] = Field(default_factory=list)

class QueryRoutingResult(BaseModel):
    route: str
    reasoning: str
```

## 4. Architectural Details

### 4.1. Financial Query Router (`QueryRouter`)
The router analyzes the normalized query using domain-specific lexical indicators:
1. **Quantitative Indicators**: `total`, `margin`, `ebitda`, `growth`, `increase`, `compare`, `difference`, `trend`, `ratio`, `q1`-`q4`, `2024`-`2026`, `highest`, `lowest`, `revenue`, `profit`, `net income`, `strongest`, `weakest`, `best`, `top`.
2. **Relationship & Provenance Indicators**: `who approved`, `which vendor`, `which department`, `related to`, `connected to`, `hierarchy`, `trace`, `supporting chain`, `belongs to`.
3. **Narrative & Qualitative Indicators**: `explain`, `why`, `note`, `policy`, `clause`, `description`, `summary`, `detail`, `overview`, `background`, `reason`, `commentary`, `cause`, `because of`.

#### Classification Logic:
- If **(Quantitative OR Relationship) AND Narrative** &rarr; `ROUTE_HYBRID`
- If **Relationship OR (Quantitative AND Comparison/Superlative/Trend)** &rarr; `ROUTE_GRAPH`
- If **Quantitative** (single metric lookup with grounded narrative) &rarr; `ROUTE_HYBRID`
- If **Purely Semantic / Descriptive** &rarr; `ROUTE_VECTOR`

### 4.2. Dynamic Cypher Generation (`generate_store_cypher`)
Generates parameterized, safe, store-bounded Cypher queries:
- **Superlative Quarter Queries** (e.g., *"What was the strongest quarter?"*):
  ```cypher
  MATCH (s:Store {id: $store_id})-[:CONTAINS]->(e)
  MATCH (e)-[r:RELATED|HAS_VALUE]->(t)
  WHERE (r.store_id = $store_id OR r.store_id IS NULL)
    AND (r.numeric_value IS NOT NULL OR r.value IS NOT NULL)
  RETURN e.name AS entity, type(r) AS relationship, t.name AS target, r.value AS value, r.numeric_value AS numeric_value
  ORDER BY coalesce(r.numeric_value, 0) DESC
  LIMIT 25
  ```
- **Entity Keyword Traversal Queries**:
  ```cypher
  MATCH (s:Store {id: $store_id})-[:CONTAINS]->(e)
  WHERE ($keyword = '' OR toLower(e.name) CONTAINS toLower($keyword))
  OPTIONAL MATCH (e)-[r]->(t)
  WHERE r.store_id = $store_id OR r.store_id IS NULL
  RETURN e.name AS entity, type(r) AS relationship, t.name AS target, r.value AS value, r.numeric_value AS numeric_value
  ORDER BY coalesce(r.numeric_value, 0) DESC
  LIMIT 25
  ```

### 4.3. Dual-Path Tabular Processing Pipeline

#### Path 1: Header-Injected Row Serialization
`serialize_tabular_row(row, store_name, row_index)` produces dense representations:
```text
Store: Main Ledger | Row: 0 | Metric: Revenue | Q1 2025: $1,200,000 | Q2 2025: $1,450,000
```
This guarantees that each row chunk embedded into Qdrant carries full structural context, preventing the loss of column headers during vector similarity search.

#### Path 2: LLM Schema Blueprint to Deterministic Parameterized Cypher
1. **Schema Profiling (`extract_schema_blueprint`)**:
   - Inspects table columns and previews head records.
   - LLM extracts `entity_label`, `key_column`, and `metric_edges` identifying temporal columns (quarters, years, dates).
   - If no LLM is configured or parsing fails, a deterministic regex-based heuristic baseline runs automatically.
2. **Cypher Statement Compilation (`compile_cypher_statements`)**:
   - Emits batch `MERGE` Cypher statements:
     ```cypher
     MERGE (s:Store {id: $store_id})
     ON CREATE SET s.name = $store_name
     MERGE (d:Document {id: $doc_id})
     ON CREATE SET d.filename = $filename, d.store_id = $store_id
     MERGE (s)-[:HAS_DOCUMENT]->(d)
     ```
     For each metric column:
     ```cypher
     MERGE (m:Metric {name: $metric_name, store_id: $store_id})
     MERGE (d)-[:CONTAINS_RECORD]->(m)
     MERGE (t:Quarter {name: $period, store_id: $store_id})
     MERGE (m)-[r:REPORTED_VALUE {period: $period, store_id: $store_id}]->(t)
     SET r.value = $raw_val, r.numeric_value = $num_val, r.doc_id = $doc_id
     MERGE (d)-[:SOURCE_FOR]->(r)
     ```
3. **Execution (`execute_cypher_ingestion`)**:
   - Executes compiled Cypher statements against Neo4j inside parameterized transactions.

## 5. Verification & Acceptance Criteria
1. `tests/test_store_rag.py::test_query_router_classification`:
   - Verifies classification of narrative policy queries to `ROUTE_VECTOR`.
   - Verifies classification of cross-period growth and superlative queries to `ROUTE_GRAPH`.
   - Verifies classification of metric + explanation queries to `ROUTE_HYBRID`.
   - Verifies dynamic Cypher generation with `ORDER BY coalesce(r.numeric_value, 0) DESC`.
2. `tests/test_retrieval.py::test_engine_routes_relationship_queries_to_graph`:
   - Validates that relationship questions invoke the Neo4j graph search path.
3. `tests/test_indexing.py::test_graph_extractor_extracts_metrics_and_quarters`:
   - Verifies table chunk decomposition into metrics and quarters.
