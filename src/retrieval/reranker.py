"""Cross-encoder reranking with an injectable model for tests and deployments."""

import os
from typing import Any, Sequence

from .models import RetrievedContext


class CrossEncoderReranker:
    def __init__(self, model: Any | None = None, model_name: str = "BAAI/bge-reranker-base"):
        self.model = model
        self.model_name = model_name

    def _get_model(self) -> Any:
        if self.model is None:
            if os.getenv("RERANKER_ENABLED", "false").lower() not in {"1", "true", "yes"}:
                return None
            try:
                from sentence_transformers import CrossEncoder
            except ImportError:
                return None
            self.model = CrossEncoder(self.model_name)
        return self.model

    def rerank(
        self, query: str, contexts: Sequence[RetrievedContext], top_n: int | None = None
    ) -> list[RetrievedContext]:
        if not contexts:
            return []
        model = self._get_model()
        if model is None:
            ranked = [
                context.model_copy(update={"rerank_score": context.initial_score})
                for context in contexts
            ]
            ranked.sort(key=lambda context: context.rerank_score or 0.0, reverse=True)
            return ranked[:top_n] if top_n is not None else ranked
        pairs = [(query, context.content) for context in contexts]
        scores = model.predict(pairs)
        ranked = [context.model_copy(update={"rerank_score": float(score)}) for context, score in zip(contexts, scores)]
        ranked.sort(key=lambda context: context.rerank_score or 0.0, reverse=True)
        return ranked[:top_n] if top_n is not None else ranked


Reranker = CrossEncoderReranker