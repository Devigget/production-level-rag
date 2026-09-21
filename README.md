# Production-Level Financial RAG

A production-oriented Retrieval-Augmented Generation system for asking grounded questions about financial documents. Users can upload reports through a web interface, have them parsed and indexed, and ask questions whose answers include retrieved source evidence and numerical-grounding checks.

## Setup and Run

The recommended setup uses Docker Compose. It starts the frontend, backend, Qdrant, and Neo4j together, including the Tesseract OCR runtime used for image uploads.

### 1. Prerequisites

Install and start:

- Docker Desktop with Docker Compose
- Git
- At least 4 GB of available memory for the service stack
- An API key for a supported hosted LLM provider

Check Docker before continuing:

```powershell
docker --version
docker compose version
```

### 2. Get the project

```powershell
## Current Status
Set-Location production-level-rag
```

On macOS or Linux, use:

```bash

cd production-level-rag
```

### 3. Configure environment variables

Create a file named `.env` in the repository root. This file is local-only and must not be committed.

Choose one configured provider and supply its key. For example:
The core end-to-end flow is implemented and tested:

```text
Upload document
    -> Parse and normalize
    -> Create FinancialChunk objects and normalized financial records
# Optional alternative provider settings:
# LLM_PROVIDER=nvidia
# NVIDIA_API_KEY=your-key
# NVIDIA_MODEL=google/gemma-4-31b-it
    -> Route to structured retrieval, vector RAG, or optional GraphRAG
    -> Generate a guarded answer and Power BI-ready payload
    -> Verify numerical grounding
    -> Stream answer and expose citations
```

The current test suite passes with **40 tests**. A deprecation warning from the test client may be shown by the installed dependency versions.

The Compose file supplies the internal Qdrant and Neo4j connection defaults, so only the LLM settings are normally required. If no valid LLM key is configured, the backend starts but returns a safe fallback instead of generating answers.

### 4. Build and start the services

| Input | Processing |
| --- | --- |
| `.csv` | Parsed as a financial table |
| `.xlsx` | Each worksheet is parsed as a separate table chunk |
The first build downloads Python, Node, Tesseract, and application dependencies and may take several minutes. Check that all containers are running:

```powershell
docker compose ps
```

Wait until `backend` and `frontend` show `healthy`. Check the backend directly:

```powershell
Invoke-RestMethod http://localhost:8000/api/health
```

Expected result:

```text
status service
------ -------
ok     financial-rag
```

### 5. Open the application

Open the Ledger Lens interface at:
| `.docx` | Non-empty Word paragraphs are extracted as text |
| `.txt` | UTF-8 text is indexed as a searchable chunk |
| `.png`, `.jpg`, `.jpeg` | OCR text is extracted with Tesseract; image metadata is retained as fallback |

Images are optional. OCR is enabled in the Docker image through `tesseract-ocr` and the Python `pytesseract` wrapper.

### 6. Use the application

1. Open http://localhost:3000.
2. Select **Add a report** and upload a CSV, Excel, PDF, Word, TXT, PNG, JPG, or JPEG file.
3. Wait for the indexing status to confirm that chunks were created.
4. Ask a question about the uploaded document, such as `What was revenue in Q2 2025?`.
5. Watch the answer stream into the chat.
6. Select **Inspect evidence** to view source files, snippets, citations, numerical grounding status, and graph traversal details.

The sample file at `data/samples/sample_pnl.csv` is useful for a first test. After uploading it, ask about revenue, operating expenses, or net income.

### Stop and restart

Stop the containers without deleting indexed data:

### Backend
docker compose down
- **FastAPI** exposes the HTTP API.
- **LangGraph** orchestrates input guardrails, retrieval, generation, and output validation.
Start them again later:
- **Neo4j** stores financial entities and relationships.
- **Pydantic** defines API, ingestion, retrieval, and answer contracts.
docker compose up -d

### Retrieval flow


To remove the containers and all persisted indexed data:

```powershell
docker compose down -v
```

Use `down -v` only when you intentionally want to rebuild the document corpus from scratch.

### Troubleshooting

**The frontend does not open:**

```powershell
1. The input guard checks the user query for prompt injection and sensitive data.
2. Vector search finds semantically similar chunks.
```

Confirm that port `3000` is not already used by another application.

**The backend is unhealthy:**

```powershell
3. Graph search finds related financial entities and document relationships.
docker compose logs neo4j
```

Neo4j must become healthy before the backend is fully ready. The first startup can take longer while Neo4j initializes.

**The chat returns a fallback answer:**

Check that `.env` contains a valid supported provider and key, then recreate the backend:

```powershell
4. Duplicate candidates are removed.
```

Never paste API keys into source files, Compose defaults, shell history, or the README.

**An upload is rejected:**

Confirm that the file extension is one of `.csv`, `.xlsx`, `.pdf`, `.docx`, `.txt`, `.png`, `.jpg`, or `.jpeg`. For image files, OCR requires the backend image built from the repository Dockerfile.
5. A reranker orders the remaining contexts.
6. The requested `top_n` controls the final number of contexts.
7. `enable_graph_expansion: false` disables graph retrieval for that request.
8. The language model receives the retrieved context in its prompt.
9. The output guard verifies numerical claims against retrieved context.
10. Citations are returned with source IDs, source files, and snippets.

## Web Interface

The frontend is a Vite-powered React application named **Ledger Lens**.

It includes:

- Chat input for financial questions.
- Incremental streaming assistant responses.
- File upload for supported documents and images.
- Upload/indexing status feedback.
- An evidence drawer with citations and grounding status.
- Graph traversal information when available.

## API

### Health check

```http
GET /api/health
```

Example response:

```json
{
  "status": "ok",
  "service": "financial-rag"
}
```

### Upload a document

```http
POST /api/upload
Content-Type: multipart/form-data
```

PowerShell example:

```powershell
Invoke-RestMethod `
  -Uri http://localhost:8000/api/upload `
  -Method Post `
  -Form @{ file = Get-Item .\data\samples\sample_pnl.csv }
```

The response includes the filename, number of created chunks, and chunk types.

### Standard chat response

```http
POST /api/chat
Content-Type: application/json
```

Request:

```json
{
  "query": "What was revenue in Q2 2025?",
  "top_n": 5,
  "enable_graph_expansion": true
}
```

Response fields include:

- `answer`
- `citations`
- `graph_nodes_traversed`
- `numerical_fidelity_passed`
- `execution_time_ms`

### Streaming chat response

```http
POST /api/chat/stream
Content-Type: application/json
Accept: text/event-stream
```

The endpoint emits Server-Sent Events:

- `token` events contain incremental answer text.
- The final `complete` event contains the complete answer, citations, grounding status, and execution metadata.

The existing `/api/chat` endpoint remains available for clients that require one JSON response.

## Running Locally with Docker

### Prerequisites

- Docker Desktop with Compose
- An LLM provider key, if using a hosted model
- At least 4 GB of available memory for the service stack

### Configuration

Create a local `.env` file. Do not commit it.

Example:

```env
LLM_PROVIDER=gemini
GEMINI_API_KEY=your-key
GEMINI_MODEL=gemini-2.5-flash

# Or use another configured provider where supported.
# GROQ_API_KEY=your-key
# GROQ_MODEL=llama-3.1-8b-instant

QDRANT_URL=http://qdrant:6333
NEO4J_URI=bolt://neo4j:7687
NEO4J_USER=neo4j
NEO4J_PASSWORD=production_password
```

Start the stack:

```powershell
docker compose up -d --build
```

Open the application at:

- Frontend: http://localhost:3000
- Backend health: http://localhost:8000/api/health
- Qdrant: http://localhost:6333
- Neo4j browser: http://localhost:7474

Check service status:

```powershell
docker compose ps
```

Stop the stack:

```powershell
docker compose down
```

The Qdrant and Neo4j volumes are named `qdrant_storage` and `neo4j_data`, so indexed data persists across normal container restarts.

## Running Tests

Run the full Python test suite:

```powershell
python -m pytest -q
```

Run focused tests:

```powershell
python -m pytest tests/test_ingestion.py -q
python -m pytest tests/test_api.py tests/test_retrieval.py -q
python -m pytest tests/test_evaluation.py tests/test_orchestration.py -q
```

Build the frontend:

```powershell
Push-Location frontend
npm install
npm run build
Pop-Location
```

Run the evaluation dataset through the configured workflow:

```powershell
python -m src.evaluation.eval_runner
```

The evaluation runner reports faithfulness, numerical accuracy, and context recall for the cases in `data/eval/golden_dataset.json`.

## Project Layout

```text
.
├── data/
│   ├── eval/                 Golden evaluation dataset
│   └── samples/              Sample financial inputs
├── frontend/
│   └── src/                  React application and UI components
├── src/
│   ├── api/                  FastAPI routes and schemas
│   ├── evaluation/           Metrics, tracing, and evaluation runner
│   ├── indexing/              Qdrant and Neo4j indexing
│   ├── ingestion/             File parsers and OCR
│   ├── mcp/                   MCP server and tools
│   ├── orchestration/         LangGraph workflow and guardrails
│   └── retrieval/              Hybrid retrieval and reranking
├── tests/                    Automated backend tests
├── docker-compose.yml        Local multi-service deployment
├── Dockerfile                Backend image with Tesseract OCR
├── requirements.txt          Python dependencies
└── PROJECT_PROGRESS.md       Earlier implementation notes
```

## Important Configuration Notes

- The backend falls back to an empty retrieval engine when Qdrant is configured for in-memory mode or when external indexing dependencies cannot be initialized.
- The default offline embedder is deterministic and hash-based. A production embedding model can be injected through the vector-store abstraction.
- The current chat generation is provider-dependent. Without a configured API key, the application uses a safe fallback response rather than inventing financial facts.
- Uploaded files are temporarily written for parsing and then removed. The indexed representations remain in Qdrant and Neo4j.

## Production Follow-Ups

The main application path is working, but the following areas are worth tightening before a high-volume production deployment:

- Remove duplicate historical uploads from persistent Qdrant and Neo4j data.
- Add document-level deduplication and idempotent upload handling.
- Improve retrieval latency and avoid unnecessary model initialization per process.
- Use a production-grade embedding model and configure model caching.
- Add authentication, authorization, rate limiting, and upload-size limits.
- Add structured application logging, request tracing, and metrics dashboards.
- Expand OCR support for rotated, low-resolution, and handwriting-heavy images.
- Add full end-to-end browser tests for upload, streaming, and citation inspection.

## License and Secrets

Keep API keys and passwords in `.env` or a deployment secret manager. Never commit credentials, generated indexes, or local environment files to source control.
