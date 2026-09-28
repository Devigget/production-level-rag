"""Pydantic contracts for the FastAPI serving layer."""

from typing import Any, List, Optional
from pydantic import BaseModel, Field


class StoreCreateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    description: str = Field(default="", max_length=500)


class DocumentSchema(BaseModel):
    doc_id: str
    store_id: str
    filename: str
    file_type: str
    uploaded_at: str
    total_chunks: int = 0
    chunk_types: List[str] = Field(default_factory=list)


class StoreResponse(BaseModel):
    id: str
    name: str
    description: str = ""
    created_at: str
    documents: List[DocumentSchema] = Field(default_factory=list)


class ChatMessageSchema(BaseModel):
    id: str
    role: str
    content: str
    citations: List[dict[str, Any]] = Field(default_factory=list)
    graph_nodes_traversed: List[str] = Field(default_factory=list)
    route_used: Optional[str] = None
    dashboard_payload: dict[str, Any] = Field(default_factory=dict)
    timestamp: float


class ChatRequest(BaseModel):
    query: str = Field(min_length=1)
    top_n: int = Field(default=5, ge=1, le=50)
    enable_graph_expansion: bool = True
    store_id: Optional[str] = None


class ChatResponse(BaseModel):
    query: str
    answer: str
    citations: list[dict[str, Any]] = Field(default_factory=list)
    graph_nodes_traversed: list[str] = Field(default_factory=list)
    numerical_fidelity_passed: bool
    execution_time_ms: float
    dashboard_payload: dict[str, Any] = Field(default_factory=dict)
    route_used: str = "HYBRID"
    store_id: str = "default"


class UploadResponse(BaseModel):
    filename: str
    source_file: str
    total_chunks: int
    chunk_types: list[str]
    doc_id: str = ""
    store_id: str = "default"


class HealthResponse(BaseModel):
    status: str
    service: str
