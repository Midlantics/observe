import json
from datetime import datetime
from fastapi import APIRouter, Request, HTTPException
from db import get_pool
from auth import get_workspace_id
from models.span import IngestSpan, IngestSpanBatch, IngestTrace, IngestLLMCall

router = APIRouter(prefix="/ingest")


# ── Traces ────────────────────────────────────────────────────────────────────

@router.post("/traces", status_code=201)
async def ingest_trace(body: IngestTrace, request: Request):
    workspace_id = get_workspace_id(request)
    pool = await get_pool()
    await pool.execute(
        """
        INSERT INTO a2a.traces
          (trace_id, workspace_id, agent_name, status, started_at, ended_at, duration_ms, metadata)
        VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
        ON CONFLICT (trace_id) DO UPDATE SET
          status      = EXCLUDED.status,
          ended_at    = EXCLUDED.ended_at,
          duration_ms = EXCLUDED.duration_ms,
          metadata    = EXCLUDED.metadata
        """,
        body.trace_id,
        workspace_id,
        body.agent_name,
        body.status,
        body.started_at,
        body.ended_at,
        body.duration_ms,
        json.dumps(body.metadata),
    )
    return {"ok": True, "trace_id": body.trace_id}


# ── Spans ─────────────────────────────────────────────────────────────────────

@router.post("/spans", status_code=201)
async def ingest_spans(body: IngestSpanBatch, request: Request):
    workspace_id = get_workspace_id(request)
    pool = await get_pool()
    async with pool.acquire() as conn:
        async with conn.transaction():
            for span in body.spans:
                await conn.execute(
                    """
                    INSERT INTO a2a.spans
                      (span_id, trace_id, parent_span_id, workspace_id,
                       name, kind, status, started_at, ended_at, duration_ms,
                       attributes, events)
                    VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12)
                    ON CONFLICT (span_id) DO UPDATE SET
                      status      = EXCLUDED.status,
                      ended_at    = EXCLUDED.ended_at,
                      duration_ms = EXCLUDED.duration_ms,
                      attributes  = EXCLUDED.attributes,
                      events      = EXCLUDED.events
                    """,
                    span.span_id,
                    span.trace_id,
                    span.parent_span_id,
                    workspace_id,
                    span.name,
                    span.kind,
                    span.status,
                    span.started_at,
                    span.ended_at,
                    span.duration_ms,
                    json.dumps(span.attributes),
                    json.dumps([e.model_dump(mode="json") for e in span.events]),
                )
    return {"ok": True, "count": len(body.spans)}


# ── LLM Calls ─────────────────────────────────────────────────────────────────

@router.post("/llm-calls", status_code=201)
async def ingest_llm_call(body: IngestLLMCall, request: Request):
    workspace_id = get_workspace_id(request)
    pool = await get_pool()
    row = await pool.fetchrow(
        """
        INSERT INTO a2a.llm_calls
          (span_id, trace_id, workspace_id, model, provider,
           prompt_tokens, completion_tokens, total_tokens,
           latency_ms, cost_usd, input, output, error, created_at)
        VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13,$14)
        RETURNING id
        """,
        body.span_id,
        body.trace_id,
        workspace_id,
        body.model,
        body.provider,
        body.prompt_tokens,
        body.completion_tokens,
        body.total_tokens,
        body.latency_ms,
        body.cost_usd,
        json.dumps(body.input) if body.input is not None else None,
        json.dumps(body.output) if body.output is not None else None,
        body.error,
        body.created_at,
    )
    return {"ok": True, "id": str(row["id"])}
