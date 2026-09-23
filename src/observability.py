"""Application telemetry, structured logging, RED metrics, and probes."""

from __future__ import annotations

import json
import logging
import os
import time
from typing import Any

from prometheus_client import CONTENT_TYPE_LATEST, Counter, Histogram, generate_latest

from src.indexing.config import IndexingSettings


REQUESTS_TOTAL = Counter(
    "http_requests_total",
    "Total HTTP requests handled by the API.",
    ("method", "route", "code"),
)
REQUEST_DURATION = Histogram(
    "http_request_duration_seconds",
    "HTTP request duration in seconds.",
    ("method", "route", "code"),
    buckets=(0.05, 0.1, 0.25, 0.5, 1, 2.5, 5, 10, 30),
)


class TraceContextFilter(logging.Filter):
    """Attach W3C trace identifiers to every structured log record."""

    def filter(self, record: logging.LogRecord) -> bool:
        try:
            from opentelemetry import trace

            context = trace.get_current_span().get_span_context()
            record.trace_id = format(context.trace_id, "032x") if context.is_valid else None
            record.span_id = format(context.span_id, "016x") if context.is_valid else None
        except ImportError:
            record.trace_id = None
            record.span_id = None
        return True


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "timestamp": self.formatTime(record, "%Y-%m-%dT%H:%M:%S%z"),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "trace_id": getattr(record, "trace_id", None),
            "span_id": getattr(record, "span_id", None),
            "service": os.getenv("OTEL_SERVICE_NAME", "financial-rag-api"),
        }
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        return json.dumps(payload, default=str)


def configure_logging() -> None:
    level_name = os.getenv("LOG_LEVEL", "INFO").upper()
    level = getattr(logging, level_name, logging.INFO)
    handler = logging.StreamHandler()
    handler.addFilter(TraceContextFilter())
    handler.setFormatter(JsonFormatter())
    root = logging.getLogger()
    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(level)


def configure_telemetry() -> None:
    """Bootstrap OTel before importing instrumented frameworks and clients."""
    if os.getenv("OTEL_ENABLED", "false").lower() not in {"1", "true", "yes"}:
        return
    try:
        from opentelemetry import trace
        from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
        from opentelemetry.sdk.resources import Resource
        from opentelemetry.sdk.trace import TracerProvider
        from opentelemetry.sdk.trace.export import BatchSpanProcessor

        provider = TracerProvider(resource=Resource.create({
            "service.name": os.getenv("OTEL_SERVICE_NAME", "financial-rag-api"),
            "deployment.environment": os.getenv("APP_ENV", "local"),
        }))
        endpoint = os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT", "http://otel-collector:4317")
        provider.add_span_processor(BatchSpanProcessor(OTLPSpanExporter(endpoint=endpoint, insecure=True)))
        trace.set_tracer_provider(provider)
        try:
            from opentelemetry.instrumentation.httpx import HTTPXClientInstrumentor

            HTTPXClientInstrumentor().instrument()
        except ImportError:
            logging.getLogger(__name__).warning("httpx_opentelemetry_instrumentation_not_installed")
    except ImportError:
        logging.getLogger(__name__).warning("opentelemetry_not_installed")


def instrument_fastapi(app: Any) -> None:
    try:
        from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor

        FastAPIInstrumentor.instrument_app(app)
    except ImportError:
        logging.getLogger(__name__).warning("fastapi_opentelemetry_instrumentation_not_installed")


def metrics_payload() -> tuple[bytes, str]:
    return generate_latest(), CONTENT_TYPE_LATEST


def record_request(request: Any, response: Any, started: float) -> None:
    route = getattr(request.scope.get("route"), "path", None) or request.url.path
    labels = (request.method, route, str(response.status_code))
    REQUESTS_TOTAL.labels(*labels).inc()
    REQUEST_DURATION.labels(*labels).observe(time.perf_counter() - started)


def dependency_status() -> dict[str, str]:
    settings = IndexingSettings()
    status = {"qdrant": "ok", "neo4j": "ok"}
    if settings.qdrant_url != ":memory:":
        try:
            import httpx

            response = httpx.get(f"{settings.qdrant_url.rstrip('/')}/readyz", timeout=1.5)
            if response.status_code >= 400:
                status["qdrant"] = "unhealthy"
        except Exception:
            status["qdrant"] = "unhealthy"
    try:
        from neo4j import GraphDatabase

        driver = GraphDatabase.driver(settings.neo4j_uri, auth=(settings.neo4j_user, settings.neo4j_password))
        try:
            driver.verify_connectivity()
        finally:
            driver.close()
    except Exception:
        status["neo4j"] = "unhealthy"
    return status