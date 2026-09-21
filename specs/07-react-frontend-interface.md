# Spec 07: React Frontend & Financial Chat Interface

## 1. Goal & Scope
Build the interactive user interface and streaming API, with Power BI-ready dashboard outputs:
- **FastAPI Serving Layer**: Expose endpoints for `/api/chat` (streaming SSE or JSON), `/api/upload` (multimodal ingestion for PDFs/Excel), and `/api/health`.
- **React Frontend**: Modern chat dashboard supporting:
  - Markdown and tabular rendering for financial figures.
  - Interactive citation badges linking directly to source snippets.
  - Collapsible inspection drawer displaying retrieved graph entities, traversal hops, and reranker scores.
  - File upload widget for ad-hoc financial document ingestion.
  - Dashboard payload state for KPI cards, period comparisons, trends, and drill-through source documents.

## 2. Target File Tree
- `src/api/server.py`                # FastAPI application & route declarations
- `src/api/schemas.py`               # API request/response schemas
- `frontend/package.json`            # React application manifest & scripts
- `frontend/src/App.jsx`             # Main dashboard layout
- `frontend/src/components/Chat.jsx` # Streaming message list & prompt bar
- `frontend/src/components/Citations.jsx` # Drawer for source verification & graph inspection
- `frontend/src/components/Upload.jsx`    # Document drag-and-drop ingestion component
- `tests/test_api.py`                # FastAPI TestClient endpoint tests

## 3. Data Contracts & Interfaces
Use Pydantic v2 for the API boundary:

```python
from pydantic import BaseModel, Field
from typing import List, Dict, Any, Optional

class ChatRequest(BaseModel):
    query: str
    top_n: int = 5
    enable_graph_expansion: bool = True

class ChatResponse(BaseModel):
    query: str
    answer: str
    citations: List[Dict[str, Any]]
    graph_nodes_traversed: List[str]
    numerical_fidelity_passed: bool
    execution_time_ms: float