"""FastAPI serving layer for store-scoped financial chat, short-term memory, and document ingestion."""

from __future__ import annotations

import json
import logging
import os
import tempfile
import time
import uuid
import asyncio
from pathlib import Path
from typing import Any

from src.observability import configure_logging, configure_telemetry

configure_telemetry()

from fastapi import FastAPI, File, Form, HTTPException, Query, UploadFile
from fastapi.responses import Response, StreamingResponse

import pandas as pd

from src.ingestion.pipeline import FinancialIngestionPipeline
from src.ingestion.parsers.tabular_pipeline import (
    compile_cypher_statements,
    execute_cypher_ingestion,
    extract_schema_blueprint,
)
from src.indexing.config import IndexingSettings
from src.retrieval.models import HybridSearchResult, RetrievalQuery
from src.retrieval.engine import HybridRetrievalEngine
from src.retrieval.graph_search import GraphSearcher
from src.retrieval.structured_search import StructuredFinancialStore
from src.retrieval.vector_search import VectorSearcher
from src.store.manager import DocumentMetadata, StoreManager
from src.api.schemas import (
    ChatMessageSchema,
    ChatRequest,
    ChatResponse,
    DocumentSchema,
    HealthResponse,
    StoreCreateRequest,
    StoreResponse,
    UploadResponse,
)
from src.orchestration.graph import build_workflow, create_llm_invoker

from src.evaluation.tracer import get_tracer

configure_logging()
logger = logging.getLogger(__name__)

store_manager = StoreManager()
tracer = get_tracer()



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


@app.on_event("startup")
def startup_sync_graph() -> None:
    if indexer is not None and hasattr(indexer, "graph_store"):
        try:
            for store in store_manager.list_stores():
                for doc in store.documents:
                    indexer.graph_store.register_document(
                        store_id=store.id,
                        store_name=store.name,
                        doc_id=doc.doc_id,
                        filename=doc.filename,
                        file_type=doc.file_type,
                        total_chunks=doc.total_chunks,
                        chunk_types=doc.chunk_types,
                        uploaded_at=doc.uploaded_at,
                    )
                    indexer.graph_store.link_unstructured_entities(
                        store_id=store.id,
                        doc_id=doc.doc_id,
                        filename=doc.filename,
                    )
            logger.info("Startup graph sync completed for registered stores")
        except Exception as exc:
            logger.warning("Startup graph sync failed: %s", exc)


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


# ---------------------------------------------------------
# Store Management & Short-Term Memory Endpoints
# ---------------------------------------------------------

@app.get("/api/stores", response_model=list[StoreResponse])
def list_stores() -> list[StoreResponse]:
    stores = store_manager.list_stores()
    return [
        StoreResponse(
            id=s.id,
            name=s.name,
            description=s.description,
            created_at=s.created_at,
            documents=[DocumentSchema(**d.model_dump()) for d in s.documents],
        )
        for s in stores
    ]


@app.post("/api/stores", response_model=StoreResponse)
def create_store(req: StoreCreateRequest) -> StoreResponse:
    store = store_manager.create_store(name=req.name, description=req.description)
    return StoreResponse(
        id=store.id,
        name=store.name,
        description=store.description,
        created_at=store.created_at,
        documents=[],
    )


@app.get("/api/stores/{store_id}", response_model=StoreResponse)
def get_store(store_id: str) -> StoreResponse:
    store = store_manager.get_store(store_id)
    if not store:
        raise HTTPException(status_code=404, detail="Store not found")
    return StoreResponse(
        id=store.id,
        name=store.name,
        description=store.description,
        created_at=store.created_at,
        documents=[DocumentSchema(**d.model_dump()) for d in store.documents],
    )


@app.delete("/api/stores/{store_id}")
def delete_store(store_id: str) -> dict[str, str]:
    success = store_manager.delete_store(store_id)
    if not success:
        raise HTTPException(status_code=404, detail="Store not found")
    return {"status": "ok", "message": f"Store {store_id} deleted"}


@app.get("/api/stores/{store_id}/documents", response_model=list[DocumentSchema])
def list_store_documents(store_id: str) -> list[DocumentSchema]:
    docs = store_manager.list_documents(store_id)
    return [DocumentSchema(**d.model_dump()) for d in docs]


@app.get("/api/stores/{store_id}/messages", response_model=list[ChatMessageSchema])
def get_store_messages(store_id: str, limit: int = 50) -> list[ChatMessageSchema]:
    messages = store_manager.get_chat_history(store_id, limit=limit)
    return [ChatMessageSchema(**m.model_dump()) for m in messages]


@app.post("/api/stores/{store_id}/clear-chat")
def clear_store_chat(store_id: str) -> dict[str, str]:
    store_manager.clear_chat_history(store_id)
    return {"status": "ok", "message": f"Chat history cleared for store {store_id}"}


# ---------------------------------------------------------
# Health, Live, Metrics, Dashboard
# ---------------------------------------------------------

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


# ---------------------------------------------------------
# Chat & Streaming with Store Isolation & Short-Term Memory
# ---------------------------------------------------------

@app.post("/api/chat", response_model=ChatResponse)
def chat(request: ChatRequest) -> ChatResponse:
    started = time.perf_counter()
    store_id = request.store_id or "default"
    store = store_manager.get_store(store_id)
    store_name = store.name if store else "Main Store"

    short_term_memory = store_manager.format_short_term_memory(store_id, max_turns=6)

    workflow_input: dict[str, Any] = {
        "raw_query": request.query,
        "top_n": request.top_n,
        "enable_graph_expansion": request.enable_graph_expansion,
    }
    if request.store_id is not None:
        workflow_input["store_id"] = store_id
        workflow_input["store_name"] = store_name
        workflow_input["chat_history"] = short_term_memory

    result = app.state.workflow.invoke(workflow_input)
    final_output = result.get("final_output")
    contexts = result.get("retrieved_contexts", [])
    route_used = result.get("retrieval_route") or getattr(final_output, "route_used", "HYBRID") or "HYBRID"

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
        "chat_completed query_length=%d citations=%d grounded=%s store_id=%s route=%s duration_ms=%.1f",
        len(request.query), len(citations), numerical_fidelity_passed, store_id, route_used,
        (time.perf_counter() - started) * 1000,
    )

    dashboard_payload = _dashboard_payload(contexts)

    # Persist in Store-scoped Short-Term Memory
    store_manager.add_message(store_id=store_id, role="user", content=request.query)
    store_manager.add_message(
        store_id=store_id,
        role="assistant",
        content=answer,
        citations=citations,
        graph_nodes_traversed=_graph_nodes(contexts),
        route_used=route_used,
        dashboard_payload=dashboard_payload,
    )

    # Trace LLM execution via Langfuse (if configured)
    tracer.trace_workflow_run(
        query=request.query,
        result=result,
        store_id=store_id,
        route_used=route_used,
        execution_time_ms=(time.perf_counter() - started) * 1000,
        session_id=f"store-{store_id}",
        user_id=f"user-{store_id}",
        tags=["production-rag", f"store:{store_id}", f"route:{route_used}", "chat"],
    )

    return ChatResponse(
        query=query,
        answer=answer,
        citations=citations,
        graph_nodes_traversed=_graph_nodes(contexts),
        numerical_fidelity_passed=numerical_fidelity_passed,
        execution_time_ms=(time.perf_counter() - started) * 1000,
        dashboard_payload=dashboard_payload,
        route_used=route_used,
        store_id=store_id,
    )


@app.post("/api/chat/stream")
def chat_stream(request: ChatRequest) -> StreamingResponse:
    """Stream a guarded answer as SSE events while preserving store scoping and citations."""
    async def events():
        started = time.perf_counter()
        store_id = request.store_id or "default"
        store = store_manager.get_store(store_id)
        store_name = store.name if store else "Main Store"
        short_term_memory = store_manager.format_short_term_memory(store_id, max_turns=6)

        workflow_input: dict[str, Any] = {
            "raw_query": request.query,
            "top_n": request.top_n,
            "enable_graph_expansion": request.enable_graph_expansion,
        }
        if request.store_id is not None:
            workflow_input["store_id"] = store_id
            workflow_input["store_name"] = store_name
            workflow_input["chat_history"] = short_term_memory

        yield "event: status\ndata: {\"status\": \"processing\"}\n\n"
        workflow_task = asyncio.create_task(asyncio.to_thread(
            app.state.workflow.invoke,
            workflow_input,
        ))
        while not workflow_task.done():
            await asyncio.sleep(15)
            if not workflow_task.done():
                yield ": keepalive\n\n"

        result = await workflow_task
        final_output = result.get("final_output")
        contexts = result.get("retrieved_contexts", [])
        route_used = result.get("retrieval_route") or getattr(final_output, "route_used", "HYBRID") or "HYBRID"

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

        dashboard_payload = _dashboard_payload(contexts)

        # Record into Short-Term Memory
        store_manager.add_message(store_id=store_id, role="user", content=request.query)
        store_manager.add_message(
            store_id=store_id,
            role="assistant",
            content=answer,
            citations=citations,
            graph_nodes_traversed=_graph_nodes(contexts),
            route_used=route_used,
            dashboard_payload=dashboard_payload,
        )

        logger.info(
            "chat_stream_ready query_length=%d citations=%d grounded=%s store_id=%s route=%s duration_ms=%.1f",
            len(request.query), len(citations), numerical_fidelity_passed, store_id, route_used,
            (time.perf_counter() - started) * 1000,
        )

        # Trace LLM execution via Langfuse (if configured)
        tracer.trace_workflow_run(
            query=request.query,
            result=result,
            store_id=store_id,
            route_used=route_used,
            execution_time_ms=(time.perf_counter() - started) * 1000,
            session_id=f"store-{store_id}",
            user_id=f"user-{store_id}",
            tags=["production-rag", f"store:{store_id}", f"route:{route_used}", "stream"],
        )

        payload = {
            "query": query,
            "citations": citations,
            "graph_nodes_traversed": _graph_nodes(contexts),
            "numerical_fidelity_passed": numerical_fidelity_passed,
            "execution_time_ms": (time.perf_counter() - started) * 1000,
            "dashboard_payload": dashboard_payload,
            "route_used": route_used,
            "store_id": store_id,
        }
        for offset in range(0, len(answer), 24):
            yield f"event: token\ndata: {json.dumps({'text': answer[offset:offset + 24]})}\n\n"
        yield f"event: complete\ndata: {json.dumps({'answer': answer, **payload})}\n\n"

    return StreamingResponse(
        events(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


# ---------------------------------------------------------
# Upload & Dual-Path Ingestion Endpoint
# ---------------------------------------------------------

from src.indexing.indexer import FinancialIndexer

indexer = (
    FinancialIndexer(structured_store=structured_store)
    if IndexingSettings().qdrant_url != ":memory:"
    else None
)


@app.post("/api/upload", response_model=UploadResponse)
def upload(
    file: UploadFile = File(...),
    store_id: str = Form("default"),
) -> UploadResponse:
    filename = Path(file.filename or "upload").name
    suffix = Path(filename).suffix.lower()
    if suffix not in {".csv", ".docx", ".jpeg", ".jpg", ".pdf", ".png", ".txt", ".xls", ".xlsx"}:
        logger.warning("upload_rejected filename=%s reason=unsupported_extension", filename)
        raise HTTPException(status_code=415, detail="Unsupported file type")

    clean_store_id = store_id.strip() if store_id else "default"
    store = store_manager.get_store(clean_store_id)
    if not store:
        store = store_manager.create_store(name=f"Store {clean_store_id}", store_id=clean_store_id)
    store_name = store.name

    doc_id = str(uuid.uuid4())[:8]
    temporary_path: str | None = None
    try:
        descriptor, temporary_path = tempfile.mkstemp(suffix=suffix)
        file_bytes = file.file.read()
        with os.fdopen(descriptor, "wb") as temporary_file:
            temporary_file.write(file_bytes)

        # Dual-path ingestion: Header-injected serialization + layout chunking
        result = app.state.ingestion_pipeline.ingest(
            temporary_path,
            store_id=clean_store_id,
            store_name=store_name,
            doc_id=doc_id,
            dual_path=True,
        )

        for chunk in result.chunks:
            chunk.source_file = filename
            chunk.store_id = clean_store_id
            chunk.doc_id = doc_id

        structured_store.upsert(result.chunks)

        chunk_types = sorted({chunk.chunk_type for chunk in result.chunks})

        if indexer is not None:
            indexer.index(result.chunks)
            if hasattr(indexer, "graph_store"):
                try:
                    indexer.graph_store.register_document(
                        store_id=clean_store_id,
                        store_name=store_name,
                        doc_id=doc_id,
                        filename=filename,
                        file_type=suffix,
                        total_chunks=result.total_chunks,
                        chunk_types=chunk_types,
                        uploaded_at=time.strftime("%Y-%m-%d %H:%M:%S"),
                    )
                except Exception as g_exc:
                    logger.warning("Graph document root registration failed: %s", g_exc)

            # If tabular, run Graph DB ingestion (LLM/heuristic Blueprint -> Cypher batch MERGE)
            if suffix in {".csv", ".xlsx", ".xls"} and hasattr(indexer, "graph_store"):
                try:
                    df = pd.read_csv(temporary_path) if suffix == ".csv" else pd.read_excel(temporary_path)
                    blueprint = extract_schema_blueprint(df)
                    cypher_statements = compile_cypher_statements(blueprint)
                    execute_cypher_ingestion(
                        driver=indexer.graph_store.driver,
                        database=indexer.graph_store.settings.neo4j_database,
                        statements=cypher_statements,
                        store_id=clean_store_id,
                        store_name=store_name,
                        doc_id=doc_id,
                        filename=filename,
                        dataframe=df,
                    )
                except Exception as g_exc:
                    logger.warning("Graph batch ingestion failed: %s", g_exc)
            elif hasattr(indexer, "graph_store"):
                try:
                    indexer.graph_store.link_unstructured_entities(
                        store_id=clean_store_id,
                        doc_id=doc_id,
                        filename=filename,
                    )
                except Exception as g_exc:
                    logger.warning("Graph unstructured linking failed: %s", g_exc)

        chunk_types = sorted({chunk.chunk_type for chunk in result.chunks})

        # Register in Store catalog
        doc_meta = DocumentMetadata(
            doc_id=doc_id,
            store_id=clean_store_id,
            filename=filename,
            file_type=suffix,
            total_chunks=result.total_chunks,
            chunk_types=chunk_types,
        )
        store_manager.add_document(clean_store_id, doc_meta)

        logger.info(
            "upload_completed filename=%s store_id=%s doc_id=%s size_bytes=%d chunks=%d chunk_types=%s",
            filename, clean_store_id, doc_id, len(file_bytes), result.total_chunks, chunk_types,
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
        chunk_types=chunk_types,
        doc_id=doc_id,
        store_id=clean_store_id,
    )
