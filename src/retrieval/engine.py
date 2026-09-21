"""Hybrid retrieval coordinator."""

import logging
import time
from typing import Any

from .models import HybridSearchResult, RetrievedContext, RetrievalQuery
from .reranker import CrossEncoderReranker


logger = logging.getLogger(__name__)


class HybridRetrievalEngine:
    def __init__(self, vector_search: Any, graph_search: Any, reranker: Any | None = None,
                 structured_search: Any | None = None):
        self.vector_search = vector_search
        self.graph_search = graph_search
        self.structured_search = structured_search
        self.reranker = reranker or CrossEncoderReranker()

    def retrieve(self, request: RetrievalQuery | str) -> HybridSearchResult:
        started = time.perf_counter()
        query = request if isinstance(request, RetrievalQuery) else RetrievalQuery(query_text=request)
        structured_contexts = (
            self.structured_search.search(query.query_text, query.top_k_structured)
            if self.structured_search is not None and query.top_k_structured > 0
            else []
        )
        vector_contexts = self.vector_search.search(
            query.query_text, query.top_k_vector, query.filters
        )
        graph_limit = query.top_k_graph
        if query.retrieval_mode == "auto" and self._needs_graph(query.query_text):
            graph_limit = max(graph_limit, 10)
        graph_contexts = (
            self.graph_search.search(query.query_text, graph_limit)
            if graph_limit > 0
            else []
        )
        candidates = self._deduplicate([*structured_contexts, *vector_contexts, *graph_contexts])
        ranked = self.reranker.rerank(query.query_text, candidates, query.final_top_n)
        logger.info(
            "retrieval_completed structured=%d vector=%d graph=%d candidates=%d selected=%d mode=%s duration_ms=%.1f",
            len(structured_contexts), len(vector_contexts), len(graph_contexts),
            len(candidates), len(ranked), query.retrieval_mode,
            (time.perf_counter() - started) * 1000,
        )
        return HybridSearchResult(
            query=query.query_text,
            ranked_contexts=ranked,
            total_candidates_evaluated=len(candidates),
        )

    search = retrieve

    @staticmethod
    def _needs_graph(query: str) -> bool:
        relationship_terms = (
            "who approved", "which vendor", "which department", "related to",
            "across subsidiaries", "trace", "supporting chain", "ownership",
        )
        normalized = query.lower()
        return any(term in normalized for term in relationship_terms)

    @staticmethod
    def _deduplicate(contexts: list[RetrievedContext]) -> list[RetrievedContext]:
        unique: dict[str, RetrievedContext] = {}
        for context in contexts:
            existing = unique.get(context.id)
            if existing is None or HybridRetrievalEngine._is_better_context(context, existing):
                unique[context.id] = context
        return list(unique.values())

    @staticmethod
    def _is_better_context(candidate: RetrievedContext, existing: RetrievedContext) -> bool:
        candidate_has_table = "|" in candidate.content and "\n" in candidate.content
        existing_has_table = "|" in existing.content and "\n" in existing.content
        if candidate_has_table != existing_has_table:
            return candidate_has_table
        if len(candidate.content) != len(existing.content):
            return len(candidate.content) > len(existing.content)
        return candidate.initial_score > existing.initial_score