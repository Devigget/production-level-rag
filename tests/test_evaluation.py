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


def test_tracer_workflow_run_graceful_without_client():
    tracer = Tracer(EvaluationSettings(langfuse_public_key=None, langfuse_secret_key=None))
    # Should not raise exception
    tracer.trace_workflow_run(
        query="What was revenue?",
        result={"sanitized_query": "What was revenue?", "is_safe": True, "raw_llm_response": "$1.2M", "retrieved_contexts": []},
        store_id="default",
    )


def test_tracer_workflow_run_with_mock_client():
    from unittest.mock import MagicMock
    mock_client = MagicMock()
    mock_trace = MagicMock()
    mock_client.trace.return_value = mock_trace

    tracer = Tracer(client=mock_client)
    tracer.trace_workflow_run(
        query="What was revenue?",
        result={
            "sanitized_query": "What was revenue?",
            "is_safe": True,
            "raw_llm_response": "$1.2M in Q1 2025",
            "retrieved_contexts": [{"id": "chunk-1", "content": "Revenue: $1.2M in Q1 2025"}],
        },
        store_id="store-123",
        route_used="HYBRID",
        execution_time_ms=120.5,
    )

    mock_client.trace.assert_called_once()
    assert mock_trace.span.call_count >= 2  # input_guard, hybrid_retrieval, output_guard
    mock_trace.generation.assert_called_once()
    mock_trace.score.assert_called_once()


def test_tracer_workflow_run_with_v4_observation_client():
    from unittest.mock import MagicMock
    mock_client = MagicMock(spec=["start_as_current_observation", "flush", "create_score", "get_current_trace_id"])
    mock_obs = MagicMock()
    mock_obs.trace_id = "test-trace-id-123"
    mock_client.start_as_current_observation.return_value.__enter__.return_value = mock_obs
    mock_client.get_current_trace_id.return_value = "test-trace-id-123"

    tracer = Tracer(client=mock_client)
    trace_id = tracer.trace_workflow_run(
        query="What was revenue?",
        result={
            "sanitized_query": "What was revenue?",
            "is_safe": True,
            "raw_llm_response": "$1.2M in Q1 2025",
            "retrieved_contexts": [{"id": "chunk-1", "content": "Revenue: $1.2M in Q1 2025"}],
        },
        store_id="store-123",
        route_used="HYBRID",
        execution_time_ms=120.5,
    )

    assert trace_id == "test-trace-id-123"
    assert mock_client.start_as_current_observation.call_count >= 4
    mock_client.create_score.assert_called_once()
    assert mock_client.flush.call_count >= 1




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