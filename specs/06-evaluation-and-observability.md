# Spec 06: Observability & Automated Evaluation Suite

## 1. Goal & Scope
Build the production telemetry, operational monitoring, and automated quality evaluation suite:
- **Distributed Tracing (OpenTelemetry & Tempo)**:
  - Instrument the FastAPI application using OpenTelemetry (`opentelemetry-instrumentation-fastapi`).
  - Propagate W3C trace contexts through request pipelines.
  - Export spans via an OpenTelemetry Collector (`otlp/tempo` exporter) to Tempo (`tempo:4317`) for end-to-end trace visualization in Grafana.
- **Operational Dashboards & Grafana Auto-Provisioning (`k8s/09-observability.yaml`)**:
  - Automatically provision datasources on container startup:
    1. **Financial RAG API** (`yesoreyeram-infinity-datasource` at `http://backend:8000`): Default datasource querying `/api/dashboard/data`.
    2. **Prometheus** (`prometheus` at `http://prometheus:9090`): Metrics timeseries engine.
    3. **Tempo** (`tempo` at `http://tempo:3200`): Distributed trace visualization engine.
  - Automatically provision project dashboards in the **Financial RAG** folder:
    1. **Financial RAG Showcase** ([`financial-rag.json`](file:///grafana/dashboards/financial-rag.json)): Real-time revenue KPIs, grounded record tables, and period bar charts via the Infinity plugin.
    2. **Financial RAG Reliability** ([`observability.json`](file:///grafana/dashboards/observability.json)): 5-minute availability, request rates, p95 latency, and RED metrics by route via Prometheus.
  - Automate plugin installation via `GF_INSTALL_PLUGINS: "yesoreyeram-infinity-datasource"`.
- **Structured JSON Logging**:
  - Format all backend logs as JSON containing `timestamp`, `level`, `logger`, `message`, `service`, `trace_id`, and `span_id` for instant correlation with traces.
- **RED Metrics & Prometheus Exposition**:
  - Track Request Rate, Error Rate, and Duration across endpoints. Expose standard Prometheus text at `/metrics`.
- **Operational Health Probes**:
  - `/healthz/live`: Dependency-free liveness probe for Kubernetes and Docker container health.
  - `/healthz/ready`: Readiness probe verifying live connectivity to Qdrant and Neo4j.
  - `/api/health`: Public application health endpoint.
  - `/api/dashboard/data`: JSON structured financial metrics endpoint for Grafana and BI visualization.
- **SLO Baseline & Triage Alerts**:
  - Target: 99.9% availability and p95 latency below 300 ms over a rolling 30-day window.
  - Alerts configured in `observability/alerts.yml`: Page when 5xx error rate exceeds 2% for 5 minutes or p95 latency exceeds 300 ms for 10 minutes. Alert annotations contain runbook URLs and Tempo trace query filters.
- **Dual-Mode Langfuse Observability (`src/evaluation/tracer.py`)**:
  - Support modern Langfuse v3/v4 OpenTelemetry observation trees (`chain`, `guardrail`, `retriever`, `generation`, `create_score`).
  - Fall back gracefully to legacy client APIs (`trace.span(...)`) or offline execution when unconfigured.
- **Automated Quality Evaluation Harness**:
  - Execute automated benchmark evaluations against `data/eval/golden_dataset.json`.
  - Calculate quantitative metrics: Context Recall, Context Precision, Faithfulness, Numerical Hallucination Rate, and Dashboard Record Validity.

## 2. Target File Tree
- `src/observability.py`                       # OTel configuration, JSON formatter, RED metrics, health probes
- `observability/otel-collector-config.yaml`  # OTel Collector pipeline routing to Tempo & Prometheus
- `observability/prometheus.yml`               # Prometheus scrape configs and alert rule references
- `observability/alerts.yml`                   # SLO error-budget and latency alert definitions
- `observability/tempo.yaml`                    # Local Tempo trace storage configuration
- `grafana/provisioning/datasources/datasource.yml` # Declarative Grafana datasources
- `grafana/provisioning/dashboards/dashboard.yml`   # Declarative Grafana dashboard provider
- `grafana/dashboards/financial-rag.json`      # Financial RAG Showcase dashboard model
- `grafana/dashboards/observability.json`      # Financial RAG Reliability dashboard model
- `k8s/09-observability.yaml`                  # Kubernetes OTel, Tempo, Prometheus, and Grafana manifests
- `src/evaluation/config.py`                    # EvaluationSettings (Langfuse keys, thresholds)
- `src/evaluation/tracer.py`                    # Dual-mode Langfuse tracer with observation trees
- `src/evaluation/metrics.py`                   # Faithfulness, precision, recall, and hallucination scoring
- `src/evaluation/eval_runner.py`               # Automated Golden Dataset test runner
- `data/eval/golden_dataset.json`              # Benchmark dataset of ground-truth financial Q&A pairs
- `tests/test_evaluation.py`                    # 9-test verification suite for metrics and Langfuse tracer
- `tests/test_api.py`                           # Health, readiness, and metrics endpoint test suite

## 3. Data Contracts & Interfaces
Use Pydantic v2:

```python
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field

class GoldenTestCase(BaseModel):
    test_id: str
    query: str
    expected_answer: str
    expected_facts: List[str]
    expected_numbers: List[str]
    ground_truth_chunks: List[str]

class EvalMetricResult(BaseModel):
    metric_name: str
    score: float  # Scale 0.0 to 1.0
    details: Dict[str, Any] = Field(default_factory=dict)

class EvalRunReport(BaseModel):
    total_test_cases: int
    mean_faithfulness_score: float
    mean_numerical_accuracy: float
    results: List[Dict[str, Any]]
```

## 4. Telemetry & Evaluation Architecture

```mermaid
graph TD
    Client[HTTP Client / Frontend] -->|Request| FastAPI[FastAPI Backend]
    
    FastAPI --> Middleware[Observability Middleware]
    Middleware --> MetricsRegistry[Prometheus RED Metrics]
    Middleware --> OTelTracer[OpenTelemetry Tracer]
    
    OTelTracer --> Collector[OTel Collector :4317/:4318]
    Collector -->|otlp/tempo| Tempo[Tempo Trace Storage :3200]
    Collector -->|prometheus| PromExport[Prometheus Exporter :8889]
    
    PromExport --> Prometheus[Prometheus Engine :9090]
    Prometheus --> Alerts[Alertmanager: SLO Rules]
    
    FastAPI --> LangfuseTracer[Langfuse Evaluation Tracer]
    LangfuseTracer -->|Observations & Scores| LangfuseCloud[Langfuse Server / Cloud]
    
    Grafana[Grafana :3001] -->|Prometheus DS| Prometheus
    Grafana -->|Tempo DS| Tempo
    Grafana -->|Infinity DS| FastAPI
```

### 4.1. Grafana Datasource & Dashboard Provisioning
In Kubernetes, all configurations are mounted from ConfigMaps (`grafana-datasources`, `grafana-dashboard-providers`, `grafana-dashboards`):

1. **Infinity Datasource (`financial-rag-api`)**:
   - Proxy requests directly to `http://backend:8000`.
   - Executes queries against `/api/dashboard/data?query=revenue` to populate table records and bar chart visualizations without custom middleware.
2. **Prometheus Datasource (`prometheus`)**:
   - Queries `http://prometheus:9090` for `http_requests_total` and `http_request_duration_seconds_bucket`.
3. **Tempo Datasource (`tempo`)**:
   - Connects to `http://tempo:3200` to visualize distributed traces linked by `trace_id`.

### 4.2. Langfuse Tracing Hierarchies (`src/evaluation/tracer.py`)
Each chat request creates a hierarchical observation tree:
1. `financial-rag-chat` (`as_type="chain"`): Root span recording user query, `store_id`, tags, and duration.
2. `input_guard` (`as_type="guardrail"`): Records raw query, sanitization output, and safety flags.
3. `query_routing` (`as_type="span"`): Records routed path (`VECTOR`, `GRAPH`, `HYBRID`) and routing rationale.
4. `hybrid_retrieval` (`as_type="retriever"`): Records candidates count, context snippets, and similarity scores.
5. `llm_generation` (`as_type="generation"`): Records prompt, model identifier, and raw LLM completion.
6. `output_guard_fidelity` (`as_type="guardrail"`): Records numerical grounding verification pass/fail status and unverified numbers.
7. `create_score`: Logs a `numerical_fidelity` score (`1.0` if passed, `0.0` if unverified numbers remain).

### 4.3. Automated Quality Metrics (`src/evaluation/metrics.py`)
- **Faithfulness**: Proportion of generated statements whose facts exist in both the retrieved context and the expected facts:
  $$\text{Faithfulness} = \frac{|\text{Verified Claims}|}{|\text{Total Claims}|}$$
- **Numerical Hallucination Rate**: Ratio of ungrounded numbers in the answer to total extracted numbers:
  $$\text{Hallucination Rate} = \frac{|\text{Unverified Numbers}|}{|\text{Total Synthesized Numbers}|}$$
- **Context Precision & Recall**: Alignment between retrieved context chunk IDs and ground-truth chunks.

## 5. Verification & Acceptance Criteria
Verified by automated test suites in `tests/test_evaluation.py`, `tests/test_api.py`, and `scripts/test-k8s.ps1`:
1. `tests/test_evaluation.py` (9 tests):
   - `test_faithfulness_requires_facts_in_answer_and_context`: Confirms fact-based grounding scoring.
   - `test_tracer_falls_back_without_credentials`: Confirms graceful startup when Langfuse keys are absent.
   - `test_tracer_workflow_run_graceful_without_client`: Confirms workflow execution when client is None.
   - `test_tracer_workflow_run_with_mock_client`: Confirms legacy client mock tracing.
   - `test_tracer_workflow_run_with_v4_observation_client`: Confirms modern v4 observation tree structure.
   - `test_eval_runner_loads_dataset_and_runs_batch`: Confirms batch execution over `golden_dataset.json`.
   - `test_runner_accepts_pydantic_final_output`: Confirms evaluation report serialization.
2. `tests/test_api.py` (7 tests):
   - `test_health_route`: Confirms public `/api/health` status.
   - `test_liveness_and_metrics_routes`: Confirms `/healthz/live` and Prometheus `/metrics` exposition.
3. Grafana Live Verification (`scripts/test-k8s.ps1`):
   - Health check `/api/datasources/uid/financial-rag-api/health` returns status `OK`.
   - Health check `/api/datasources/uid/prometheus/health` returns status `OK`.
   - Dashboards `Financial RAG Showcase` and `Financial RAG Reliability` loaded and searchable via `/api/search`.