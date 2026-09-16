"""Typed state and structured responses used by the orchestration graph."""

from typing import Any, Optional, TypedDict

from pydantic import BaseModel, Field


class GuardrailCheckResult(BaseModel):
    is_safe: bool
    sanitized_text: str
    violations: list[str] = Field(default_factory=list)


class Citation(BaseModel):
    source_id: str
    source_file: str
    snippet: str


class FinancialAnswer(BaseModel):
    query: str
    answer: str
    citations: list[Citation] = Field(default_factory=list)
    numerical_fidelity_passed: bool
    unverified_numbers: list[str] = Field(default_factory=list)


class AgentWorkflowState(TypedDict):
    raw_query: str
    sanitized_query: str
    is_safe: bool
    retrieved_contexts: list[dict[str, Any]]
    raw_llm_response: str
    final_output: Optional[FinancialAnswer]
    errors: list[str]
