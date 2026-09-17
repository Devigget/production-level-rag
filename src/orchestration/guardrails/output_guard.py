"""Numerical grounding checks for generated financial answers."""

import re
from decimal import Decimal, InvalidOperation
from typing import Any

from pydantic import BaseModel, Field


class NumericalGroundingResult(BaseModel):
    passed: bool
    unverified_numbers: list[str] = Field(default_factory=list)


# Symmetrical word/boundary checks, allowing numbers following prefixes like "Q1_" or "FY"
_NUMBER = re.compile(
    r"(?<![a-zA-Z0-9])"
    r"(?P<currency>[$€£])?\s*"
    r"(?P<number>\(?\d{1,3}(?:,\d{3})*(?:\.\d+)?\)?|\(?\d+(?:\.\d+)?\)?)"
    r"\s*(?P<scale>[KMBkmb])?\s*(?P<percent>%)?"
    r"(?![a-zA-Z0-9])"
)

# Strip out bracketed citations [Doc: 123] before running validation
_CITATION_PATTERN = re.compile(r"\[.*?\]")


def _is_calendar_year(value: Decimal) -> bool:
    return value == value.to_integral_value() and 1900 <= value <= 2100


def _normalized_numbers(text: str) -> set[Decimal]:
    values: set[Decimal] = set()
    # Normalize markdown bolding/italics and underscores so tokens like Q1_2025 decouple into 2025
    clean_text = text.replace("*", " ").replace("_", " ")

    for match in _NUMBER.finditer(clean_text):
        raw = match.group("number").replace(",", "").replace("(", "-").replace(")", "")
        try:
            value = Decimal(raw)
        except InvalidOperation:
            continue
        scale = {"k": 1_000, "m": 1_000_000, "b": 1_000_000_000}.get(
            (match.group("scale") or "").lower(), 1
        )
        values.add(value * scale)
    return values


def verify_numerical_grounding(answer: str, contexts: list[Any]) -> NumericalGroundingResult:
    context_parts: list[str] = []
    for item in contexts:
        if isinstance(item, str):
            context_parts.append(item)
        elif hasattr(item, "content"):
            context_parts.append(str(item.content))
        elif isinstance(item, dict):
            context_parts.append(str(item.get("content", "")))
        else:
            context_parts.append(str(item))

    context_text = "\n".join(context_parts)
    context_values = _normalized_numbers(context_text)

    # Strip bracketed citations from the answer to prevent false positives from file hashes/IDs
    cleaned_answer = _CITATION_PATTERN.sub("", answer).replace("*", " ").replace("_", " ")

    unverified: list[str] = []
    for match in _NUMBER.finditer(cleaned_answer):
        raw_token = match.group(0).strip()
        token_vals = _normalized_numbers(raw_token)
        token_vals = {value for value in token_vals if not _is_calendar_year(value)}
        if token_vals and not token_vals.issubset(context_values):
            unverified.append(raw_token)

    return NumericalGroundingResult(passed=len(unverified) == 0, unverified_numbers=unverified)


def check_output(answer: str, contexts: list[Any]) -> NumericalGroundingResult:
    return verify_numerical_grounding(answer, contexts)


class OutputGuardrail:
    def check(self, answer: str, contexts: list[Any]) -> NumericalGroundingResult:
        return verify_numerical_grounding(answer, contexts)

    __call__ = check