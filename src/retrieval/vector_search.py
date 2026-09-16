"""Dense retrieval over the Qdrant collection created by the indexing layer."""

from typing import Any

from qdrant_client import QdrantClient

from src.indexing.config import IndexingSettings
from src.indexing.vector_store import HashEmbedder

from .models import RetrievedContext


class VectorSearcher:
    def __init__(
        self,
        settings: IndexingSettings | None = None,
        client: QdrantClient | None = None,
        embedder: Any | None = None,
    ):
        self.settings = settings or IndexingSettings()
        if client is not None:
            self.client = client
        elif self.settings.qdrant_url == ":memory:":
            self.client = QdrantClient(location=":memory:")
        else:
            self.client = QdrantClient(
                url=self.settings.qdrant_url, api_key=self.settings.qdrant_api_key
            )
        self.embedder = embedder or HashEmbedder(self.settings.embedding_dimension)

    def _embed(self, text: str) -> list[float]:
        encoded = self.embedder.encode([text])
        encoded = encoded.tolist() if hasattr(encoded, "tolist") else encoded
        return list(encoded[0])

    def search(
        self, query: str, limit: int = 10, filters: dict[str, Any] | None = None
    ) -> list[RetrievedContext]:
        if limit <= 0:
            return []
        kwargs: dict[str, Any] = {
            "collection_name": self.settings.qdrant_collection,
            "query": self._embed(query),
            "limit": limit,
            "with_payload": True,
        }
        if filters:
            kwargs["query_filter"] = filters
        if hasattr(self.client, "query_points"):
            response = self.client.query_points(**kwargs)
            points = response.points
        else:
            kwargs["query_vector"] = kwargs.pop("query")
            points = self.client.search(**kwargs)
        return [self._to_context(point) for point in points]

    @staticmethod
    def _to_context(point: Any) -> RetrievedContext:
        payload = point.get("payload", {}) if isinstance(point, dict) else getattr(point, "payload", {}) or {}
        chunk = payload.get("chunk", payload)
        if hasattr(chunk, "model_dump"):
            chunk = chunk.model_dump()
        score = point.get("score", 0.0) if isinstance(point, dict) else getattr(point, "score", 0.0)
        point_id = point.get("id") if isinstance(point, dict) else getattr(point, "id", None)
        return RetrievedContext(
            id=str(chunk.get("chunk_id", point_id)),
            content=str(chunk.get("content", "")),
            source_type="vector_chunk",
            initial_score=float(score or 0.0),
            metadata={
                **dict(chunk.get("metadata", {})),
                "source_file": chunk.get("source_file", ""),
            },
        )


VectorSearch = VectorSearcher