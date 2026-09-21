# Spec 06: Observability & Automated Evaluation Suite

## 1. Goal & Scope
Build tracing telemetry and automated quality evaluation:
- **Observability (Langfuse)**: Trace full execution paths across ingestion, hybrid retrieval, graph extraction, and LangGraph agent runs (capturing latencies, token counts, and step inputs/outputs).
- **Automated Evaluations**: Implement an evaluation harness using structured financial test datasets to measure:
  - Retrieval Context Recall & Precision
  - Faithfulness (grounding against context)
  - Numerical Hallucination Rate
    - Structured-record exact-match accuracy for metric and period queries
    - Dashboard payload validity and source coverage
- **CI/CD Eval Runner**: Provide an automated evaluation runner runnable via command line or GitHub Actions.

## 2. Target File Tree
- `src/evaluation/config.py`           # Langfuse & evaluation harness settings
- `src/evaluation/tracer.py`           # Langfuse tracing client wrapper & decorators
- `src/evaluation/metrics.py`          # Quantitative metrics (faithfulness, precision, hallucination rate)
- `src/evaluation/eval_runner.py`      # Automated evaluation harness
- `data/eval/golden_dataset.json`     # Ground-truth financial Q&A benchmark dataset
- `tests/test_evaluation.py`           # Unit tests for evaluation harness and metric calculations

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