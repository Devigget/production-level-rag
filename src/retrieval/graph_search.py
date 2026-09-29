"""Entity-directed and store-scoped graph retrieval over Neo4j."""

from typing import Any, Optional

from neo4j import GraphDatabase

from src.indexing.config import IndexingSettings

from .models import RetrievedContext


GRAPH_QUERY = """
MATCH (entity)
WHERE (entity:FinancialEntity OR entity:Metric OR entity:Quarter)
  AND (
    toLower($query_text) CONTAINS toLower(entity.name)
    OR (toLower(entity.name) CONTAINS 'revenue' AND toLower($query_text) CONTAINS 'revenue')
    OR (toLower(entity.name) CONTAINS 'income' AND toLower($query_text) CONTAINS 'income')
    OR (toLower(entity.name) CONTAINS 'profit' AND toLower($query_text) CONTAINS 'profit')
    OR (
      (entity:Quarter OR entity.category = 'Quarter')
      AND ($query_text =~ '(?i).*(quarter|strongest|highest|best|top|q1|q2|q3|q4).*')
    )
  )
MATCH path=(entity)-[*1..2]-(connected)
UNWIND relationships(path) AS relation
WITH entity, relation, connected, length(path) AS hops
WHERE relation.chunk_id IS NOT NULL OR relation.value IS NOT NULL OR relation.numeric_value IS NOT NULL
RETURN coalesce(relation.chunk_id, entity.id, toString(id(entity))) AS id,
       coalesce(relation.content, relation.value, connected.name, entity.name) AS content,
       1.0 / hops AS score,
       {entity: entity.name, connected_entity: connected.name, hops: hops,
        graph_nodes_traversed: [entity.name, connected.name],
        source_file: relation.source_file,
        numeric_value: relation.numeric_value} AS metadata
ORDER BY
  CASE WHEN toLower($query_text) =~ '(?i).*(strongest|highest|top|best|max).*' AND relation.numeric_value IS NOT NULL
       THEN relation.numeric_value ELSE 0 END DESC,
  score DESC
LIMIT $limit
"""

STORE_SCOPED_GRAPH_QUERY = """
MATCH (entity)
WHERE (entity:FinancialEntity OR entity:Metric OR entity:Quarter)
  AND (entity.store_id = $store_id OR ($store_id = 'default' AND entity.store_id IS NULL))
  AND (
    toLower($query_text) CONTAINS toLower(entity.name)
    OR (toLower(entity.name) CONTAINS 'revenue' AND toLower($query_text) CONTAINS 'revenue')
    OR (toLower(entity.name) CONTAINS 'income' AND toLower($query_text) CONTAINS 'income')
    OR (toLower(entity.name) CONTAINS 'profit' AND toLower($query_text) CONTAINS 'profit')
    OR (
      (entity:Quarter OR entity.category = 'Quarter')
      AND ($query_text =~ '(?i).*(quarter|strongest|highest|best|top|q1|q2|q3|q4).*')
    )
  )
MATCH path=(entity)-[*1..2]-(connected)
WHERE (connected.store_id = $store_id OR ($store_id = 'default' AND connected.store_id IS NULL))
UNWIND relationships(path) AS relation
WITH entity, relation, connected, length(path) AS hops
WHERE (relation.store_id = $store_id OR ($store_id = 'default' AND relation.store_id IS NULL))
RETURN coalesce(relation.chunk_id, entity.id, toString(id(entity))) AS id,
       coalesce(relation.content, relation.value, connected.name, entity.name) AS content,
       1.0 / hops AS score,
       {entity: entity.name, connected_entity: connected.name, hops: hops,
        graph_nodes_traversed: [entity.name, connected.name],
        source_file: relation.source_file,
        numeric_value: relation.numeric_value,
        store_id: $store_id} AS metadata
ORDER BY
  CASE WHEN toLower($query_text) =~ '(?i).*(strongest|highest|top|best|max).*' AND relation.numeric_value IS NOT NULL
       THEN relation.numeric_value ELSE 0 END DESC,
  score DESC
LIMIT $limit
"""


class GraphSearcher:
    def __init__(self, settings: IndexingSettings | None = None, driver: Any | None = None):
        self.settings = settings or IndexingSettings()
        self.driver = driver or GraphDatabase.driver(
            self.settings.neo4j_uri,
            auth=(self.settings.neo4j_user, self.settings.neo4j_password),
        )

    def search(
        self, query: str, limit: int = 10, store_id: Optional[str] = None
    ) -> list[RetrievedContext]:
        if limit <= 0:
            return []
        cypher = STORE_SCOPED_GRAPH_QUERY if store_id else GRAPH_QUERY
        params = {"query_text": query, "limit": limit}
        if store_id:
            params["store_id"] = store_id

        with self.driver.session(database=self.settings.neo4j_database) as session:
            records = session.run(cypher, **params)
            return [self._to_context(record) for record in records]

    def run_cypher_traversal(
        self, cypher: str, params: dict[str, Any]
    ) -> list[RetrievedContext]:
        """Execute parameterized Cypher from query router and convert to RetrievedContext."""
        contexts: list[RetrievedContext] = []
        try:
            with self.driver.session(database=self.settings.neo4j_database) as session:
                records = session.run(cypher, **params)
                for rec in records:
                    rec_dict = dict(rec)
                    nodes = [str(v) for k, v in rec_dict.items() if "name" in k or "entity" in k]
                    content_str = " | ".join(f"{k}: {v}" for k, v in rec_dict.items() if v is not None)
                    contexts.append(
                        RetrievedContext(
                            id=f"graph-query-{len(contexts)}",
                            content=content_str,
                            source_type="graph_traversal",
                            initial_score=1.0,
                            metadata={
                                "graph_nodes_traversed": nodes,
                                "raw_result": rec_dict,
                                "store_id": params.get("store_id", "default"),
                            },
                        )
                    )
        except Exception as exc:
            import logging
            logging.getLogger(__name__).warning("Cypher traversal execution error: %s", exc)
        return contexts

    @staticmethod
    def _to_context(record: Any) -> RetrievedContext:
        data = dict(record) if not isinstance(record, dict) else record
        return RetrievedContext(
            id=str(data.get("id", "")),
            content=str(data.get("content", "")),
            source_type="graph_subgraph",
            initial_score=float(data.get("score", 0.0) or 0.0),
            metadata=dict(data.get("metadata", {}) or {}),
        )

    def close(self) -> None:
        self.driver.close()


GraphSearch = GraphSearcher