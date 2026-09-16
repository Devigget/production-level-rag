# Spec 03: Hybrid Retrieval & Cross-Encoder Reranking

## 1. Goal & Scope
Build the dual-retrieval and reranking pipeline:
- **Dense Semantic Retrieval**: Query Qdrant for top-K semantically relevant document chunks.
- **Graph Knowledge Retrieval**: Traverse Neo4j for 1-hop and 2-hop connected entities, metrics, and relationships matching entities present in the query.
- **Context Fusion**: Interleave and deduplicate chunks from both sources into a unified candidate pool.
- **Cross-Encoder Reranking**: Apply a cross-encoder model (`BAAI/bge-reranker-base` or `cross-encoder/ms-marco-MiniLM-L-6-v2`) to score relevance of each candidate against the query and truncate to top-N contexts.

## 2. Target File Tree
- `src/retrieval/models.py`        # Query, RetrievalResult, and RerankedChunk schemas
- `src/retrieval/vector_search.py` # Vector retrieval implementation using Qdrant
- `src/retrieval/graph_search.py`  # Entity-directed Cypher traversal via Neo4j
- `src/retrieval/reranker.py`      # Cross-Encoder scoring engine
- `src/retrieval/engine.py`        # HybridRetrievalEngine orchestrator class
- `tests/test_retrieval.py`        # Comprehensive retrieval and reranker test suite

## 3. Data Contracts & Interfaces
Use Pydantic v2:

```python
from pydantic import BaseModel, Field
from typing import List, Dict, Any, Optional

class RetrievalQuery(BaseModel):
    query_text: str
    top_k_vector: int = 10
    top_k_graph: int = 10
    final_top_n: int = 5
    filters: Optional[Dict[str, Any]] = None

class RetrievedContext(BaseModel):
    id: str
    content: str
    source_type: str  # "vector_chunk" or "graph_subgraph"
    initial_score: float = 0.0
    rerank_score: Optional[float] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)

class HybridSearchResult(BaseModel):
    query: str
    ranked_contexts: List[RetrievedContext]
    total_candidates_evaluated: int