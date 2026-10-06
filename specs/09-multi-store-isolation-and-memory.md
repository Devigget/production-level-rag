# Spec 09: Multi-Store Financial Data Isolation & Conversational Short-Term Memory

## 1. Goal & Scope
Build a multi-store catalog and session-isolated short-term conversational memory system with cross-pod synchronization:
- **Store Partitioning**: Allow financial analysts to create and manage isolated workspaces ("Stores", e.g., "Main Ledger", "North America Retail", "EMEA Operations", "Brew and Bean").
- **Multi-Pod Concurrency Synchronization (`src/store/manager.py`)**:
  - In high-availability multi-replica environments (e.g., 2 backend pods in Kubernetes), synchronize in-memory catalogs across pods sharing the persistent volume (`backend-data-pvc` at `/app/data/stores_registry.json`).
  - Implement timestamp-based cache invalidation (`os.path.getmtime` checking) on all read/write accesses to prevent state drift, store duplication, or fluctuating store IDs across load-balanced requests.
- **Document Registry**: Maintain a persistent document catalog per store, tracking filename, upload timestamp, chunk counts, and chunk types.
- **Short-Term Conversational Memory**: Maintain multi-turn conversational history scoped strictly to each store. Feed recent turns into the agentic orchestration graph to resolve pronoun references and follow-up financial questions.
- **Cross-Layer Data Isolation**:
  - **Vector Layer (Qdrant)**: Tag all point payloads with `store_id` and filter search queries using Qdrant payload condition filters.
  - **Graph Layer (Neo4j)**: Structure the property graph with `:Store` root nodes connected via `[:HAS_DOCUMENT]` to `:Document` nodes, scoping `:Metric` and `:FinancialEntity` nodes with `store_id`.
  - **Structured Layer**: Scope normalized financial records to the active store.
- **Startup Synchronization**: Synchronize registered stores and documents into the Neo4j graph during application startup (`startup_sync_graph`).
- **Persistence**: Persist stores, document metadata, and message history to `data/stores_registry.json` with automatic fallback and default store provisioning.

## 2. Target File Tree
- `src/store/manager.py`            # StoreManager with multi-pod file synchronization
- `src/store/__init__.py`           # Store module exports
- `data/stores_registry.json`       # Persistent JSON store catalog and chat history
- `src/api/server.py`               # REST endpoints for store lifecycle and memory
- `src/api/schemas.py`              # Pydantic schemas for store requests and responses
- `frontend/src/components/Sidebar.jsx` # Store management and switching interface
- `tests/test_store_rag.py`         # Store lifecycle, document scoping, and memory test suite

## 3. Data Contracts & Interfaces
Use Pydantic v2:

```python
import time
import uuid
from typing import Any, List, Optional
from pydantic import BaseModel, Field

class DocumentMetadata(BaseModel):
    doc_id: str
    store_id: str
    filename: str
    file_type: str
    uploaded_at: str = Field(default_factory=lambda: time.strftime("%Y-%m-%d %H:%M:%S"))
    total_chunks: int = 0
    chunk_types: List[str] = Field(default_factory=list)

class ChatMessage(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    role: str  # "user" or "assistant"
    content: str
    citations: List[dict[str, Any]] = Field(default_factory=list)
    graph_nodes_traversed: List[str] = Field(default_factory=list)
    route_used: Optional[str] = None
    dashboard_payload: dict[str, Any] = Field(default_factory=dict)
    timestamp: float = Field(default_factory=time.time)

class Store(BaseModel):
    id: str
    name: str
    description: str = ""
    created_at: str = Field(default_factory=lambda: time.strftime("%Y-%m-%d %H:%M:%S"))
    documents: List[DocumentMetadata] = Field(default_factory=list)

class StoreCreateRequest(BaseModel):
    name: str
    description: str = ""

class StoreResponse(BaseModel):
    id: str
    name: str
    description: str = ""
    created_at: str
    documents: List[DocumentMetadata] = Field(default_factory=list)
```

## 4. Architectural Details

### 4.1. Store Manager Multi-Pod Synchronization (`StoreManager`)
In Kubernetes, multiple backend pod replicas mount the shared volume `backend-data-pvc` at `/app/data`. If Pod A creates a store, Pod B must immediately reflect that store on subsequent requests.

- **Timestamp Synchronization (`_check_and_reload`)**:
  ```python
  def _check_and_reload(self) -> None:
      if not os.path.exists(self.registry_path):
          return
      try:
          current_mtime = os.path.getmtime(self.registry_path)
          if current_mtime > self._last_mtime:
              self._load_from_disk()
              self._last_mtime = current_mtime
      except Exception:
          pass
  ```
- **Operations**:
  - `list_stores()`: Invokes `_check_and_reload()` and returns all active stores.
  - `get_store(store_id)`: Checks for disk updates before retrieving store metadata.
  - `create_store(name, description)`: Generates an 8-character UUID identifier, checks for existing stores by name to avoid duplicate creations, writes atomically, and updates `_last_mtime`.
  - `delete_store(store_id)`: Removes custom stores and cleans up memory. Preserves the `"default"` store.
  - `add_document(store_id, doc)`: Deduplicates documents by `doc_id` or `filename`, updates metadata, and flushes to disk.
  - `list_documents(store_id)`: Retrieves documents uploaded to the specified store.
  - `sync_documents_from_graph(documents)`: Reconciles documents discovered from Neo4j graph storage into local store state across replicas without duplication.
  - `add_message(store_id, role, content, ...)`: Records conversation turns with full audit metadata (citations, traversed graph nodes, route used, dashboard payload).
  - `get_chat_history(store_id, limit)`: Retrieves the last `N` messages for a store.
  - `format_short_term_memory(store_id, max_turns)`: Formats the recent dialogue turns into a prompt-ready transcript (`User: ... \n Assistant: ...`) for LLM context windowing.
  - `clear_chat_history(store_id)`: Resets conversation history for the specified store.

### 4.2. Short-Term Memory Formatting
When a query is dispatched to the orchestration pipeline, `StoreManager.format_short_term_memory(store_id, max_turns=6)` formats the sliding window of recent conversation turns into:
```text
User: What was Q1 revenue?
Assistant: Q1 revenue was $50,000.
User: What about Q2?
```
This formatted history is passed in `workflow_input["chat_history"]` and bound to the LangGraph state machine so the LLM can resolve follow-up questions without losing retrieval fidelity.

### 4.3. REST API Surface
| Method | Path | Description |
|---|---|---|
| `GET` | `/api/stores` | List all stores and their document inventories |
| `POST` | `/api/stores` | Create a new isolated financial store |
| `GET` | `/api/stores/{store_id}` | Retrieve store metadata and document count |
| `DELETE` | `/api/stores/{store_id}` | Delete a store and purge its short-term memory |
| `GET` | `/api/stores/{store_id}/documents` | List documents indexed under a store |
| `GET` | `/api/stores/{store_id}/messages` | Retrieve short-term chat messages for a store |
| `POST` | `/api/stores/{store_id}/clear-chat` | Clear conversation history for a store |

### 4.4. Cross-Layer Storage Partitioning
1. **Document Ingestion (`/api/upload`)**:
   - Accepts `store_id` as form parameter (defaulting to `"default"`).
   - Assigns a unique `doc_id` and attaches `store_id` to all generated `FinancialChunk` and `FinancialRecord` objects.
   - Registers `DocumentMetadata` in `StoreManager`.
2. **Qdrant Vector Storage**:
   - Ingests chunks with `payload={"store_id": store_id, "doc_id": doc_id, "chunk": ...}`.
   - In queries with `store_id`, applies Qdrant `FieldCondition` filtering on `store_id`.
3. **Neo4j Graph Storage**:
   - Executes `register_document(...)`: Merges `(:Store {id: $store_id})`, `(:Document {id: $doc_id})`, and creates `(:Store)-[:HAS_DOCUMENT]->(:Document)`.
   - Links entities to the document via `[:REPORTED_METRIC]`, `[:DEFINES]`, and `[:MENTIONS]` while attaching `store_id`.
   - On application startup, `startup_sync_graph()` re-verifies graph synchronization across all stores registered in `StoreManager`.

## 5. Verification & Acceptance Criteria
1. `tests/test_store_rag.py::test_store_creation_and_listing`:
   - Validates store creation, UUID generation, and store listing.
2. `tests/test_store_rag.py::test_store_scoped_upload_and_document_tracking`:
   - Verifies CSV upload with `store_id`, chunk count tracking, and store-specific document retrieval.
3. `tests/test_store_rag.py::test_store_short_term_memory_persistence`:
   - Validates message persistence, retrieval, sliding-window formatting, and clear-chat reset.
4. `tests/test_store_rag.py::test_store_manager_cross_replica_sync_and_deduplication`:
   - Validates multi-replica state persistence and concurrent chat writes preserving new document additions.
5. `tests/test_store_rag.py::test_store_manager_sync_from_graph`:
   - Validates idempotent reconciliation of graph-persisted documents into the local store catalog.
6. Multi-pod store synchronization verification (`scripts/test-k8s.ps1` Phase 3):
   - Confirms that stores created on Pod A are immediately returned by Pod B across round-robin load-balanced requests without store duplication or ID fluctuation.
