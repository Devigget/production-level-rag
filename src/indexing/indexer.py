"""Coordinator for dual graph and vector indexing."""

from collections.abc import Iterable

from src.ingestion.models import FinancialChunk

from .graph_extractor import GraphExtractor
from .graph_store import GraphStore
from .vector_store import VectorStore


class FinancialIndexer:
    def __init__(
        self,
        vector_store: VectorStore | None = None,
        graph_extractor: GraphExtractor | None = None,
        graph_store: GraphStore | None = None,
    ):
        self.vector_store = vector_store or VectorStore()
        self.graph_extractor = graph_extractor or GraphExtractor()
        self.graph_store = graph_store or GraphStore()

    def index(self, chunks: Iterable[FinancialChunk]) -> dict[str, int]:
        chunks = list(chunks)
        vector_count = self.vector_store.upsert(chunks)
        entity_count = relation_count = 0
        for chunk in chunks:
            graph_data = self.graph_extractor.extract(chunk)
            entities, relations = self.graph_store.upsert(graph_data)
            entity_count += entities
            relation_count += relations
        return {
            "chunks_indexed": vector_count,
            "entities_indexed": entity_count,
            "relations_indexed": relation_count,
        }

    index_chunks = index