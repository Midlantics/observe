from __future__ import annotations
from datetime import datetime
from typing import Any
from pydantic import BaseModel, Field


class SpanEvent(BaseModel):
    name: str
    timestamp: datetime
    attributes: dict[str, Any] = {}


class IngestSpan(BaseModel):
    span_id: str
    trace_id: str
    parent_span_id: str | None = None
    name: str
    kind: str = "internal"          # internal | llm | tool | agent | handoff
    status: str = "ok"              # ok | error
    started_at: datetime
    ended_at: datetime | None = None
    duration_ms: int | None = None
    attributes: dict[str, Any] = {}
    events: list[SpanEvent] = []


class IngestSpanBatch(BaseModel):
    spans: list[IngestSpan]


class IngestTrace(BaseModel):
    trace_id: str
    agent_name: str | None = None
    status: str = "running"         # running | success | error
    started_at: datetime
    ended_at: datetime | None = None
    duration_ms: int | None = None
    metadata: dict[str, Any] = {}


class IngestLLMCall(BaseModel):
    span_id: str | None = None
    trace_id: str
    model: str
    provider: str
    prompt_tokens: int | None = None
    completion_tokens: int | None = None
    total_tokens: int | None = None
    latency_ms: int | None = None
    cost_usd: float | None = None
    input: Any = None
    output: Any = None
    error: str | None = None
    created_at: datetime = Field(default_factory=datetime.utcnow)
