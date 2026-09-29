"""Neo4j persistence for extracted financial graph data."""

from typing import Any

from neo4j import GraphDatabase

from .config import IndexingSettings
from .graph_extractor import ExtractedGraphData


class GraphStore:
    """Persist graph entities and relations using an injectable Neo4j driver."""

    def __init__(self, settings: IndexingSettings | None = None, driver: Any | None = None):
        self.settings = settings or IndexingSettings()
        self.driver = driver or GraphDatabase.driver(
            self.settings.neo4j_uri,
            auth=(self.settings.neo4j_user, self.settings.neo4j_password),
        )

    def upsert(self, graph_data: ExtractedGraphData) -> tuple[int, int]:
        with self.driver.session(database=self.settings.neo4j_database) as session:
            for entity in graph_data.entities:
                props = entity.properties or {}
                session.run(
                    """MERGE (node:FinancialEntity {name: $name, category: $category})
                    SET node += $properties
                    FOREACH (_ IN CASE WHEN $category = 'Metric' THEN [1] ELSE [] END | SET node:Metric)
                    FOREACH (_ IN CASE WHEN $category = 'Quarter' THEN [1] ELSE [] END | SET node:Quarter)""",
                    name=entity.name,
                    category=entity.category,
                    properties=props,
                )
            for relation in graph_data.relations:
                session.run(
                    """MATCH (source:FinancialEntity {name: $source})
                    MATCH (target:FinancialEntity {name: $target})
                    MERGE (source)-[edge:RELATED {type: $relationship_type}]->(target)
                    SET edge += $properties""",
                    source=relation.source_entity,
                    target=relation.target_entity,
                    relationship_type=relation.relationship_type,
                    properties=relation.properties,
                )
        return len(graph_data.entities), len(graph_data.relations)

    upsert_graph = upsert

    def register_document(
        self,
        store_id: str,
        store_name: str,
        doc_id: str,
        filename: str,
        file_type: str | None = None,
        total_chunks: int | None = None,
        chunk_types: list[str] | None = None,
        uploaded_at: str | None = None,
    ) -> None:
        """Ensure Store, Document, and HAS_DOCUMENT nodes exist in Neo4j."""
        with self.driver.session(database=self.settings.neo4j_database) as session:
            session.run(
                """
                MERGE (s:Store {id: $store_id})
                ON CREATE SET s.name = $store_name
                MERGE (d:Document {id: $doc_id})
                SET d.filename = $filename,
                    d.store_id = $store_id,
                    d.file_type = coalesce($file_type, d.file_type),
                    d.total_chunks = coalesce($total_chunks, d.total_chunks),
                    d.chunk_types = coalesce($chunk_types, d.chunk_types),
                    d.uploaded_at = coalesce($uploaded_at, d.uploaded_at)
                MERGE (s)-[:HAS_DOCUMENT]->(d)
                """,
                store_id=store_id,
                store_name=store_name,
                doc_id=doc_id,
                filename=filename,
                file_type=file_type,
                total_chunks=total_chunks,
                chunk_types=chunk_types,
                uploaded_at=uploaded_at,
            )

    def link_unstructured_entities(
        self,
        store_id: str,
        doc_id: str,
        filename: str,
    ) -> None:
        """Scope extracted financial entities and relations to the store and document."""
        with self.driver.session(database=self.settings.neo4j_database) as session:
            session.run(
                """
                MATCH (d:Document {id: $doc_id})
                MATCH (s:Store {id: $store_id})
                MATCH (f:FinancialEntity {name: $filename})-[r:RELATED]->(target:FinancialEntity)
                SET target.store_id = $store_id,
                    r.store_id = $store_id,
                    r.doc_id = $doc_id
                MERGE (s)-[:CONTAINS]->(target)
                FOREACH (_ IN CASE WHEN r.type = 'REPORTED_METRIC' THEN [1] ELSE [] END |
                    MERGE (d)-[rel:REPORTED_METRIC]->(target)
                    SET rel += properties(r), rel.store_id = $store_id, rel.doc_id = $doc_id
                    MERGE (d)-[:DEFINES]->(target)
                )
                FOREACH (_ IN CASE WHEN r.type = 'MENTIONS' THEN [1] ELSE [] END |
                    MERGE (d)-[rel:MENTIONS]->(target)
                    SET rel += properties(r), rel.store_id = $store_id, rel.doc_id = $doc_id
                )
                """,
                store_id=store_id,
                doc_id=doc_id,
                filename=filename,
            )
            session.run(
                """
                MATCH (target:FinancialEntity)-[val:RELATED]->(q)
                WHERE val.source_file = $filename
                SET target.store_id = $store_id,
                    val.store_id = $store_id,
                    val.doc_id = $doc_id,
                    q.store_id = $store_id
                """,
                store_id=store_id,
                doc_id=doc_id,
                filename=filename,
            )

    def close(self) -> None:
        self.driver.close()