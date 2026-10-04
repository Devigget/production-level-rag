# Production-Level Financial RAG: System Specifications

## 1. System Overview & Architecture

The **Production-Level Financial RAG System** is an enterprise-grade financial intelligence engine designed to ingest, normalize, index, and query complex financial reports (spreadsheets, annual reports, earnings call transcripts, scanned receipts, Word memos).

It employs a **tri-modal architecture**:
1. **Dense Vector Search (Qdrant)**: Semantic retrieval over structured table rows and narrative paragraphs.
2. **Knowledge Graph Traversal (Neo4j)**: Property graph linking stores, documents, metrics, line items, and temporal periods for multi-hop reasoning.
3. **Structured Financial Records (`StructuredFinancialStore`)**: Deterministic key-value metrics for exact KPI lookups and Power BI dashboard feeds.

Orchestrated through **LangGraph** with strict input/output guardrails and deployed on **Kubernetes**, the system guarantees numerical grounding, multi-store tenant isolation, multi-pod synchronization, short-term conversational memory, distributed OpenTelemetry tracing, and automated quality benchmarking.

```mermaid
graph TD
    User([Financial Analyst / Power BI]) -->|HTTP / Ingress| Ingress[Kubernetes Nginx Ingress / Spec 08]
    User -->|STDIO / SSE| MCP[MCP Server / Spec 05]
    
    Ingress -->|Static Assets| Frontend[React Vite SPA Replicas / Spec 07]
    Ingress -->|REST API / Stream| Backend[FastAPI Backend Replicas :8000 / Spec 08]
    MCP -->|Tools| Backend
    
    Backend --> StoreMgr[Store Manager with Multi-Pod Sync / Spec 09]
    StoreMgr --- PVCBackend[(Shared Volume: backend-data-pvc / Spec 08)]
    
    Backend --> Pipeline[Multimodal Ingestion Pipeline / Spec 01]
    Pipeline --> DualTab[Dual-Path Tabular Pipeline / Spec 10]
    Pipeline --> Indexer[Financial Indexer Coordinator / Spec 02]
    
    Indexer --> Qdrant[(Qdrant Vector DB & PVC / Spec 02)]
    Indexer --> Neo4j[(Neo4j StatefulSet & PVC / Spec 02 & Spec 10)]
    Indexer --> StructStore[(Structured Store / Spec 02 & Spec 03)]
    
    Backend --> Router[Query Router / Spec 10]
    Router --> Orchestration[LangGraph State Machine / Spec 04]
    
    Orchestration --> InputGuard[Input Guardrail: PII & Injection / Spec 04]
    InputGuard --> HybridEngine[Hybrid Retrieval Engine & Reranker / Spec 03]
    
    HybridEngine --> Qdrant
    HybridEngine --> Neo4j
    HybridEngine --> StructStore
    
    HybridEngine --> LLMInvoker[Live Groq LLM Invoker / Spec 04]
    LLMInvoker --> OutputGuard[Output Guardrail: Numerical Fidelity / Spec 04]
    
    OutputGuard --> Backend
    
    Backend -.-> OTelCol[OTel Collector :4317 / Spec 06]
    OTelCol -.-> Tempo[(Tempo Distributed Trace Storage / Spec 06)]
    OTelCol -.-> Prom[(Prometheus Metrics TSDB / Spec 06)]
    Backend -.-> Tracer[Langfuse Observability / Spec 06]
    Backend -.-> EvalHarness[Automated Evaluation Harness / Spec 06]
    
    Grafana[Grafana Dashboards / Spec 06] --> Prom
    Grafana --> Tempo
    Grafana --> Backend
```

---

## 2. Master Specification Index

| Spec | Title | Primary Components | Verification Suite |
|---|---|---|---|
| [Spec 01](file:///c:/Users/VigneshPandurangGaun/OneDrive%20-%20McLaren%20Strategic%20Solutions%20US%20Inc/Documents/Final%20Evaluation%20Project/Production%20level%20RAG/specs/01-document-ingestion-multimodal.md) | **Multimodal Financial Document Ingestion** | PDF, Excel, CSV, Word (`.docx`), TXT, Tesseract OCR (`.png`/`.jpg`), Pydantic models | `tests/test_ingestion.py` (8 tests) |
| [Spec 02](file:///c:/Users/VigneshPandurangGaun/OneDrive%20-%20McLaren%20Strategic%20Solutions%20US%20Inc/Documents/Final%20Evaluation%20Project/Production%20level%20RAG/specs/02-graph-vector-storage-indexing.md) | **Hybrid Graph & Vector Storage Engine** | Qdrant vector indexing, Neo4j StatefulSet (`enableServiceLinks: false`), 10Gi PVC storage, startup sync | `tests/test_indexing.py` (5 tests)<br>`kubectl rollout status` |
| [Spec 03](file:///c:/Users/VigneshPandurangGaun/OneDrive%20-%20McLaren%20Strategic%20Solutions%20US%20Inc/Documents/Final%20Evaluation%20Project/Production%20level%20RAG/specs/03-hybrid-retrieval-reranking.md) | **Hybrid Retrieval & Cross-Encoder Reranking** | Tri-modal search, 2-hop entity expansion, cross-document coverage, BGE cross-encoder | `tests/test_retrieval.py` (13 tests) |
| [Spec 04](file:///c:/Users/VigneshPandurangGaun/OneDrive%20-%20McLaren%20Strategic%20Solutions%20US%20Inc/Documents/Final%20Evaluation%20Project/Production%20level%20RAG/specs/04-guardrails-and-agentic-orchestration.md) | **Financial Guardrails & Agentic Orchestration** | LangGraph workflow, PII & injection guard, numerical fidelity guard, multi-provider LLM (Groq live) | `tests/test_orchestration.py` (6 tests) |
| [Spec 05](file:///c:/Users/VigneshPandurangGaun/OneDrive%20-%20McLaren%20Strategic%20Solutions%20US%20Inc/Documents/Final%20Evaluation%20Project/Production%20level%20RAG/specs/05-mcp-server-and-tooling.md) | **Model Context Protocol (MCP) Server & Tooling** | FastMCP server, financial search, EBITDA & CAGR math, graph inspection, Power BI payload | `tests/test_mcp.py` (8 tests) |
| [Spec 06](file:///c:/Users/VigneshPandurangGaun/OneDrive%20-%20McLaren%20Strategic%20Solutions%20US%20Inc/Documents/Final%20Evaluation%20Project/Production%20level%20RAG/specs/06-evaluation-and-observability.md) | **Observability & Automated Evaluation Suite** | OpenTelemetry, Prometheus, Tempo trace engine, Grafana auto-provisioning (Infinity & RED dashboards), Langfuse | `tests/test_evaluation.py` (9 tests)<br>`tests/test_api.py` (7 tests)<br>`scripts/test-k8s.ps1` |
| [Spec 07](file:///c:/Users/VigneshPandurangGaun/OneDrive%20-%20McLaren%20Strategic%20Solutions%20US%20Inc/Documents/Final%20Evaluation%20Project/Production%20level%20RAG/specs/07-react-frontend-interface.md) | **React Frontend & Financial Chat Interface** | Vite React app (2 replicas), multi-store sidebar, SSE streaming chat, dashboard cards, citations | `tests/test_api.py` (7 tests)<br>`frontend/tests/chat.spec.js` |
| [Spec 08](file:///c:/Users/VigneshPandurangGaun/OneDrive%20-%20McLaren%20Strategic%20Solutions%20US%20Inc/Documents/Final%20Evaluation%20Project/Production%20level%20RAG/specs/08-cicd-docker-deployment.md) | **Production Containerization, Kubernetes Orchestration & CI/CD** | K8s (`k8s/`), 8 services / 10 pods, Nginx Ingress, Docker Compose, Jenkins CI/CD (`Jenkinsfile`) | `scripts/test-k8s.ps1`<br>Jenkins Pipeline<br>GitHub Actions CI |
| [Spec 09](file:///c:/Users/VigneshPandurangGaun/OneDrive%20-%20McLaren%20Strategic%20Solutions%20US%20Inc/Documents/Final%20Evaluation%20Project/Production%20level%20RAG/specs/09-multi-store-isolation-and-memory.md) | **Multi-Store Isolation & Conversational Short-Term Memory** | `StoreManager` with multi-pod file synchronization (`os.path.getmtime`), document tracking, dialogue history | `tests/test_store_rag.py` (5 tests)<br>`scripts/test-k8s.ps1` |
| [Spec 10](file:///c:/Users/VigneshPandurangGaun/OneDrive%20-%20McLaren%20Strategic%20Solutions%20US%20Inc/Documents/Final%20Evaluation%20Project/Production%20level%20RAG/specs/10-intelligent-routing-and-graph-blueprint.md) | **Intelligent Query Routing & Tabular Cypher Blueprinting** | `QueryRouter` (Vector/Graph/Hybrid), dynamic Cypher generation, dual-path tabular pipeline | `tests/test_store_rag.py`<br>`tests/test_retrieval.py` |

---

## 3. Test Verification Matrix (61 Unit Tests + Kubernetes Smoke Test Suite)

### 3.1. Python Automated Test Suite
The core Python engine is verified by **61 passing unit and integration tests**:

```text
======================= 61 passed in 115.57s =======================
tests/test_api.py (7 passed)
tests/test_evaluation.py (9 passed)
tests/test_indexing.py (5 passed)
tests/test_ingestion.py (8 passed)
tests/test_mcp.py (8 passed)
tests/test_orchestration.py (6 passed)
tests/test_retrieval.py (13 passed)
tests/test_store_rag.py (5 passed)
```

| Test Module | Tests | Specifications Covered | Key Capabilities Verified |
|---|---|---|---|
| `tests/test_ingestion.py` | 8 | Spec 01, Spec 10 | CSV tables, multi-sheet Excel, `.docx` paragraphs, `.txt` chunks, Tesseract OCR text, unsupported extensions, PDF table markdown |
| `tests/test_indexing.py` | 5 | Spec 02, Spec 09, Spec 10 | Qdrant in-memory upsert/search, graph metric & quarter extraction, Neo4j mocked driver, indexer coordinator, document registration & unstructured linking |
| `tests/test_retrieval.py` | 13 | Spec 03, Spec 10 | Context deduplication, top-k limits, graph expansion toggle, relationship query routing, structured store exact matches, empty query safety, BGE cross-encoder reranker sorting/defaults/container caching/env overrides, Neo4j record mapping, 2-hop entity expansion |
| `tests/test_orchestration.py` | 6 | Spec 04, Spec 09 | PII redaction, prompt injection blocking, numerical scale multiplier ($1.2M -> 1.2M), percentage scaling (15.5% vs 0.155), fiscal year recognition, end-to-end LangGraph state flow, Groq & local provider factories |
| `tests/test_mcp.py` | 8 | Spec 05 | Growth rate math, zero-denominator rejection, EBITDA margin calculation, financial search bridge serialization, dashboard structured records filtering, parameterized graph inspection, MCP tool signatures |
| `tests/test_evaluation.py` | 9 | Spec 06 | Fact-grounded faithfulness, Langfuse credential fallback, workflow run without client, mock client tracing, modern v4 observation client tracing, Golden dataset batch evaluation, Pydantic runner compatibility |
| `tests/test_api.py` | 7 | Spec 06, Spec 07, Spec 09 | Public `/api/health`, `/healthz/live`, `/metrics` scrape, CSV `/api/upload`, `/api/chat` response contract, retrieval parameter passing, SSE `/api/chat/stream` token & completion events, prompt injection rejection |
| `tests/test_store_rag.py` | 4 | Spec 09, Spec 10 | Store creation & listing, store-scoped upload & document inventory, short-term conversational memory & clear-chat, QueryRouter classification & dynamic Cypher generation |

### 3.2. Kubernetes Cluster Verification Suite (`scripts/test-k8s.ps1`)
Automated cluster smoke testing executed against the live Kubernetes deployment:
1. **Pod & Service Status**: Validates all 10 pods across all 8 microservices are `1/1 Running`.
2. **Backend Health & DB Connectivity**: Queries `/healthz/live` and `/healthz/ready` (validating Qdrant and Neo4j connectivity).
3. **Multi-Pod Store Synchronization**: Confirms store catalog sync across backend replicas sharing `backend-data-pvc`.
4. **Live RAG Inference**: Dispatches real-time SSE stream query, verifying grounded answer ($84,000) and verified citations.
5. **Observability Reachability**: Confirms Frontend UI (HTTP 200) and Grafana health + pre-provisioned dashboards.

---

## 4. End-to-End Operational Lifecycle

1. **Upload & Ingestion**:
   - Analyst selects or creates a Store (`store_id`) in the frontend sidebar.
   - Uploads financial file via `/api/upload` (multipart form).
   - Ingestion pipeline routes file to parser:
     - Excel/CSV: Dual-path header-injected rows + schema blueprint extraction.
     - PDF: `pdfplumber` extracts tables as Markdown and narrative paragraphs as text.
     - Word/TXT: Paragraph parsing.
     - PNG/JPG: Tesseract OCR extracts receipt items; metadata retained as fallback.
   - Chunks and structured records are created with `store_id` and `doc_id`.
2. **Indexing & Storage**:
   - Dense vectors embedded and upserted to Qdrant collection with `store_id` payload on `qdrant-pvc`.
   - Structured records added to `StructuredFinancialStore`.
   - Graph entities and relationships merged into Neo4j property graph scoped to `(:Store {id: store_id})` on `neo4j-pvc`.
3. **Query & Routing**:
   - Analyst sends a financial question (via `/api/chat` or `/api/chat/stream`).
   - `StoreManager` checks disk mtime for multi-pod synchronization and retrieves the last 6 conversation turns.
   - `QueryRouter` classifies query into `ROUTE_VECTOR`, `ROUTE_GRAPH`, or `ROUTE_HYBRID`.
4. **Execution & Guardrails**:
   - **Input Guard**: Inspects query for PII (redacts) and prompt injections (blocks).
   - **Hybrid Retrieval**: Queries Qdrant (filtered by `store_id`), Neo4j (via Cypher or traversal), and Structured Store. Performs 2-hop entity expansion for causal queries ("grew because", "line item") and reranks with `bge-reranker-base`.
   - **LLM Generation**: Synthesizes answer using grounded contexts and short-term dialogue memory via Groq Cloud API.
   - **Output Guard**: Extracts all numbers and percentages from the response, normalizes scales ($1.2M -> 1,200,000), and validates each against retrieved evidence to eliminate numerical hallucinations.
5. **Delivery & Observability**:
   - Answer, citations, traversed graph nodes, and Power BI-ready dashboard payload are returned or streamed via SSE.
   - Dialogue turn is recorded in `StoreManager` and synced to disk.
   - OpenTelemetry span exported to Tempo; RED metrics recorded in Prometheus; trace hierarchy logged to Langfuse; visualized live in Grafana.
