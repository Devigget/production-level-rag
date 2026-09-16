"""Hybrid retrieval coordinator."""

from typing import Any

from .models import HybridSearchResult, RetrievedContext, RetrievalQuery
from .reranker import CrossEncoderReranker


class HybridRetrievalEngine:
    def __init__(self, vector_search: Any, graph_search: Any, reranker: Any | None = None):
        self.vector_search = vector_search
        self.graph_search = graph_search
        self.reranker = reranker or CrossEncoderReranker()

    def retrieve(self, request: RetrievalQuery | str) -> HybridSearchResult:
        query = request if isinstance(request, RetrievalQuery) else RetrievalQuery(query_text=request)
        vector_contexts = self.vector_search.search(
            query.query_text, query.top_k_vector, query.filters
        )
        graph_contexts = self.graph_search.search(query.query_text, query.top_k_graph)
        candidates = self._deduplicate([*vector_contexts, *graph_contexts])
        ranked = self.reranker.rerank(query.query_text, candidates, query.final_top_n)
        return HybridSearchResult(
            query=query.query_text,
            ranked_contexts=ranked,
            total_candidates_evaluated=len(candidates),
        )

    search = retrieve

    @staticmethod
    def _deduplicate(contexts: list[RetrievedContext]) -> list[RetrievedContext]:
        unique: dict[str, RetrievedContext] = {}
        for context in contexts:
            existing = unique.get(context.id)
            if existing is None or context.initial_score > existing.initial_score:
                unique[context.id] = context
        return list(unique.values())