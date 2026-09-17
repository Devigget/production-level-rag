"""FastAPI serving layer for financial chat and document ingestion."""

from __future__ import annotations

import json
import os
import tempfile
import time
from pathlib import Path
from typing import Any

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.responses import StreamingResponse

from src.ingestion.pipeline import FinancialIngestionPipeline
from src.indexing.config import IndexingSettings
from src.retrieval.models import HybridSearchResult, RetrievalQuery
from src.retrieval.engine import HybridRetrievalEngine
from src.retrieval.graph_search import GraphSearcher
from src.retrieval.vector_search import VectorSearcher
from src.api.schemas import ChatRequest, ChatResponse, HealthResponse, UploadResponse
from src.orchestration.graph import build_workflow, create_llm_invoker


class _EmptyRetrievalEngine:
    """Dependency-safe default until vector and graph stores are configured."""

    def retrieve(self, query: RetrievalQuery | str) -> HybridSearchResult:
        query_text = query.query_text if isinstance(query, RetrievalQuery) else query
        return HybridSearchResult(query=query_text, ranked_contexts=[], total_candidates_evaluated=0)


def _build_default_workflow() -> Any:
    settings = IndexingSettings()
    if settings.qdrant_url == ":memory:":
        return build_workflow(_EmptyRetrievalEngine(), create_llm_invoker())
    try:
        retrieval_engine = HybridRetrievalEngine(
            VectorSearcher(settings=settings),
            GraphSearcher(settings=settings),
        )
    except Exception:
        retrieval_engine = _EmptyRetrievalEngine()
    return build_workflow(retrieval_engine, create_llm_invoker())


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
    result = app.state.workflow.invoke(
        {
            "raw_query": request.query,
            "top_n": request.top_n,
            "enable_graph_expansion": request.enable_graph_expansion,
        }
    )
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


@app.post("/api/chat/stream")
def chat_stream(request: ChatRequest) -> StreamingResponse:
    """Stream a guarded answer as SSE events while preserving final citations."""
    started = time.perf_counter()
    result = app.state.workflow.invoke(
        {
            "raw_query": request.query,
            "top_n": request.top_n,
            "enable_graph_expansion": request.enable_graph_expansion,
        }
    )
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

    payload = {
        "query": query,
        "citations": citations,
        "graph_nodes_traversed": _graph_nodes(contexts),
        "numerical_fidelity_passed": numerical_fidelity_passed,
        "execution_time_ms": (time.perf_counter() - started) * 1000,
    }

    def events():
        for offset in range(0, len(answer), 24):
            yield f"event: token\ndata: {json.dumps({'text': answer[offset:offset + 24]})}\n\n"
        yield f"event: complete\ndata: {json.dumps({'answer': answer, **payload})}\n\n"

    return StreamingResponse(
        events(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


from src.indexing.indexer import FinancialIndexer

indexer = FinancialIndexer() if IndexingSettings().qdrant_url != ":memory:" else None

@app.post("/api/upload", response_model=UploadResponse)
def upload(file: UploadFile = File(...)) -> UploadResponse:
    filename = Path(file.filename or "upload").name
    suffix = Path(filename).suffix.lower()
    if suffix not in {".csv", ".docx", ".jpeg", ".jpg", ".pdf", ".png", ".txt", ".xlsx"}:
        raise HTTPException(status_code=415, detail="Unsupported file type")

    temporary_path: str | None = None
    try:
        descriptor, temporary_path = tempfile.mkstemp(suffix=suffix)
        with os.fdopen(descriptor, "wb") as temporary_file:
            temporary_file.write(file.file.read())
        result = app.state.ingestion_pipeline.ingest(temporary_path)
        for chunk in result.chunks:
            sheet_name = chunk.metadata.get("sheet_name", "document")
            chunk.chunk_id = f"{filename}:{sheet_name}"
            chunk.source_file = filename
        if indexer is not None:
            indexer.index(result.chunks)
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
