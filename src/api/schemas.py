"""Pydantic contracts for the FastAPI serving layer."""

from typing import Any

from pydantic import BaseModel, Field


class ChatRequest(BaseModel):
    query: str = Field(min_length=1)
    top_n: int = Field(default=5, ge=1, le=50)
    enable_graph_expansion: bool = True


class ChatResponse(BaseModel):
    query: str
    answer: str
    citations: list[dict[str, Any]] = Field(default_factory=list)
    graph_nodes_traversed: list[str] = Field(default_factory=list)
    numerical_fidelity_passed: bool
    execution_time_ms: float
    dashboard_payload: dict[str, Any] = Field(default_factory=dict)


class UploadResponse(BaseModel):
    filename: str
    source_file: str
    total_chunks: int
    chunk_types: list[str]


class HealthResponse(BaseModel):
    status: str
    service: str
