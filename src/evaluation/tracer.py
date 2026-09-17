"""Optional Langfuse tracing with a no-op fallback for local and CI runs."""

from collections.abc import Callable
from functools import wraps
from typing import Any, ParamSpec, TypeVar

from .config import EvaluationSettings

P = ParamSpec("P")
R = TypeVar("R")


class _NoOpSpan:
    def update(self, **kwargs: Any) -> None:
        return None

    def end(self, **kwargs: Any) -> None:
        return None


class Tracer:
    """Small adapter that keeps application code independent of Langfuse."""

    def __init__(self, settings: EvaluationSettings | None = None, client: Any = None):
        self.settings = settings or EvaluationSettings()
        self.client = client
        if self.client is None and self.settings.tracing_enabled:
            try:
                from langfuse import Langfuse

                self.client = Langfuse(public_key=self.settings.langfuse_public_key,
                                       secret_key=self.settings.langfuse_secret_key,
                                       host=self.settings.langfuse_host)
            except (ImportError, RuntimeError, TypeError, ValueError):
                self.client = None

    @property
    def enabled(self) -> bool:
        return self.client is not None

    def start_span(self, name: str, **kwargs: Any) -> Any:
        if not self.client:
            return _NoOpSpan()
        try:
            return self.client.start_span(name=name, **kwargs)
        except (AttributeError, RuntimeError, TypeError, ValueError):
            return _NoOpSpan()

    def flush(self) -> None:
        if self.client:
            try:
                self.client.flush()
            except (AttributeError, RuntimeError):
                return

    def trace(self, name: str) -> Callable[[Callable[P, R]], Callable[P, R]]:
        def decorator(function: Callable[P, R]) -> Callable[P, R]:
            @wraps(function)
            def wrapped(*args: P.args, **kwargs: P.kwargs) -> R:
                span = self.start_span(name)
                try:
                    result = function(*args, **kwargs)
                    span.update(output=result)
                    return result
                except Exception as error:
                    span.update(level="ERROR", status_message=str(error))
                    raise
                finally:
                    span.end()

            return wrapped

        return decorator


def get_tracer(settings: EvaluationSettings | None = None) -> Tracer:
    return Tracer(settings=settings)