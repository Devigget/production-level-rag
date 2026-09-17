from unittest.mock import MagicMock

from qdrant_client import QdrantClient

from src.indexing.config import IndexingSettings
from src.indexing.graph_extractor import GraphExtractor
from src.indexing.graph_store import GraphStore
from src.indexing.indexer import FinancialIndexer
from src.indexing.vector_store import VectorStore
from src.ingestion.models import FinancialChunk


def sample_chunk() -> FinancialChunk:
    return FinancialChunk(
        chunk_id="pnl:sample_pnl",
        content=(
            "| Line Item | Q1_2025 | Q2_2025 |\n"
            "| --- | --- | --- |\n"
            "| Revenue | $1200000 | $1450000 |"
        ),
        chunk_type="table",
        source_file="sample_pnl.csv",
        metadata={"sheet_name": "sample_pnl"},
    )


def test_vector_store_uses_in_memory_qdrant():
    settings = IndexingSettings(qdrant_url=":memory:", embedding_dimension=32)
    store = VectorStore(settings=settings, client=QdrantClient(location=":memory:"))

    assert store.upsert([sample_chunk()]) == 1
    results = store.search("Revenue", limit=1)

    assert len(results) == 1
    assert results[0].payload["chunk"]["chunk_id"] == "pnl:sample_pnl"


def test_graph_extractor_extracts_metrics_and_quarters():
    extracted = GraphExtractor().extract(sample_chunk())

    assert {entity.name for entity in extracted.entities} >= {
        "sample_pnl.csv",
        "Revenue",
        "Q1_2025",
    }
    assert any(
        relation.relationship_type == "HAS_VALUE"
        and relation.source_entity == "Revenue"
        for relation in extracted.relations
    )


def test_graph_store_uses_mocked_neo4j_driver():
    driver = MagicMock()
    session = driver.session.return_value.__enter__.return_value
    graph_data = GraphExtractor().extract(sample_chunk())
    store = GraphStore(settings=IndexingSettings(), driver=driver)

    entity_count, relation_count = store.upsert(graph_data)

    assert entity_count == len(graph_data.entities)
    assert relation_count == len(graph_data.relations)
    assert session.run.call_count == entity_count + relation_count
    assert session.run.call_args_list[0].args[0].startswith("MERGE (node:FinancialEntity")


def test_indexer_combines_vector_and_graph_layers():
    vector_store = VectorStore(
        settings=IndexingSettings(qdrant_url=":memory:", embedding_dimension=32),
        client=QdrantClient(location=":memory:"),
    )
    driver = MagicMock()
    graph_store = GraphStore(settings=IndexingSettings(), driver=driver)
    result = FinancialIndexer(vector_store=vector_store, graph_store=graph_store).index(
        [sample_chunk()]
    )

    assert result["chunks_indexed"] == 1
    assert result["entities_indexed"] >= 2
    assert result["relations_indexed"] >= 2