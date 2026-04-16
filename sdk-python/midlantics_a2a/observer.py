from __future__ import annotations

import time
from datetime import datetime, timezone
from types import TracebackType
from typing import Any
from uuid import uuid4

from .sender import BackgroundSender


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _ms(start: float) -> int:
    return int((time.perf_counter() - start) * 1000)


class SpanContext:
    def __init__(
        self,
        trace: "TraceContext",
        name: str,
        kind: str = "internal",
        parent_span_id: str | None = None,
    ) -> None:
        self._trace = trace
        self.span_id = str(uuid4())
        self.name = name
        self.kind = kind
        self.parent_span_id = parent_span_id
        self._attributes: dict[str, Any] = {}
        self._events: list[dict] = []
        self._start: float = 0.0
        self._started_at: str = ""

    def __enter__(self) -> "SpanContext":
        self._start = time.perf_counter()
        self._started_at = _now()
        return self

    def __exit__(
        self,
        exc_type: type | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> None:
        duration = _ms(self._start)
        ended_at = _now()
        status = "error" if exc_type else "ok"
        if exc_val:
            self._attributes["error.message"] = str(exc_val)
            self._attributes["error.type"] = exc_type.__name__ if exc_type else ""

        self._trace._observer._sender.enqueue(
            "/ingest/spans",
            {
                "spans": [
                    {
                        "span_id": self.span_id,
                        "trace_id": self._trace.trace_id,
                        "parent_span_id": self.parent_span_id,
                        "name": self.name,
                        "kind": self.kind,
                        "status": status,
                        "started_at": self._started_at,
                        "ended_at": ended_at,
                        "duration_ms": duration,
                        "attributes": self._attributes,
                        "events": self._events,
                    }
                ]
            },
        )

    def set_attribute(self, key: str, value: Any) -> "SpanContext":
        self._attributes[key] = value
        return self

    def add_event(self, name: str, attributes: dict[str, Any] | None = None) -> "SpanContext":
        self._events.append({"name": name, "timestamp": _now(), "attributes": attributes or {}})
        return self

    def record_llm(
        self,
        *,
        model: str,
        provider: str,
        prompt_tokens: int | None = None,
        completion_tokens: int | None = None,
        total_tokens: int | None = None,
        cost_usd: float | None = None,
        input: Any = None,
        output: Any = None,
        error: str | None = None,
    ) -> "SpanContext":
        latency_ms = _ms(self._start)
        self._trace._observer._sender.enqueue(
            "/ingest/llm-calls",
            {
                "span_id": self.span_id,
                "trace_id": self._trace.trace_id,
                "model": model,
                "provider": provider,
                "prompt_tokens": prompt_tokens,
                "completion_tokens": completion_tokens,
                "total_tokens": total_tokens or (
                    (prompt_tokens or 0) + (completion_tokens or 0) or None
                ),
                "latency_ms": latency_ms,
                "cost_usd": cost_usd,
                "input": input,
                "output": output,
                "error": error,
                "created_at": _now(),
            },
        )
        return self


class TraceContext:
    def __init__(
        self,
        observer: "Observer",
        agent_name: str | None,
        trace_id: str | None,
    ) -> None:
        self._observer = observer
        self.trace_id = trace_id or str(uuid4())
        self.agent_name = agent_name
        self._start: float = 0.0
        self._started_at: str = ""

    def __enter__(self) -> "TraceContext":
        self._start = time.perf_counter()
        self._started_at = _now()
        self._observer._sender.enqueue(
            "/ingest/traces",
            {
                "trace_id": self.trace_id,
                "agent_name": self.agent_name,
                "status": "running",
                "started_at": self._started_at,
            },
        )
        return self

    def __exit__(
        self,
        exc_type: type | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> None:
        duration = _ms(self._start)
        self._observer._sender.enqueue(
            "/ingest/traces",
            {
                "trace_id": self.trace_id,
                "agent_name": self.agent_name,
                "status": "error" if exc_type else "success",
                "started_at": self._started_at,
                "ended_at": _now(),
                "duration_ms": duration,
            },
        )

    def span(
        self,
        name: str,
        kind: str = "internal",
        parent_span_id: str | None = None,
    ) -> SpanContext:
        return SpanContext(self, name, kind, parent_span_id)


class Observer:
    """
    Entry point for the Midlantics A2A SDK.

    Usage::

        from midlantics_a2a import Observer

        obs = Observer(api_url="https://a2a-api.midlantics.com", token="<jwt>")

        with obs.trace("purchase-agent") as trace:
            with trace.span("call-llm", kind="llm") as span:
                response = client.chat(...)
                span.record_llm(model="gpt-4o", provider="openai", ...)
    """

    def __init__(
        self,
        api_url: str,
        token: str,
        agent_name: str | None = None,
    ) -> None:
        self._sender = BackgroundSender(api_url, token)
        self._agent_name = agent_name

    def trace(
        self,
        agent_name: str | None = None,
        trace_id: str | None = None,
    ) -> TraceContext:
        return TraceContext(self, agent_name or self._agent_name, trace_id)

    def flush(self) -> None:
        """Block until all queued events have been sent."""
        self._sender.flush()

    def shutdown(self) -> None:
        """Flush and stop the background sender thread."""
        self._sender.shutdown()
