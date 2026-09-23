"""Cross-encoder reranking with an injectable model for tests and deployments."""

import os
from typing import Any, Sequence

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

from .models import RetrievedContext


class CrossEncoderReranker:
    def __init__(
        self,
        model: Any | None = None,
        model_name: str | None = None,
        max_length: int | None = None,
        device: str | None = None,
        use_fp16: bool | None = None,
        local_files_only: bool | None = None,
    ):
        self.model = model
        self.model_name = (
            model_name
            or os.getenv("RERANKER_MODEL_PATH")
            or os.getenv("RERANKER_MODEL_NAME")
            or os.getenv("RERANKER_MODEL")
            or ("/models/bge-reranker-base" if os.path.exists("/models/bge-reranker-base") else "cross-encoder/ms-marco-MiniLM-L-6-v2")
        )
        if max_length is not None:
            self.max_length = max_length
        else:
            env_max_len = os.getenv("RERANKER_MAX_LENGTH")
            self.max_length = int(env_max_len) if env_max_len and env_max_len.isdigit() else 256

        self.device = self._resolve_device(device)

        if use_fp16 is not None:
            self.use_fp16 = use_fp16
        else:
            env_fp16 = os.getenv("RERANKER_USE_FP16")
            if env_fp16 is not None:
                self.use_fp16 = env_fp16.lower() in {"1", "true", "yes"}
            else:
                self.use_fp16 = self.device == "cuda"

        if local_files_only is not None:
            self.local_files_only = local_files_only
        else:
            self.local_files_only = os.getenv("RERANKER_LOCAL_FILES_ONLY", "false").lower() in {
                "1", "true", "yes"
            }

    @staticmethod
    def _resolve_device(device: str | None) -> str:
        target = device or os.getenv("RERANKER_DEVICE", "auto")
        if target and target.lower() != "auto":
            return target.lower()
        try:
            import torch
            if torch.cuda.is_available():
                return "cuda"
            if hasattr(torch.backends, "mps") and torch.backends.mps.is_available():
                return "mps"
        except ImportError:
            pass
        return "cpu"

    def _get_model(self) -> Any:
        if self.model is None:
            if os.getenv("RERANKER_ENABLED", "false").lower() not in {"1", "true", "yes"}:
                return None
            try:
                from sentence_transformers import CrossEncoder
            except ImportError:
                return None

            kwargs: dict[str, Any] = {
                "max_length": self.max_length,
                "device": self.device,
            }
            if self.local_files_only:
                kwargs["local_files_only"] = True
            if self.use_fp16 and self.device == "cuda":
                try:
                    import torch
                    kwargs["model_kwargs"] = {"torch_dtype": torch.float16}
                except ImportError:
                    pass

            model_target = self.model_name
            if model_target == "/models/bge-reranker-base" and not os.path.exists(model_target):
                host_path = os.getenv(
                    "RERANKER_HOST_MODEL_PATH",
                    r"C:\Users\VigneshPandurangGaun\OneDrive - McLaren Strategic Solutions US Inc\Documents\models\Reranker models",
                )
                if host_path and os.path.exists(host_path):
                    model_target = host_path

            self.model = CrossEncoder(model_target, **kwargs)
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