"""Redaction and prompt-injection checks for user queries."""

import re

from ..state import GuardrailCheckResult

_PII_PATTERNS = (
    ("credit_card", re.compile(r"(?<!\d)(?:\d[ -]?){13,19}(?!\d)")),
    ("iban", re.compile(r"\b[A-Z]{2}\d{2}[A-Z0-9]{11,30}\b", re.IGNORECASE)),
    ("ssn", re.compile(r"(?<!\d)\d{3}-\d{2}-\d{4}(?!\d)")),
)
_INJECTION_PATTERNS = (
    re.compile(r"ignore\s+(?:all\s+)?previous\s+instructions", re.IGNORECASE),
    re.compile(r"(?:reveal|show|print|repeat)\s+(?:the\s+)?(?:system|developer)\s+prompt", re.IGNORECASE),
    re.compile(r"\b(?:jailbreak|do\s+anything\s+now|dan)\b", re.IGNORECASE),
    re.compile(r"(?:^|\n)\s*(?:system|developer)\s*:", re.IGNORECASE),
)


def check_input(text: str) -> GuardrailCheckResult:
    """Redact financial PII and reject common prompt-injection attempts."""
    sanitized = text
    violations: list[str] = []
    for name, pattern in _PII_PATTERNS:
        if pattern.search(sanitized):
            violations.append(f"pii:{name}")
            sanitized = pattern.sub(f"[REDACTED_{name.upper()}]", sanitized)
    if any(pattern.search(sanitized) for pattern in _INJECTION_PATTERNS):
        violations.append("prompt_injection")
    return GuardrailCheckResult(
        is_safe="prompt_injection" not in violations,
        sanitized_text=sanitized,
        violations=violations,
    )


def guard_input(text: str) -> GuardrailCheckResult:
    return check_input(text)


class InputGuardrail:
    def check(self, text: str) -> GuardrailCheckResult:
        return check_input(text)

    __call__ = check
