"""Coordinator for dual graph and vector indexing."""

from collections.abc import Iterable
import logging
import time

from src.ingestion.models import FinancialChunk

from .graph_extractor import GraphExtractor
from .graph_store import GraphStore
from .vector_store import VectorStore
from src.retrieval.structured_search import StructuredFinancialStore


logger = logging.getLogger(__name__)


class FinancialIndexer:
    def __init__(
        self,
        vector_store: VectorStore | None = None,
        graph_extractor: GraphExtractor | None = None,
        graph_store: GraphStore | None = None,
        structured_store: StructuredFinancialStore | None = None,
    ):
        self.vector_store = vector_store or VectorStore()
        self.graph_extractor = graph_extractor or GraphExtractor()
        self.graph_store = graph_store or GraphStore()
        self.structured_store = structured_store

    def index(self, chunks: Iterable[FinancialChunk]) -> dict[str, int]:
        started = time.perf_counter()
        chunks = list(chunks)
        vector_count = self.vector_store.upsert(chunks)
        structured_count = self.structured_store.upsert(chunks) if self.structured_store else 0
        entity_count = relation_count = 0
        for chunk in chunks:
            graph_data = self.graph_extractor.extract(chunk)
            entities, relations = self.graph_store.upsert(graph_data)
            entity_count += entities
            relation_count += relations
        result = {
            "chunks_indexed": vector_count,
            "structured_records_indexed": structured_count,
            "entities_indexed": entity_count,
            "relations_indexed": relation_count,
        }
        logger.info(
            "indexing_completed chunks=%d vectors=%d structured=%d entities=%d relations=%d duration_ms=%.1f",
            len(chunks), vector_count, structured_count, entity_count, relation_count,
            (time.perf_counter() - started) * 1000,
        )
        return result

    index_chunks = index