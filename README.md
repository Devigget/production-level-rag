# Production-Level Financial RAG

A production-oriented Retrieval-Augmented Generation system for asking grounded questions about financial documents. Users can upload reports through a web interface, have them parsed and indexed, and ask questions whose answers include retrieved source evidence and numerical-grounding checks.

## What It Does

- Accepts CSV, Excel, PDF, Word, plain-text, and image files.
- Extracts tables, document text, Word paragraphs, and OCR text from images.
- Indexes uploaded content in both Qdrant and Neo4j.
- Combines vector retrieval, graph retrieval, and reranking.
- Uses guarded orchestration for input safety and numerical grounding.
- Provides a React chat interface with streaming responses.
- Displays source citations and retrieved snippets in an evidence drawer.
- Supports evaluation against a golden financial QA dataset.

The system is designed to answer from retrieved document context rather than relying only on the language model's general knowledge. When context is insufficient, the answer-generation prompt instructs the model to say so instead of guessing.

## Current Status

The core end-to-end flow is implemented and tested:

```text
Upload document
    -> Parse and normalize
    -> Create FinancialChunk objects
    -> Index in Qdrant and Neo4j visualization
    -> Retrieve relevant vector and graph context
    -> Rerank candidates
    -> Generate a guarded answer
    -> Verify numerical grounding
    -> Stream answer and expose citations
```

The current test suite passes with **40 tests**. A deprecation warning from the test client may be shown by the installed dependency versions.

## Supported Inputs

| Input | Processing |
| --- | --- |
| `.csv` | Parsed as a financial table |
| `.xlsx` | Each worksheet is parsed as a separate table chunk |
| `.pdf` | Tables and page text are extracted with page metadata |
| `.docx` | Non-empty Word paragraphs are extracted as text |
| `.txt` | UTF-8 text is indexed as a searchable chunk |
| `.png`, `.jpg`, `.jpeg` | OCR text is extracted with Tesseract; image metadata is retained as fallback |

Images are optional. OCR is enabled in the Docker image through `tesseract-ocr` and the Python `pytesseract` wrapper.

## Architecture

### Backend

- **FastAPI** exposes the HTTP API.
- **LangGraph** orchestrates input guardrails, retrieval, generation, and output validation.
- **Qdrant** stores dense vectors and serialized financial chunks.
- **Neo4j** stores financial entities and relationships.
- **Pydantic** defines API, ingestion, retrieval, and answer contracts.
- **Pandas**, `openpyxl`, `pdfplumber`, `python-docx`, Pillow, and Tesseract handle document processing.

### Retrieval flow

1. The input guard checks the user query for prompt injection and sensitive data.
2. Vector search finds semantically similar chunks.
3. Graph search finds related financial entities and document relationships.
4. Duplicate candidates are removed.
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
