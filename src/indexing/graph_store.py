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
                session.run(
                    "MERGE (node:FinancialEntity {name: $name, category: $category})",
                    name=entity.name,
                    category=entity.category,
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

    def close(self) -> None:
        self.driver.close()