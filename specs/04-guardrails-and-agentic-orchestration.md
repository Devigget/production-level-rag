# Spec 04: Financial Guardrails & Agentic Orchestration

## 1. Goal & Scope
Build the safety validation layer and the LangGraph-based state machine:
- **Input Guardrail**: Redact sensitive financial PII (credit cards, IBANs, SSNs) and flag common prompt-injection attempts before queries hit the database or LLM.
- **Agentic Orchestration (LangGraph)**: Coordinate a multi-node workflow that executes input checks, performs hybrid retrieval via Spec 03's engine, generates an answer with explicit citations, and validates output numerical fidelity.
- **Output Guardrail**: Extract numbers, currency values, and percentages from the synthesized answer and ensure they exist within the retrieved context to eliminate numerical hallucinations.
- **Structured Output**: Produce typed responses complete with answer text, citation references, safety audit logs, and confidence flags.

## 2. Target File Tree
- `src/orchestration/state.py`                         # LangGraph state schema (TypedDict)
- `src/orchestration/guardrails/input_guard.py`        # PII redaction and injection detection
- `src/orchestration/guardrails/output_guard.py`       # Numerical grounding verification
- `src/orchestration/prompts.py`                      # Financial system prompts and instructions
- `src/orchestration/graph.py`                        # Compiled LangGraph workflow and nodes
- `tests/test_orchestration.py`                       # Test suite for guardrails and execution graph

## 3. Data Contracts & Interfaces
Use Pydantic v2 and Python typing:

```python
from typing import TypedDict, List, Dict, Any, Optional
from pydantic import BaseModel, Field

class GuardrailCheckResult(BaseModel):
    is_safe: bool
    sanitized_text: str
    violations: List[str] = Field(default_factory=list)

class Citation(BaseModel):
    source_id: str
    source_file: str
    snippet: str

class FinancialAnswer(BaseModel):
    query: str
    answer: str
    citations: List[Citation] = Field(default_factory=list)
    numerical_fidelity_passed: bool
    unverified_numbers: List[str] = Field(default_factory=list)

class AgentWorkflowState(TypedDict):
    raw_query: str
    sanitized_query: str
    is_safe: bool
    retrieved_contexts: List[Dict[str, Any]]
    raw_llm_response: str
    final_output: Optional[FinancialAnswer]
    errors: List[str]