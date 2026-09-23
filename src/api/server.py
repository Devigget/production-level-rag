"""FastAPI serving layer for financial chat and document ingestion."""

from __future__ import annotations

import json
import logging
import os
import tempfile
import time
import asyncio
from pathlib import Path
from typing import Any

from src.observability import configure_logging, configure_telemetry

configure_telemetry()

from fastapi import FastAPI, File, HTTPException, Query, UploadFile
from fastapi.responses import Response, StreamingResponse

from src.ingestion.pipeline import FinancialIngestionPipeline
from src.indexing.config import IndexingSettings
from src.retrieval.models import HybridSearchResult, RetrievalQuery
from src.retrieval.engine import HybridRetrievalEngine
from src.retrieval.graph_search import GraphSearcher
from src.retrieval.structured_search import StructuredFinancialStore
from src.retrieval.vector_search import VectorSearcher
from src.api.schemas import ChatRequest, ChatResponse, HealthResponse, UploadResponse
from src.orchestration.graph import build_workflow, create_llm_invoker
configure_logging()
logger = logging.getLogger(__name__)


class _EmptyRetrievalEngine:
    """Dependency-safe default until vector and graph stores are configured."""

    def retrieve(self, query: RetrievalQuery | str) -> HybridSearchResult:
        query_text = query.query_text if isinstance(query, RetrievalQuery) else query
        return HybridSearchResult(query=query_text, ranked_contexts=[], total_candidates_evaluated=0)


class _EmptySearch:
    def search(self, *_args: Any, **_kwargs: Any) -> list[Any]:
        return []


structured_store = StructuredFinancialStore()


def _build_default_workflow() -> Any:
    settings = IndexingSettings()
    if settings.qdrant_url == ":memory:":
        logger.info("retrieval_backend mode=in_memory")
        retrieval_engine = HybridRetrievalEngine(
            _EmptySearch(), _EmptySearch(), structured_search=structured_store
        )
        return build_workflow(retrieval_engine, create_llm_invoker())
    try:
        retrieval_engine = HybridRetrievalEngine(
            VectorSearcher(settings=settings),
            GraphSearcher(settings=settings),
            structured_search=structured_store,
        )
    except Exception:
        logger.exception("retrieval_backend_initialization_failed")
        retrieval_engine = _EmptyRetrievalEngine()
    return build_workflow(retrieval_engine, create_llm_invoker())


app = FastAPI(title="Financial RAG API", version="1.0.0")
app.state.workflow = _build_default_workflow()
app.state.ingestion_pipeline = FinancialIngestionPipeline()


@app.middleware("http")
async def metrics_middleware(request: Any, call_next: Any) -> Response:
    from src.observability import record_request

    started = time.perf_counter()
    response = await call_next(request)
    record_request(request, response, started)
    return response


from src.observability import dependency_status, instrument_fastapi, metrics_payload

instrument_fastapi(app)


def _graph_nodes(contexts: list[dict[str, Any]]) -> list[str]:
    nodes: list[str] = []
    for context in contexts:
        metadata = context.get("metadata", {})
        values = metadata.get("graph_nodes_traversed", metadata.get("graph_nodes", []))
        if isinstance(values, str):
            values = [values]
        elif not values:
            entity = metadata.get("entity")
            connected = metadata.get("connected_entity")
            if entity and connected:
                values = [str(entity), str(connected)]
            elif entity:
                values = [str(entity)]
        for value in values:
            val_str = str(value).strip()
            if val_str and val_str not in nodes:
                nodes.append(val_str)
    return nodes



def _dashboard_payload(contexts: list[dict[str, Any]]) -> dict[str, Any]:
    rows = []
    for context in contexts:
        if context.get("source_type") != "structured_record":
            continue
        metadata = context.get("metadata", {})
        rows.append({
            "metric": metadata.get("metric"),
            "period": metadata.get("period"),
            "value": metadata.get("value"),
            "source_file": metadata.get("source_file"),
            "sheet_name": metadata.get("sheet_name"),
            "citation_id": context.get("id"),
        })
    return {"rows": rows, "source_count": len(rows)}


@app.get("/api/health", response_model=HealthResponse)
def health() -> HealthResponse:
    logger.debug("health_check status=ok")
    return HealthResponse(status="ok", service="financial-rag")


@app.get("/healthz/live")
def liveness() -> dict[str, str]:
    return {"status": "ok", "service": "financial-rag"}


@app.get("/healthz/ready")
def readiness() -> Response:
    dependencies = dependency_status()
    ready = all(value == "ok" for value in dependencies.values())
    return Response(
        content=json.dumps({"status": "ready" if ready else "unhealthy", "dependencies": dependencies}),
        status_code=200 if ready else 503,
        media_type="application/json",
    )


@app.get("/metrics")
def metrics() -> Response:
    payload, content_type = metrics_payload()
    return Response(content=payload, media_type=content_type.split(";", 1)[0], headers={"Content-Type": content_type})


@app.get("/api/dashboard/data")
def dashboard_data(query: str = Query(default="revenue", min_length=1)) -> dict[str, Any]:
    """Return grounded structured records for Grafana and other dashboard clients."""
    contexts = [context.model_dump() for context in structured_store.search(query, limit=50)]
    return {"query": query, **_dashboard_payload(contexts)}


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

    logger.info(
        "chat_completed query_length=%d citations=%d grounded=%s duration_ms=%.1f",
        len(request.query), len(citations), numerical_fidelity_passed,
        (time.perf_counter() - started) * 1000,
    )

    return ChatResponse(
        query=query,
        answer=answer,
        citations=citations,
        graph_nodes_traversed=_graph_nodes(contexts),
        numerical_fidelity_passed=numerical_fidelity_passed,
        execution_time_ms=(time.perf_counter() - started) * 1000,
        dashboard_payload=_dashboard_payload(contexts),
    )


@app.post("/api/chat/stream")
def chat_stream(request: ChatRequest) -> StreamingResponse:
    """Stream a guarded answer as SSE events while preserving final citations."""
    async def events():
        started = time.perf_counter()
        yield "event: status\ndata: {\"status\": \"processing\"}\n\n"
        workflow_task = asyncio.create_task(asyncio.to_thread(
            app.state.workflow.invoke,
            {
                "raw_query": request.query,
                "top_n": request.top_n,
                "enable_graph_expansion": request.enable_graph_expansion,
            },
        ))
        while not workflow_task.done():
            await asyncio.sleep(15)
            if not workflow_task.done():
                yield ": keepalive\n\n"

        result = await workflow_task
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

        logger.info(
            "chat_stream_ready query_length=%d citations=%d grounded=%s duration_ms=%.1f",
            len(request.query), len(citations), numerical_fidelity_passed,
            (time.perf_counter() - started) * 1000,
        )

        payload = {
            "query": query,
            "citations": citations,
            "graph_nodes_traversed": _graph_nodes(contexts),
            "numerical_fidelity_passed": numerical_fidelity_passed,
            "execution_time_ms": (time.perf_counter() - started) * 1000,
            "dashboard_payload": _dashboard_payload(contexts),
        }
        for offset in range(0, len(answer), 24):
            yield f"event: token\ndata: {json.dumps({'text': answer[offset:offset + 24]})}\n\n"
        yield f"event: complete\ndata: {json.dumps({'answer': answer, **payload})}\n\n"

    return StreamingResponse(
        events(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


from src.indexing.indexer import FinancialIndexer

indexer = (
    FinancialIndexer(structured_store=structured_store)
    if IndexingSettings().qdrant_url != ":memory:"
    else None
)

@app.post("/api/upload", response_model=UploadResponse)
def upload(file: UploadFile = File(...)) -> UploadResponse:
    filename = Path(file.filename or "upload").name
    suffix = Path(filename).suffix.lower()
    if suffix not in {".csv", ".docx", ".jpeg", ".jpg", ".pdf", ".png", ".txt", ".xlsx"}:
        logger.warning("upload_rejected filename=%s reason=unsupported_extension", filename)
        raise HTTPException(status_code=415, detail="Unsupported file type")

    temporary_path: str | None = None
    try:
        descriptor, temporary_path = tempfile.mkstemp(suffix=suffix)
        file_bytes = file.file.read()
        with os.fdopen(descriptor, "wb") as temporary_file:
            temporary_file.write(file_bytes)
        result = app.state.ingestion_pipeline.ingest(temporary_path)
        for chunk in result.chunks:
            sheet_name = chunk.metadata.get("sheet_name", "document")
            chunk.chunk_id = f"{filename}:{sheet_name}"
            chunk.source_file = filename
        structured_store.upsert(result.chunks)
        if indexer is not None:
            indexing_result = indexer.index(result.chunks)
        else:
            indexing_result = {}
        logger.info(
            "upload_completed filename=%s extension=%s size_bytes=%d chunks=%d chunk_types=%s indexed=%s",
            filename, suffix, len(file_bytes), result.total_chunks,
            ",".join(sorted({chunk.chunk_type for chunk in result.chunks})),
            bool(indexing_result),
        )
    except Exception as exc:
        logger.exception("upload_failed filename=%s extension=%s", filename, suffix)
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
