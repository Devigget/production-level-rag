"""Demonstration script for Langfuse LLM Observability in Financial RAG.

Usage:
    python scripts/demo_langfuse.py
"""

import os
import sys
from pathlib import Path

# Add project root to sys.path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.evaluation.config import EvaluationSettings
from src.evaluation.tracer import get_tracer


def main():
    print("=" * 60)
    print(" FINANCIAL RAG - LANGFUSE OBSERVABILITY DEMO")
    print("=" * 60)

    settings = EvaluationSettings()
    tracer = get_tracer(settings)

    print("\n1. Langfuse Status:")
    print(f"   - Tracing Enabled: {tracer.enabled}")
    print(f"   - Langfuse Host:   {settings.langfuse_host}")
    print(f"   - Public Key Set:  {bool(settings.langfuse_public_key)}")

    # Sample query and execution result simulating an end-to-end RAG chat
    sample_query = "What was the revenue in Q2 2025 and why did it increase?"
    sample_result = {
        "is_safe": True,
        "sanitized_query": sample_query,
        "errors": [],
        "retrieved_contexts": [
            {
                "id": "pnl.csv:Revenue:Q2_2025",
                "content": "Metric: Revenue | Period: Q2 2025 | Value: $1,450,000",
                "initial_score": 0.94,
                "metadata": {"source_file": "pnl.csv", "period": "Q2 2025"},
            },
            {
                "id": "management_notes.txt:chunk-0",
                "content": "Revenue grew due to seasonal coffee promotion and high pastry demand in June.",
                "initial_score": 0.88,
                "metadata": {"source_file": "management_notes.txt"},
            },
        ],
        "raw_llm_response": (
            "According to the financial statements, revenue in Q2 2025 was $1,450,000 [Doc: pnl.csv:Revenue:Q2_2025]. "
            "It increased primarily due to the seasonal coffee promotion and strong food sales in June [Doc: management_notes.txt:chunk-0]."
        ),
    }

    class MockAnswer:
        answer = sample_result["raw_llm_response"]
        numerical_fidelity_passed = True
        unverified_numbers = []

    sample_result["final_output"] = MockAnswer()

    print("\n2. Simulating End-to-End Tracing Execution:")
    print("   Observation Hierarchy & Types:")
    print("   |-- Root (Chain): financial-rag-chat")
    print("   |   |-- Guardrail: input_guard (PII check & Prompt Injection scan)")
    print("   |   |-- Span:      query_routing (Dynamic Hybrid / Vector / Graph routing)")
    print("   |   |-- Retriever: hybrid_retrieval (Qdrant vector chunks + Neo4j entities)")
    print("   |   |-- Generation: llm_generation (Model, prompt tokens, completion)")
    print("   |   +-- Guardrail: output_guard_fidelity (Decimal & arithmetic verification)")
    print("   +-- Metric Score:  numerical_fidelity (1.0 = Grounded, 0.0 = Hallucinated)")

    if tracer.enabled:
        print("\n3. Sending Live Trace to Langfuse Cloud...")
        trace_id = tracer.trace_workflow_run(
            query=sample_query,
            result=sample_result,
            store_id="default",
            route_used="HYBRID",
            execution_time_ms=1240.5,
        )
        print("   [SUCCESS] Live trace sent!")
        if trace_id:
            print(f"   - Trace ID:    {trace_id}")
            print("   - Session ID:  store-default")
            print(f"   - Environment: {settings.langfuse_environment}")
        print(f"   - Dashboard:   {settings.langfuse_host}")

    else:
        print("\n3. No Langfuse API keys detected in .env.")
        print("   The RAG application automatically runs in fallback mode without crashing.")
        print("\n   To connect live traces to Langfuse Cloud for free:")
        print("   1. Sign up for free at https://cloud.langfuse.com")
        print("   2. Create a project and copy your API keys.")
        print("   3. Add them to your .env file:")
        print("      LANGFUSE_PUBLIC_KEY=pk-lf-...")
        print("      LANGFUSE_SECRET_KEY=sk-lf-...")
        print("      LANGFUSE_HOST=https://cloud.langfuse.com")
        print("   4. Re-run this script or use the chat interface!")

    print("\n" + "=" * 60)


if __name__ == "__main__":
    main()
