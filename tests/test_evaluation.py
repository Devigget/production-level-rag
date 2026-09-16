from pathlib import Path

from src.evaluation.config import EvaluationSettings
from src.evaluation.eval_runner import EvaluationRunner, GoldenTestCase, load_dataset
from src.evaluation.metrics import (
    calculate_context_recall,
    calculate_faithfulness,
    calculate_numerical_accuracy,
)
from src.evaluation.tracer import Tracer


def test_numerical_accuracy_normalizes_currency_and_scale():
    result = calculate_numerical_accuracy(["$1,200,000", "10.5%"], "Revenue was $1.2M with a 10.5% margin.")

    assert result.score == 1.0


def test_context_recall_is_fraction_of_ground_truth_chunks():
    result = calculate_context_recall(["Revenue was $1,200,000", "Gross margin was 42.5%"],
                                      [{"content": "Revenue was $1,200,000"}])

    assert result.score == 0.5


def test_faithfulness_requires_facts_in_answer_and_context():
    result = calculate_faithfulness(["Revenue was $1,200,000", "Gross margin was 42.5%"],
                                    "Revenue was $1.2M.",
                                    [{"content": "Revenue was $1,200,000. Gross margin was 42.5%."}])

    assert result.score == 0.0


def test_tracer_falls_back_without_credentials():
    tracer = Tracer(EvaluationSettings(langfuse_public_key=None, langfuse_secret_key=None))

    @tracer.trace("local-test")
    def value():
        return 7

    assert not tracer.enabled
    assert value() == 7
    tracer.flush()


def test_eval_runner_loads_dataset_and_runs_batch():
    dataset_path = Path("data/eval/golden_dataset.json")
    cases = load_dataset(dataset_path)

    class FakeWorkflow:
        def invoke(self, state):
            return {
                "final_output": {"answer": "Total revenue was $1.2M."},
                "retrieved_contexts": [{"content": "Total revenue was $1,200,000"}],
            }

    report = EvaluationRunner(FakeWorkflow()).run(cases[:1])

    assert report.total_test_cases == 1
    assert report.mean_numerical_accuracy == 1.0
    assert report.results[0]["metrics"]["context_recall"] == 1.0
    assert len(cases) >= 5


def test_runner_accepts_pydantic_final_output():
    case = GoldenTestCase(test_id="one", query="revenue", expected_answer="Revenue was $1.2M.",
                          expected_facts=["Revenue was $1,200,000"], expected_numbers=["$1,200,000"],
                          ground_truth_chunks=["Revenue was $1,200,000"])

    class FakeOutput:
        answer = "Revenue was $1.2M."

    class FakeWorkflow:
        def invoke(self, state):
            return {"final_output": FakeOutput(), "retrieved_contexts": [{"content": "Revenue was $1,200,000"}]}

    assert EvaluationRunner(FakeWorkflow()).evaluate_case(case)["metrics"]["faithfulness"] == 0.0