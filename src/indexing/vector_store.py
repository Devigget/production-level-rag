"""Qdrant-backed dense vector storage for financial chunks."""

import hashlib
import math
import uuid
from typing import Any, Iterable, Sequence

from qdrant_client import QdrantClient, models

from src.ingestion.models import FinancialChunk

from .config import IndexingSettings


class HashEmbedder:
    """Small deterministic embedder used when no model is injected."""

    def __init__(self, dimension: int):
        self.dimension = dimension

    def encode(self, texts: Sequence[str], **_: Any) -> list[list[float]]:
        vectors = []
        for text in texts:
            values = [0.0] * self.dimension
            for token in text.lower().split():
                digest = hashlib.sha256(token.encode("utf-8")).digest()
                index = int.from_bytes(digest[:4], "big") % self.dimension
                values[index] += 1.0
            norm = math.sqrt(sum(value * value for value in values)) or 1.0
            vectors.append([value / norm for value in values])
        return vectors


class VectorStore:
    """Store and search ``FinancialChunk`` embeddings in Qdrant."""

    def __init__(
        self,
        settings: IndexingSettings | None = None,
        client: QdrantClient | None = None,
        embedder: Any | None = None,
    ):
        self.settings = settings or IndexingSettings()
        self.client = client or self._create_client()
        self.embedder = embedder or HashEmbedder(self.settings.embedding_dimension)
        self._ensure_collection()

    def _create_client(self) -> QdrantClient:
        if self.settings.qdrant_url == ":memory:":
            return QdrantClient(location=":memory:")
        return QdrantClient(
            url=self.settings.qdrant_url,
            api_key=self.settings.qdrant_api_key,
        )

    def _ensure_collection(self) -> None:
        if not self.client.collection_exists(self.settings.qdrant_collection):
            self.client.create_collection(
                collection_name=self.settings.qdrant_collection,
                vectors_config=models.VectorParams(
                    size=self.settings.embedding_dimension,
                    distance=models.Distance.COSINE,
                ),
            )

    def _embed(self, texts: Sequence[str]) -> list[list[float]]:
        encoded = self.embedder.encode(texts)
        return encoded.tolist() if hasattr(encoded, "tolist") else list(encoded)

    @staticmethod
    def _point_id(chunk_id: str) -> str:
        return str(uuid.uuid5(uuid.NAMESPACE_URL, chunk_id))

    def upsert(self, chunks: Iterable[FinancialChunk]) -> int:
        chunks = list(chunks)
        if not chunks:
            return 0
        vectors = self._embed([chunk.content for chunk in chunks])
        points = [
            models.PointStruct(
                id=self._point_id(chunk.chunk_id),
                vector=vector,
                payload={
                    "chunk": chunk.model_dump(),
                    "store_id": getattr(chunk, "store_id", "default") or "default",
                    "doc_id": getattr(chunk, "doc_id", "") or "",
                },
            )
            for chunk, vector in zip(chunks, vectors)
        ]
        self.client.upsert(
            collection_name=self.settings.qdrant_collection,
            points=points,
        )
        return len(points)

    upsert_chunks = upsert

    def search(self, query: str, limit: int = 5, store_id: str | None = None) -> list[Any]:
        vector = self._embed([query])[0]
        query_filter = None
        if store_id:
            query_filter = models.Filter(
                should=[
                    models.FieldCondition(key="store_id", match=models.MatchValue(value=store_id)),
                    models.FieldCondition(key="chunk.store_id", match=models.MatchValue(value=store_id)),
                ]
            )

        kwargs: dict[str, Any] = {
            "collection_name": self.settings.qdrant_collection,
            "limit": limit * 2 if store_id else limit,
            "with_payload": True,
        }
        if query_filter:
            kwargs["query_filter"] = query_filter

        if hasattr(self.client, "query_points"):
            try:
                response = self.client.query_points(
                    query=vector,
                    **kwargs,
                )
                points = list(response.points)
            except Exception:
                kwargs.pop("query_filter", None)
                response = self.client.query_points(
                    query=vector,
                    **kwargs,
                )
                points = list(response.points)
        else:
            try:
                points = list(self.client.search(
                    query_vector=vector,
                    **kwargs,
                ))
            except Exception:
                kwargs.pop("query_filter", None)
                points = list(self.client.search(
                    query_vector=vector,
                    **kwargs,
                ))

        if store_id:
            points = [
                p for p in points
                if getattr(p, "payload", {}).get("store_id") == store_id
                or getattr(p, "payload", {}).get("chunk", {}).get("store_id") == store_id
            ][:limit]

        return points