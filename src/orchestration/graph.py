"""LangGraph workflow for guarded hybrid financial question answering."""

from collections.abc import Callable
from typing import Any

from .guardrails.input_guard import check_input
from .guardrails.output_guard import verify_numerical_grounding
from .prompts import build_user_prompt
from .state import AgentWorkflowState, Citation, FinancialAnswer


def _as_context_dict(context: Any) -> dict[str, Any]:
    if hasattr(context, "model_dump"):
        return context.model_dump()
    return dict(context)


class _FallbackWorkflow:
    """Small local equivalent used when LangGraph is not installed."""

    def __init__(self, nodes: list[Callable[[AgentWorkflowState], AgentWorkflowState]]):
        self.nodes = nodes

    def invoke(self, state: dict[str, Any]) -> AgentWorkflowState:
        current = dict(state)
        current.setdefault("errors", [])
        current.setdefault("retrieved_contexts", [])
        current.setdefault("final_output", None)
        current.setdefault("raw_llm_response", "")
        current.setdefault("sanitized_query", "")
        for node in self.nodes:
            current = node(current)
            if current.get("is_safe") is False:
                break
        return current


def build_workflow(retrieval_engine: Any, llm_invoker: Callable[[str], str]) -> Any:
    """Build and compile the guarded workflow with injectable dependencies."""

    def input_node(state: AgentWorkflowState) -> AgentWorkflowState:
        result = check_input(state["raw_query"])
        return {**state, "sanitized_query": result.sanitized_text, "is_safe": result.is_safe,
                "errors": [*state.get("errors", []), *result.violations]}

    def retrieve_node(state: AgentWorkflowState) -> AgentWorkflowState:
        result = retrieval_engine.retrieve(state["sanitized_query"])
        contexts = [_as_context_dict(item) for item in result.ranked_contexts]
        return {**state, "retrieved_contexts": contexts}

    def generate_node(state: AgentWorkflowState) -> AgentWorkflowState:
        response = llm_invoker(build_user_prompt(state["sanitized_query"], state["retrieved_contexts"]))
        return {**state, "raw_llm_response": response}

    def output_node(state: AgentWorkflowState) -> AgentWorkflowState:
        check = verify_numerical_grounding(state["raw_llm_response"], state["retrieved_contexts"])
        citations = [Citation(source_id=str(item.get("id", "")),
                              source_file=str(item.get("metadata", {}).get("source_file", "")),
                              snippet=str(item.get("content", "")))
                     for item in state["retrieved_contexts"]]
        answer = FinancialAnswer(query=state["sanitized_query"], answer=state["raw_llm_response"],
                                 citations=citations, numerical_fidelity_passed=check.passed,
                                 unverified_numbers=check.unverified_numbers)
        errors = [*state.get("errors", [])]
        if not check.passed:
            errors.append("unverified_numbers")
        return {**state, "final_output": answer, "errors": errors}

    try:
        from langgraph.graph import END, START, StateGraph

        graph = StateGraph(AgentWorkflowState)
        graph.add_node("input_guard", input_node)
        graph.add_node("retrieve", retrieve_node)
        graph.add_node("generate", generate_node)
        graph.add_node("output_guard", output_node)
        graph.add_edge(START, "input_guard")
        graph.add_conditional_edges("input_guard", lambda state: "retrieve" if state["is_safe"] else END)
        graph.add_edge("retrieve", "generate")
        graph.add_edge("generate", "output_guard")
        graph.add_edge("output_guard", END)
        return graph.compile()
    except ImportError:
        return _FallbackWorkflow([input_node, retrieve_node, generate_node, output_node])


build_graph = build_workflow
create_workflow = build_workflow
