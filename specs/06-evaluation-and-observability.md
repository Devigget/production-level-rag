# Spec 06: Observability & Automated Evaluation Suite

## 1. Goal & Scope
Build production telemetry and automated quality evaluation:
- **Distributed tracing (OpenTelemetry)**: Instrument FastAPI and downstream clients, propagate W3C trace context, and export spans through an OpenTelemetry Collector to Tempo.
- **Structured logs**: Emit JSON logs with `service`, `trace_id`, and `span_id` fields so every request can be correlated with a trace.
- **RED metrics**: Record request rate, error rate, and duration by method, normalized route, and status code. Expose Prometheus text at `/metrics`.
- **Probes**: Keep `/healthz/live` dependency-free for liveness and use `/healthz/ready` for Qdrant and Neo4j readiness. Preserve `/api/health` as the public application health contract.
- **SLO baseline**: Track 99.9% availability and p95 latency below 300 ms over a rolling 30-day window. Page on error rate above 2% for 5 minutes or p95 above 300 ms for 10 minutes.
- **Telemetry routing**: Compose runs the Collector, Prometheus, Tempo, and Grafana. Prometheus rules include runbook URLs and exact trace filters in alert annotations.
- **Evaluation tracing (Langfuse)**: Keep the optional evaluation adapter for quality runs; it is separate from request telemetry and remains credential-gated.
- **Automated Evaluations**: Implement an evaluation harness using structured financial test datasets to measure:
  - Retrieval Context Recall & Precision
  - Faithfulness (grounding against context)
  - Numerical Hallucination Rate
    - Structured-record exact-match accuracy for metric and period queries
    - Dashboard payload validity and source coverage
- **CI/CD Eval Runner**: Provide an automated evaluation runner runnable via command line or GitHub Actions.

## 2. Target File Tree
- `src/observability.py`              # OTel bootstrap, JSON logging, RED metrics, and probes
- `observability/otel-collector-config.yaml` # OTLP receiver and Tempo/Prometheus exporters
- `observability/prometheus.yml`      # Scrape and rule configuration
- `observability/alerts.yml`          # SLO/error budget alerts with triage metadata
- `observability/tempo.yaml`           # Local trace storage configuration
- `src/evaluation/config.py`           # Langfuse & evaluation harness settings
- `src/evaluation/tracer.py`           # Langfuse tracing client wrapper & decorators
- `src/evaluation/metrics.py`          # Quantitative metrics (faithfulness, precision, hallucination rate)
- `src/evaluation/eval_runner.py`      # Automated evaluation harness
- `data/eval/golden_dataset.json`     # Ground-truth financial Q&A benchmark dataset
- `tests/test_evaluation.py`           # Unit tests for evaluation harness and metric calculations
- `tests/test_api.py`                  # Health and metrics endpoint coverage

## 3. Data Contracts & Interfaces
Use Pydantic v2:

```python
from pydantic import BaseModel, Field
from typing import List, Dict, Any, Optional

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