"""Entity-directed graph retrieval over Neo4j."""

from typing import Any

from neo4j import GraphDatabase

from src.indexing.config import IndexingSettings

from .models import RetrievedContext


GRAPH_QUERY = """
MATCH (entity:FinancialEntity)
WHERE toLower($query_text) CONTAINS toLower(entity.name)
MATCH path=(entity)-[*1..2]-(connected:FinancialEntity)
UNWIND relationships(path) AS relation
WITH entity, relation, connected, length(path) AS hops
WHERE relation.chunk_id IS NOT NULL
RETURN relation.chunk_id AS id,
       coalesce(relation.content, relation.value, connected.name) AS content,
       1.0 / hops AS score,
       {entity: entity.name, connected_entity: connected.name, hops: hops,
    source_file: relation.source_file} AS metadata
ORDER BY score DESC
LIMIT $limit
"""


class GraphSearcher:
    def __init__(self, settings: IndexingSettings | None = None, driver: Any | None = None):
        self.settings = settings or IndexingSettings()
        self.driver = driver or GraphDatabase.driver(
            self.settings.neo4j_uri,
            auth=(self.settings.neo4j_user, self.settings.neo4j_password),
        )

    def search(self, query: str, limit: int = 10) -> list[RetrievedContext]:
        if limit <= 0:
            return []
        with self.driver.session(database=self.settings.neo4j_database) as session:
            records = session.run(GRAPH_QUERY, query_text=query, limit=limit)
            return [self._to_context(record) for record in records]

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