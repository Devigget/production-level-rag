"""Pydantic contracts for hybrid retrieval."""

from typing import Any

from pydantic import BaseModel, Field


class RetrievalQuery(BaseModel):
    query_text: str
    top_k_vector: int = 10
    top_k_structured: int = 10
    top_k_graph: int = 10
    final_top_n: int = 5
    filters: dict[str, Any] | None = None
    retrieval_mode: str = "auto"


class RetrievedContext(BaseModel):
    id: str
    content: str
    source_type: str
    initial_score: float = 0.0
    rerank_score: float | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class HybridSearchResult(BaseModel):
    query: str
    ranked_contexts: list[RetrievedContext]
    total_candidates_evaluated: int