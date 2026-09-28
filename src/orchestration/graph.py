"""LangGraph workflow for guarded hybrid financial question answering with store isolation and memory."""

import os
import logging
from collections.abc import Callable
from typing import Any

from dotenv import load_dotenv

from .guardrails.input_guard import check_input
from .guardrails.output_guard import verify_numerical_grounding
from .prompts import build_user_prompt
from src.retrieval.models import RetrievalQuery
from src.retrieval.router import QueryRouter, ROUTE_GRAPH, ROUTE_HYBRID, ROUTE_VECTOR
from .state import AgentWorkflowState, Citation, FinancialAnswer

logger = logging.getLogger(__name__)


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
    router = QueryRouter(llm_invoker=llm_invoker)

    def input_node(state: AgentWorkflowState) -> AgentWorkflowState:
        result = check_input(state["raw_query"])
        if not result.is_safe:
            logger.warning("guardrail_blocked violations=%s", ",".join(result.violations))
        return {**state, "sanitized_query": result.sanitized_text, "is_safe": result.is_safe,
                "errors": [*state.get("errors", []), *result.violations]}

    def route_node(state: AgentWorkflowState) -> AgentWorkflowState:
        route, reasoning = router.route_query(state["sanitized_query"])
        return {**state, "retrieval_route": route, "router_reasoning": reasoning}

    def retrieve_node(state: AgentWorkflowState) -> AgentWorkflowState:
        store_id = state.get("store_id")
        route = state.get("retrieval_route", ROUTE_HYBRID)

        if "top_n" not in state and "enable_graph_expansion" not in state and not store_id:
            result = retrieval_engine.retrieve(state["sanitized_query"])
        else:
            top_k_graph = 0 if route == ROUTE_VECTOR else (10 if state.get("enable_graph_expansion", True) else 0)
            top_k_vector = 0 if route == ROUTE_GRAPH else 10
            retrieval_query = RetrievalQuery(
                query_text=state["sanitized_query"],
                store_id=store_id or "default",
                final_top_n=state.get("top_n", 5),
                top_k_vector=top_k_vector or 10,
                top_k_graph=top_k_graph,
                filters={"store_id": store_id} if store_id else None,
                retrieval_mode=("auto" if state.get("enable_graph_expansion", True) else "structured_vector"),
            )
            result = retrieval_engine.retrieve(retrieval_query)

        contexts = [_as_context_dict(item) for item in result.ranked_contexts]
        return {**state, "retrieved_contexts": contexts}

    def generate_node(state: AgentWorkflowState) -> AgentWorkflowState:
        prompt = build_user_prompt(
            query=state["sanitized_query"],
            contexts=state["retrieved_contexts"],
            store_name=state.get("store_name"),
            chat_history=state.get("chat_history"),
        )
        try:
            response = llm_invoker(prompt)
        except Exception as exc:
            logger.warning("llm_invoke_failed error=%s", exc)
            response = "I could not find supporting financial context for that question."
        return {**state, "raw_llm_response": response}

    def output_node(state: AgentWorkflowState) -> AgentWorkflowState:
        check = verify_numerical_grounding(state["raw_llm_response"], state["retrieved_contexts"])
        citations = [Citation(source_id=str(item.get("id", "")),
                              source_file=str(item.get("metadata", {}).get("source_file", "")),
                              snippet=str(item.get("content", "")))
                     for item in state["retrieved_contexts"]]
        answer = FinancialAnswer(
            query=state["sanitized_query"],
            answer=state["raw_llm_response"],
            citations=citations,
            numerical_fidelity_passed=check.passed,
            unverified_numbers=check.unverified_numbers,
            route_used=state.get("retrieval_route", ROUTE_HYBRID),
            store_id=state.get("store_id", "default"),
        )
        errors = [*state.get("errors", [])]
        if not check.passed:
            errors.append("unverified_numbers")
            logger.warning("grounding_failed unverified_count=%d", len(check.unverified_numbers))
        return {**state, "final_output": answer, "errors": errors}

    try:
        from langgraph.graph import END, START, StateGraph

        graph = StateGraph(AgentWorkflowState)
        graph.add_node("input_guard", input_node)
        graph.add_node("route", route_node)
        graph.add_node("retrieve", retrieve_node)
        graph.add_node("generate", generate_node)
        graph.add_node("output_guard", output_node)
        graph.add_edge(START, "input_guard")
        graph.add_conditional_edges("input_guard", lambda state: "route" if state["is_safe"] else END)
        graph.add_edge("route", "retrieve")
        graph.add_edge("retrieve", "generate")
        graph.add_edge("generate", "output_guard")
        graph.add_edge("output_guard", END)
        return graph.compile()
    except ImportError:
        return _FallbackWorkflow([input_node, route_node, retrieve_node, generate_node, output_node])


build_graph = build_workflow
create_workflow = build_workflow


class GeminiLLMInvoker:
    """Callable Gemini adapter used by the workflow's generation node."""

    def __init__(self, api_key: str, model: str = "gemini-3.5-flash"):
        from google import genai

        self.model = model
        self.client = genai.Client(api_key=api_key)

    def __call__(self, prompt: str) -> str:
        models_to_try = [self.model, "gemini-3.5-flash", "gemini-flash-latest"]
        last_exc = None
        for m in dict.fromkeys(models_to_try):
            try:
                response = self.client.models.generate_content(model=m, contents=prompt)
                if response.text:
                    return response.text
            except Exception as exc:
                last_exc = exc
                logger.warning("gemini_api_call_failed model=%s error=%s", m, exc)
        logger.warning("all_gemini_models_failed last_error=%s", last_exc)
        return "I could not find supporting financial context for that question."


class NvidiaLLMInvoker:
    """Callable adapter for NVIDIA's OpenAI-compatible inference endpoint."""

    def __init__(self, api_key: str, model: str):
        import httpx

        self.model = model
        self.client = httpx.Client(
            base_url="https://integrate.api.nvidia.com/v1",
            headers={"Authorization": f"Bearer {api_key}", "Accept": "application/json"},
            timeout=60.0,
        )

    def __call__(self, prompt: str) -> str:
        try:
            response = self.client.post(
                "/chat/completions",
                json={
                    "model": self.model,
                    "messages": [
                        {"role": "system", "content": "You are a helpful financial RAG assistant. Answer only from the provided context."},
                        {"role": "user", "content": prompt},
                    ],
                    "max_tokens": 3000,
                    "temperature": 0.0,
                    "top_p": 1.0,
                    "stream": False,
                },
            )
            if response.is_error:
                logger.error("nvidia_api_error status=%d body=%s", response.status_code, response.text)
                return "I could not find supporting financial context for that question."
            return response.json()["choices"][0]["message"]["content"] or ""
        except Exception as exc:
            logger.warning("nvidia_api_call_failed: %s", exc)
            return "I could not find supporting financial context for that question."


class GroqLLMInvoker:
    """Callable Groq adapter using its OpenAI-compatible chat endpoint."""

    def __init__(self, api_key: str, model: str):
        import httpx

        self.model = model
        self.client = httpx.Client(
            base_url="https://api.groq.com/openai/v1",
            headers={"Authorization": f"Bearer {api_key}", "Accept": "application/json"},
            timeout=60.0,
        )

    def __call__(self, prompt: str) -> str:
        try:
            response = self.client.post(
                "/chat/completions",
                json={
                    "model": self.model,
                    "messages": [
                        {"role": "system", "content": "You are a helpful financial RAG assistant. Answer only from the provided context."},
                        {"role": "user", "content": prompt},
                    ],
                    "max_tokens": 3000,
                    "temperature": 0.0,
                    "stream": False,
                },
            )
            if response.is_error:
                logger.error("groq_api_error status=%d body=%s", response.status_code, response.text)
                return "I could not find supporting financial context for that question."
            return response.json()["choices"][0]["message"]["content"] or ""
        except Exception as exc:
            logger.warning("groq_api_call_failed: %s", exc)
            return "I could not find supporting financial context for that question."


class LocalHuggingFaceLLMInvoker:
    """Callable adapter for local Hugging Face CausalLM models (e.g., Qwen2.5-1.5B-Instruct)."""

    def __init__(
        self,
        model_path: str | None = None,
        device: str | None = None,
        max_new_tokens: int = 1024,
    ):
        target_path = (
            model_path
            or os.getenv("LOCAL_LLM_MODEL_PATH")
            or "/models/llm/Qwen2.5-1.5B-Instruct"
        )
        if target_path == "/models/llm/Qwen2.5-1.5B-Instruct" and not os.path.exists(target_path):
            host_path = os.getenv(
                "LOCAL_LLM_HOST_PATH",
                r"C:\Users\VigneshPandurangGaun\OneDrive - McLaren Strategic Solutions US Inc\Documents\models\llm\Qwen2.5-1.5B-Instruct",
            )
            if host_path and os.path.exists(host_path):
                target_path = host_path

        self.model_path = target_path
        env_max = os.getenv("LOCAL_LLM_MAX_NEW_TOKENS")
        self.max_new_tokens = int(env_max) if env_max and env_max.isdigit() else max_new_tokens
        self._target_device = device
        self.tokenizer = None
        self.model = None
        self.device = None

    def _ensure_loaded(self) -> None:
        if self.model is not None and self.tokenizer is not None:
            return

        import torch
        from transformers import AutoModelForCausalLM, AutoTokenizer

        target_dev = self._target_device or os.getenv("LOCAL_LLM_DEVICE", "auto")
        if target_dev.lower() == "auto":
            self.device = "cuda" if torch.cuda.is_available() else "cpu"
        else:
            self.device = target_dev.lower()

        logger.info(
            "loading_local_llm path=%s device=%s max_new_tokens=%d",
            self.model_path,
            self.device,
            self.max_new_tokens,
        )
        self.tokenizer = AutoTokenizer.from_pretrained(self.model_path)
        torch_dtype = torch.bfloat16 if self.device == "cpu" else torch.float16
        try:
            self.model = AutoModelForCausalLM.from_pretrained(
                self.model_path,
                torch_dtype=torch_dtype,
                low_cpu_mem_usage=True,
            ).to(self.device)
        except Exception:
            self.model = AutoModelForCausalLM.from_pretrained(
                self.model_path,
                torch_dtype="auto",
                low_cpu_mem_usage=True,
            ).to(self.device)
        self.model.eval()

    def __call__(self, prompt: str) -> str:
        import torch

        try:
            self._ensure_loaded()
            messages = [
                {
                    "role": "system",
                    "content": "You are a helpful financial RAG assistant. Answer only from the provided context.",
                },
                {"role": "user", "content": prompt},
            ]
            inputs = self.tokenizer.apply_chat_template(
                messages,
                tokenize=True,
                add_generation_prompt=True,
                return_tensors="pt",
                return_dict=True,
            )
            inputs = {k: v.to(self.device) for k, v in inputs.items()}
            with torch.no_grad():
                outputs = self.model.generate(
                    **inputs,
                    max_new_tokens=self.max_new_tokens,
                    do_sample=False,
                )
            generated_tokens = outputs[0][inputs["input_ids"].shape[1] :]
            text = self.tokenizer.decode(generated_tokens, skip_special_tokens=True)
            return text.strip()
        except Exception as exc:
            logger.warning("local_llm_generation_failed: %s", exc)
            return "I could not find supporting financial context for that question."


LocalLLMInvoker = LocalHuggingFaceLLMInvoker


def create_llm_invoker() -> Callable[[str], str]:
    """Create the configured LLM invoker, retaining an offline fallback."""
    load_dotenv()
    provider = os.getenv("LLM_PROVIDER", "gemini").lower()
    if provider in ("local", "huggingface", "qwen"):
        try:
            logger.info("llm_provider_selected provider=local model=Qwen2.5-1.5B-Instruct")
            return LocalHuggingFaceLLMInvoker()
        except Exception as exc:
            logger.warning("local_llm_provider_init_failed: %s", exc)
            return lambda _: "I could not find supporting financial context for that question."
    if provider == "groq":
        api_key = os.getenv("GROQ_API_KEY")
        if api_key:
            logger.info("llm_provider_selected provider=groq model=%s", os.getenv("GROQ_MODEL", "openai/gpt-oss-120b"))
            return GroqLLMInvoker(api_key, os.getenv("GROQ_MODEL", "openai/gpt-oss-120b"))
        logger.warning("llm_provider_missing_api_key provider=groq")
        return lambda _: "I could not find supporting financial context for that question."
    if provider == "nvidia":
        api_key = os.getenv("NVIDIA_API_KEY")
        if api_key:
            logger.info("llm_provider_selected provider=nvidia model=%s", os.getenv("NVIDIA_MODEL", "google/gemma-4-31b-it"))
            return NvidiaLLMInvoker(api_key, os.getenv("NVIDIA_MODEL", "google/gemma-4-31b-it"))
        return lambda _: "I could not find supporting financial context for that question."

    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        return lambda _: "I could not find supporting financial context for that question."
    try:
        model_name = os.getenv("GEMINI_MODEL", "gemini-3.5-flash")
        logger.info("llm_provider_selected provider=gemini model=%s", model_name)
        gemini_invoker = GeminiLLMInvoker(api_key, model_name)

        def _resilient_gemini_invoker(prompt: str) -> str:
            res = gemini_invoker(prompt)
            if res and res != "I could not find supporting financial context for that question.":
                return res
            try:
                logger.info("falling_back_to_local_llm")
                local_invoker = LocalHuggingFaceLLMInvoker()
                return local_invoker(prompt)
            except Exception as exc:
                logger.warning("fallback_local_llm_failed: %s", exc)
                return res

        return _resilient_gemini_invoker
    except ImportError:
        return lambda _: "I could not find supporting financial context for that question."
