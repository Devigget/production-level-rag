"""Qdrant-backed dense vector storage for financial chunks."""

import hashlib
import math
import uuid
from collections.abc import Iterable, Sequence
from typing import Any

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
                payload={"chunk": chunk.model_dump()},
            )
            for chunk, vector in zip(chunks, vectors)
        ]
        self.client.upsert(
            collection_name=self.settings.qdrant_collection,
            points=points,
        )
        return len(points)

    upsert_chunks = upsert

    def search(self, query: str, limit: int = 5) -> list[Any]:
        vector = self._embed([query])[0]
        if hasattr(self.client, "query_points"):
            response = self.client.query_points(
                collection_name=self.settings.qdrant_collection,
                query=vector,
                limit=limit,
                with_payload=True,
            )
            return list(response.points)
        return self.client.search(
            collection_name=self.settings.qdrant_collection,
            query_vector=vector,
            limit=limit,
            with_payload=True,
        )