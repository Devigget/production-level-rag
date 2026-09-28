"""Hybrid retrieval coordinator."""

import logging
import time
from typing import Any

from .models import HybridSearchResult, RetrievedContext, RetrievalQuery
from .reranker import CrossEncoderReranker


logger = logging.getLogger(__name__)


class HybridRetrievalEngine:
    def __init__(self, vector_search: Any, graph_search: Any, reranker: Any | None = None,
                 structured_search: Any | None = None, llm_invoker: Any | None = None):
        self.vector_search = vector_search
        self.graph_search = graph_search
        self.structured_search = structured_search
        self.reranker = reranker or CrossEncoderReranker()
        self.llm_invoker = llm_invoker

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
        store_id = query.store_id if query.store_id and query.store_id != "default" else None
        graph_contexts = (
            self.graph_search.search(query.query_text, graph_limit, store_id=store_id)
            if graph_limit > 0 and store_id
            else (self.graph_search.search(query.query_text, graph_limit) if graph_limit > 0 else [])
        )
        candidates = self._deduplicate([*structured_contexts, *vector_contexts, *graph_contexts])

        # Multi-Hop Entity Expansion (Hop 2)
        hop2_contexts: list[RetrievedContext] = []
        if self._needs_entity_expansion(query.query_text) and candidates:
            hop2_contexts = self._perform_entity_expansion(query, candidates)
            if hop2_contexts:
                candidates = self._deduplicate([*candidates, *hop2_contexts])

        ranked = self.reranker.rerank(query.query_text, candidates, query.final_top_n)

        # Cross-document coverage guarantee: Ensure high-relevance Hop 2 contexts (e.g. tabular line items)
        # are not squeezed out by single-document bias in the reranker
        if hop2_contexts and ranked:
            table_hop2 = next(
                (c for c in hop2_contexts if ("row-" in c.id or c.source_type in {"table", "tabular", "structured_record"}) and not any(r.id == c.id for r in ranked)),
                None
            )
            if table_hop2 is None:
                table_hop2 = next((c for c in hop2_contexts if not any(r.id == c.id for r in ranked)), None)
            if table_hop2 is not None:
                ranked = [ranked[0], table_hop2, *[r for r in ranked[1:] if r.id != table_hop2.id]][:query.final_top_n]

        logger.info(
            "retrieval_completed structured=%d vector=%d graph=%d hop2=%d candidates=%d selected=%d mode=%s duration_ms=%.1f",
            len(structured_contexts), len(vector_contexts), len(graph_contexts), len(hop2_contexts),
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
    def _needs_entity_expansion(query: str) -> bool:
        normalized = query.lower()
        trigger_phrases = (
            "line item", "which line", "what line", "grew because", "increased because",
            "decreased because", "fell because", "rose because", "changed because",
            "mentioned in", "because of the", "due to the", "according to the", "cross-document",
            "how much did", "driver of"
        )
        return any(phrase in normalized for phrase in trigger_phrases)

    def _extract_expansion_entities(self, query: str, contexts: list[RetrievedContext]) -> list[str]:
        import re
        stop = {
            "what", "when", "where", "which", "that", "this", "from", "with", "line",
            "item", "statement", "income", "report", "quarterly", "grew", "much", "about",
            "rose", "grow", "total", "net", "during", "after", "over", "because"
        }
        query_tokens = [w for w in re.findall(r"[a-zA-Z]{4,}", query.lower()) if w not in stop]
        known_line_items = [
            "marketing", "operating expenses", "cost of goods sold", "cogs", "rent",
            "utilities", "salaries", "wages", "depreciation", "interest expense",
            "revenue", "coffee & beverage sales", "pastry & food sales", "net income", "gross profit"
        ]

        causal_entities: list[str] = []
        general_entities: list[str] = []

        for ctx in contexts:
            sentences = re.split(r"[\.\n]+", ctx.content)
            for s in sentences:
                s_lower = s.lower()
                has_query_kw = any(qt in s_lower for qt in query_tokens)
                has_growth_kw = any(w in s_lower for w in ["rose", "grew", "increas", "promot", "driver", "fell", "drop"])
                target_list = causal_entities if has_query_kw else (general_entities if has_growth_kw else None)
                if target_list is not None:
                    for item in known_line_items:
                        if item in s_lower and item.title() not in target_list:
                            target_list.append(item.title())
                    matches = re.findall(r"\b([A-Za-z]{4,})\s+(?:spend|expense|sales|cost|revenue)\b", s, re.I)
                    for m in matches:
                        if m.lower() not in stop and m.title() not in target_list:
                            target_list.append(m.title())

        combined = [*causal_entities]
        for e in general_entities:
            if e not in combined:
                combined.append(e)
        return combined

    def _perform_entity_expansion(
        self, query: RetrievalQuery, candidates: list[RetrievedContext]
    ) -> list[RetrievedContext]:
        entities = self._extract_expansion_entities(query.query_text, candidates)
        if not entities:
            return []

        expanded: list[RetrievedContext] = []
        store_id = query.store_id if query.store_id and query.store_id != "default" else None

        for ent in entities:
            vec_res = self.vector_search.search(ent, limit=5, filters=query.filters, store_id=store_id)
            ent_lower = ent.lower()
            matching_vec = [c for c in vec_res if ent_lower in c.content.lower()]
            expanded.extend(matching_vec if matching_vec else vec_res[:2])

            vec_stmt = self.vector_search.search(f"{ent} income statement", limit=2, filters=query.filters, store_id=store_id)
            matching_stmt = [c for c in vec_stmt if ent_lower in c.content.lower()]
            expanded.extend(matching_stmt if matching_stmt else vec_stmt[:1])

            if self.structured_search is not None:
                struct_res = self.structured_search.search(ent, limit=3)
                expanded.extend(struct_res)
            if hasattr(self.graph_search, "search"):
                try:
                    graph_res = (
                        self.graph_search.search(ent, limit=3, store_id=store_id)
                        if store_id
                        else self.graph_search.search(ent, limit=3)
                    )
                    expanded.extend(graph_res)
                except Exception:
                    pass

        return self._deduplicate(expanded)

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