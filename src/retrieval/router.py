"""Hybrid Query Router for store-scoped vector, graph traversal, and hybrid retrieval."""

from __future__ import annotations

import logging
import re
from typing import Any, Callable, Dict, List, Optional, Tuple

from .models import RetrievedContext

logger = logging.getLogger(__name__)

ROUTE_VECTOR = "VECTOR_SEARCH"
ROUTE_GRAPH = "GRAPH_TRAVERSAL"
ROUTE_HYBRID = "HYBRID"


class QueryRouter:
    """Classify query intent and route to Vector, Graph Traversal, or Hybrid search."""

    def __init__(self, llm_invoker: Optional[Callable[[str], str]] = None):
        self.llm_invoker = llm_invoker

    def route_query(self, query: str) -> Tuple[str, str]:
        """Return (route_name, reasoning)."""
        normalized = query.lower()

        # Check for quantitative calculations, comparisons, multi-hop entity relationships
        has_quantitative = any(
            term in normalized
            for term in (
                "total", "sum", "average", "avg", "margin", "ebitda", "growth", "grew", "grow", "increase",
                "compare", "difference", "trend", "ratio", "q1", "q2", "q3", "q4",
                "2024", "2025", "2026", "highest", "lowest", "calculate", "percentage",
                "balance", "revenue", "profit", "net income", "expense", "how much", "line item", "income statement"
            )
        )
        has_relationship = any(
            term in normalized
            for term in (
                "who approved", "which vendor", "which department", "related to",
                "connected to", "hierarchy", "trace", "supporting chain", "belongs to"
            )
        )
        has_narrative = any(
            term in normalized
            for term in (
                "explain", "why", "note", "policy", "clause", "description",
                "summary", "detail", "overview", "background", "reason", "commentary",
                "report", "promotion", "cause", "mentioned", "because of"
            )
        )

        if (has_quantitative or has_relationship) and has_narrative:
            return ROUTE_HYBRID, "Query requires both quantitative data from tables and qualitative explanations from text notes."
        if has_relationship or (has_quantitative and ("compare" in normalized or "growth" in normalized or "trend" in normalized or "q1" in normalized and "q2" in normalized)):
            return ROUTE_GRAPH, "Query requires multi-hop entity relationships or cross-quarter quantitative traversal."
        if has_quantitative:
            return ROUTE_HYBRID, "Query seeks quantitative metrics with grounded context."

        # If purely semantic / descriptive lookup
        return ROUTE_VECTOR, "Descriptive, textual, or semantic policy lookup."

    def generate_store_cypher(self, query: str, store_id: str) -> Tuple[str, dict[str, Any]]:
        """Generate safe, store-bounded Cypher traversal query for GRAPH_TRAVERSAL."""
        words = re.findall(r"\b[A-Za-z0-9_]{3,}\b", query)
        stop_words = {"what", "when", "where", "which", "show", "tell", "much", "were", "with", "from", "that", "this"}
        keywords = [w for w in words if w.lower() not in stop_words]
        keyword = keywords[0] if keywords else ""

        cypher = """
        MATCH (s:Store {id: $store_id})-[:CONTAINS]->(e)
        WHERE ($keyword = '' OR toLower(e.name) CONTAINS toLower($keyword))
        OPTIONAL MATCH (e)-[r]->(t)
        WHERE r.store_id = $store_id OR r.store_id IS NULL
        RETURN e.name AS entity, type(r) AS relationship, t.name AS target, r.value AS value
        LIMIT 25
        """
        params = {"store_id": store_id, "keyword": keyword}
        return cypher, params
