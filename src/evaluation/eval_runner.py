"""Batch evaluation runner for the guarded orchestration workflow."""

import json
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from .metrics import calculate_context_recall, calculate_faithfulness, calculate_numerical_accuracy


class GoldenTestCase(BaseModel):
    test_id: str
    query: str
    expected_answer: str
    expected_facts: list[str]
    expected_numbers: list[str]
    ground_truth_chunks: list[str]


class EvalRunReport(BaseModel):
    total_test_cases: int
    mean_faithfulness_score: float
    mean_numerical_accuracy: float
    results: list[dict[str, Any]] = Field(default_factory=list)


def load_dataset(path: str | Path) -> list[GoldenTestCase]:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    return [GoldenTestCase.model_validate(item) for item in payload]


class EvaluationRunner:
    def __init__(self, workflow: Any):
        self.workflow = workflow

    def evaluate_case(self, case: GoldenTestCase) -> dict[str, Any]:
        state = self.workflow.invoke({"raw_query": case.query})
        final_output = state.get("final_output") or {}
        answer = final_output.get("answer", "") if isinstance(final_output, dict) else final_output.answer
        contexts = state.get("retrieved_contexts", [])
        metrics = {
            "faithfulness": calculate_faithfulness(case.expected_facts, answer, contexts).score,
            "numerical_accuracy": calculate_numerical_accuracy(case.expected_numbers, answer).score,
            "context_recall": calculate_context_recall(case.ground_truth_chunks, contexts).score,
        }
        return {"test_id": case.test_id, "query": case.query, "answer": answer, "metrics": metrics}

    def run(self, cases: list[GoldenTestCase]) -> EvalRunReport:
        results = [self.evaluate_case(case) for case in cases]
        count = len(results)
        return EvalRunReport(
            total_test_cases=count,
            mean_faithfulness_score=sum(item["metrics"]["faithfulness"] for item in results) / count if count else 0.0,
            mean_numerical_accuracy=sum(item["metrics"]["numerical_accuracy"] for item in results) / count if count else 0.0,
            results=results,
        )


def run_evaluation(workflow: Any, dataset_path: str | Path) -> EvalRunReport:
    return EvaluationRunner(workflow).run(load_dataset(dataset_path))