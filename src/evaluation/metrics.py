"""Deterministic metrics for financial retrieval and answer evaluation."""

import re
from collections.abc import Iterable
from decimal import Decimal, InvalidOperation
from typing import Any

from pydantic import BaseModel, Field


class EvalMetricResult(BaseModel):
    metric_name: str
    score: float = Field(ge=0.0, le=1.0)
    details: dict[str, Any] = Field(default_factory=dict)


_NUMBER = re.compile(r"(?<![\w-])(?P<number>\(?\d[\d,]*(?:\.\d+)?\)?)\s*(?P<scale>[KMBkmb])?\s*(?P<percent>%)?")
_WORD = re.compile(r"[a-zA-Z]{3,}")
_STOPWORDS = {"and", "the", "was", "were", "with", "from", "this", "that", "total"}


def _number_values(text: str) -> set[Decimal]:
    values: set[Decimal] = set()
    for match in _NUMBER.finditer(text):
        raw = match.group("number").replace(",", "").replace("(", "-").replace(")", "")
        try:
            value = Decimal(raw)
        except InvalidOperation:
            continue
        scale = {"k": 1_000, "m": 1_000_000, "b": 1_000_000_000}.get((match.group("scale") or "").lower(), 1)
        values.add(value * scale)
    return values


def _contents(contexts: Iterable[Any]) -> str:
    parts = []
    for context in contexts:
        if isinstance(context, str):
            parts.append(context)
        elif hasattr(context, "content"):
            parts.append(str(context.content))
        elif isinstance(context, dict):
            parts.append(str(context.get("content", "")))
    return "\n".join(parts)


def calculate_numerical_accuracy(expected_numbers: list[str], answer: str) -> EvalMetricResult:
    expected = set().union(*(_number_values(item) for item in expected_numbers)) if expected_numbers else set()
    matched = expected & _number_values(answer)
    score = len(matched) / len(expected) if expected else 1.0
    return EvalMetricResult(metric_name="numerical_accuracy", score=score,
                            details={"expected": len(expected), "matched": len(matched)})


def calculate_context_recall(ground_truth_chunks: list[str], contexts: Iterable[Any]) -> EvalMetricResult:
    context_items = [
        item if isinstance(item, str) else str(item.content if hasattr(item, "content") else item.get("content", ""))
        if isinstance(item, dict) or hasattr(item, "content")
        else str(item)
        for item in contexts
    ]
    context_text = "\n".join(context_items).casefold()
    matched = []
    for chunk in ground_truth_chunks:
        normalized_chunk = chunk.casefold()
        if normalized_chunk in context_text:
            matched.append(chunk)
            continue
        chunk_numbers = _number_values(chunk)
        chunk_words = {word.casefold() for word in _WORD.findall(chunk)} - _STOPWORDS
        equivalent = any(
            chunk_numbers & _number_values(context_item)
            and chunk_words & ({word.casefold() for word in _WORD.findall(context_item)} - _STOPWORDS)
            for context_item in context_items
        )
        if equivalent:
            matched.append(chunk)
    score = len(matched) / len(ground_truth_chunks) if ground_truth_chunks else 1.0
    return EvalMetricResult(metric_name="context_recall", score=score, details={"matched_chunks": matched})


def calculate_faithfulness(expected_facts: list[str], answer: str, contexts: Iterable[Any]) -> EvalMetricResult:
    context_text = _contents(contexts).casefold()
    answer_text = answer.casefold()
    supported = [fact for fact in expected_facts if fact.casefold() in context_text and fact.casefold() in answer_text]
    score = len(supported) / len(expected_facts) if expected_facts else 1.0
    return EvalMetricResult(metric_name="faithfulness", score=score, details={"supported_facts": supported})


def numerical_accuracy(expected_numbers: list[str], answer: str) -> float:
    return calculate_numerical_accuracy(expected_numbers, answer).score


def context_recall(ground_truth_chunks: list[str], contexts: Iterable[Any]) -> float:
    return calculate_context_recall(ground_truth_chunks, contexts).score


def faithfulness(expected_facts: list[str], answer: str, contexts: Iterable[Any]) -> float:
    return calculate_faithfulness(expected_facts, answer, contexts).score