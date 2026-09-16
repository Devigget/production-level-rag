"""FastAPI serving layer for financial chat and document ingestion."""

from __future__ import annotations

import os
import tempfile
import time
from pathlib import Path
from typing import Any

from fastapi import FastAPI, File, HTTPException, UploadFile

from src.ingestion.pipeline import FinancialIngestionPipeline
from src.retrieval.models import HybridSearchResult
from src.api.schemas import ChatRequest, ChatResponse, HealthResponse, UploadResponse
from src.orchestration.graph import build_workflow


class _EmptyRetrievalEngine:
    """Dependency-safe default until vector and graph stores are configured."""

    def retrieve(self, query: str) -> HybridSearchResult:
        return HybridSearchResult(query=query, ranked_contexts=[], total_candidates_evaluated=0)


def _default_llm(_: str) -> str:
    return "I could not find supporting financial context for that question."


def _build_default_workflow() -> Any:
    return build_workflow(_EmptyRetrievalEngine(), _default_llm)


app = FastAPI(title="Financial RAG API", version="1.0.0")
app.state.workflow = _build_default_workflow()
app.state.ingestion_pipeline = FinancialIngestionPipeline()


def _graph_nodes(contexts: list[dict[str, Any]]) -> list[str]:
    nodes: list[str] = []
    for context in contexts:
        metadata = context.get("metadata", {})
        values = metadata.get("graph_nodes_traversed", metadata.get("graph_nodes", []))
        if isinstance(values, str):
            values = [values]
        for value in values:
            if value not in nodes:
                nodes.append(str(value))
    return nodes


@app.get("/api/health", response_model=HealthResponse)
def health() -> HealthResponse:
    return HealthResponse(status="ok", service="financial-rag")


@app.post("/api/chat", response_model=ChatResponse)
def chat(request: ChatRequest) -> ChatResponse:
    started = time.perf_counter()
    result = app.state.workflow.invoke({"raw_query": request.query})
    final_output = result.get("final_output")
    contexts = result.get("retrieved_contexts", [])

    if final_output is None:
        answer = "This request could not be processed safely."
        citations: list[dict[str, Any]] = []
        numerical_fidelity_passed = False
        query = result.get("sanitized_query") or request.query
    else:
        answer = final_output.answer
        citations = [citation.model_dump() for citation in final_output.citations]
        numerical_fidelity_passed = final_output.numerical_fidelity_passed
        query = final_output.query

    return ChatResponse(
        query=query,
        answer=answer,
        citations=citations,
        graph_nodes_traversed=_graph_nodes(contexts),
        numerical_fidelity_passed=numerical_fidelity_passed,
        execution_time_ms=(time.perf_counter() - started) * 1000,
    )


@app.post("/api/upload", response_model=UploadResponse)
def upload(file: UploadFile = File(...)) -> UploadResponse:
    filename = Path(file.filename or "upload").name
    suffix = Path(filename).suffix.lower()
    if suffix not in {".csv", ".jpeg", ".pdf", ".png", ".xlsx"}:
        raise HTTPException(status_code=415, detail="Unsupported file type")

    temporary_path: str | None = None
    try:
        descriptor, temporary_path = tempfile.mkstemp(suffix=suffix)
        with os.fdopen(descriptor, "wb") as temporary_file:
            temporary_file.write(file.file.read())
        result = app.state.ingestion_pipeline.ingest(temporary_path)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Unable to ingest file: {exc}") from exc
    finally:
        if temporary_path is not None:
            os.unlink(temporary_path)
        file.file.close()

    return UploadResponse(
        filename=filename,
        source_file=filename,
        total_chunks=result.total_chunks,
        chunk_types=sorted({chunk.chunk_type for chunk in result.chunks}),
    )
