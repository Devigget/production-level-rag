"""Numerical grounding checks for generated financial answers."""

import re
from decimal import Decimal, InvalidOperation

from pydantic import BaseModel, Field


class NumericalGroundingResult(BaseModel):
    passed: bool
    unverified_numbers: list[str] = Field(default_factory=list)


_NUMBER = re.compile(
    r"(?<![\w-])(?P<currency>[$€£])?\s*(?P<number>\(?\d[\d,]*(?:\.\d+)?\)?)\s*(?P<scale>[KMBkmb])?\s*(?P<percent>%)?"
)


def _normalized_numbers(text: str) -> set[Decimal]:
    values: set[Decimal] = set()
    for match in _NUMBER.finditer(text):
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


def verify_numerical_grounding(answer: str, contexts: list[object]) -> NumericalGroundingResult:
    context_parts: list[str] = []
    for item in contexts:
        if isinstance(item, str):
            context_parts.append(item)
        elif hasattr(item, "content"):
            context_parts.append(str(item.content))
        else:
            context_parts.append(str(item.get("content", "")))
    context_text = "\n".join(context_parts)
    context_values = _normalized_numbers(context_text)
    unverified = [match.group(0).strip() for match in _NUMBER.finditer(answer)
                  if _normalized_numbers(match.group(0)) - context_values]
    return NumericalGroundingResult(passed=not unverified, unverified_numbers=unverified)


def check_output(answer: str, contexts: list[object]) -> NumericalGroundingResult:
    return verify_numerical_grounding(answer, contexts)


class OutputGuardrail:
    def check(self, answer: str, contexts: list[object]) -> NumericalGroundingResult:
        return verify_numerical_grounding(answer, contexts)

    __call__ = check
