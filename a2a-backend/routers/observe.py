from fastapi import APIRouter, Request, Query
from db import get_pool
from auth import get_workspace_id

router = APIRouter(prefix="/observe")


# ── Dashboard summary ─────────────────────────────────────────────────────────

@router.get("/summary")
async def summary(request: Request):
    workspace_id = get_workspace_id(request)
    pool = await get_pool()
    row = await pool.fetchrow(
        """
        SELECT
          COUNT(*)                                        AS total_traces,
          COUNT(*) FILTER (WHERE status = 'error')       AS error_traces,
          COUNT(*) FILTER (WHERE status = 'running')     AS running_traces,
          AVG(duration_ms)                               AS avg_duration_ms
        FROM a2a.traces
        WHERE workspace_id = $1
          AND started_at > NOW() - INTERVAL '24 hours'
        """,
        workspace_id,
    )
    llm_row = await pool.fetchrow(
        """
        SELECT
          COUNT(*)               AS total_llm_calls,
          SUM(total_tokens)      AS total_tokens,
          SUM(cost_usd)          AS total_cost_usd,
          AVG(latency_ms)        AS avg_latency_ms
        FROM a2a.llm_calls
        WHERE workspace_id = $1
          AND created_at > NOW() - INTERVAL '24 hours'
        """,
        workspace_id,
    )
    return {
        "traces": {
            "total": row["total_traces"],
            "errors": row["error_traces"],
            "running": row["running_traces"],
            "avg_duration_ms": round(row["avg_duration_ms"] or 0, 1),
        },
        "llm": {
            "total_calls": llm_row["total_llm_calls"],
            "total_tokens": llm_row["total_tokens"] or 0,
            "total_cost_usd": float(llm_row["total_cost_usd"] or 0),
            "avg_latency_ms": round(llm_row["avg_latency_ms"] or 0, 1),
        },
    }


# ── Traces ────────────────────────────────────────────────────────────────────

@router.get("/traces")
async def list_traces(
    request: Request,
    limit: int = Query(50, le=200),
    offset: int = Query(0, ge=0),
    status: str | None = None,
    agent_name: str | None = None,
):
    workspace_id = get_workspace_id(request)
    pool = await get_pool()
    filters = ["workspace_id = $1"]
    params: list = [workspace_id]
    idx = 2
    if status:
        filters.append(f"status = ${idx}")
        params.append(status)
        idx += 1
    if agent_name:
        filters.append(f"agent_name ILIKE ${idx}")
        params.append(f"%{agent_name}%")
        idx += 1
    where = " AND ".join(filters)
    rows = await pool.fetch(
        f"""
        SELECT trace_id, agent_name, status, started_at, ended_at, duration_ms, metadata
        FROM a2a.traces
        WHERE {where}
        ORDER BY started_at DESC
        LIMIT ${idx} OFFSET ${idx+1}
        """,
        *params, limit, offset,
    )
    return [dict(r) for r in rows]


@router.get("/traces/{trace_id}")
async def get_trace(trace_id: str, request: Request):
    workspace_id = get_workspace_id(request)
    pool = await get_pool()
    trace = await pool.fetchrow(
        "SELECT * FROM a2a.traces WHERE trace_id = $1 AND workspace_id = $2",
        trace_id, workspace_id,
    )
    if not trace:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail="Trace not found")
    spans = await pool.fetch(
        """
        SELECT span_id, parent_span_id, name, kind, status,
               started_at, ended_at, duration_ms, attributes, events
        FROM a2a.spans
        WHERE trace_id = $1 AND workspace_id = $2
        ORDER BY started_at ASC
        """,
        trace_id, workspace_id,
    )
    return {"trace": dict(trace), "spans": [dict(s) for s in spans]}


# ── LLM Calls ─────────────────────────────────────────────────────────────────

@router.get("/llm-calls")
async def list_llm_calls(
    request: Request,
    limit: int = Query(50, le=200),
    offset: int = Query(0, ge=0),
    model: str | None = None,
    trace_id: str | None = None,
):
    workspace_id = get_workspace_id(request)
    pool = await get_pool()
    filters = ["workspace_id = $1"]
    params: list = [workspace_id]
    idx = 2
    if model:
        filters.append(f"model = ${idx}")
        params.append(model)
        idx += 1
    if trace_id:
        filters.append(f"trace_id = ${idx}")
        params.append(trace_id)
        idx += 1
    where = " AND ".join(filters)
    rows = await pool.fetch(
        f"""
        SELECT id, span_id, trace_id, model, provider,
               prompt_tokens, completion_tokens, total_tokens,
               latency_ms, cost_usd, error, created_at
        FROM a2a.llm_calls
        WHERE {where}
        ORDER BY created_at DESC
        LIMIT ${idx} OFFSET ${idx+1}
        """,
        *params, limit, offset,
    )
    return [dict(r) for r in rows]


# ── Agent activity ─────────────────────────────────────────────────────────────

@router.get("/agents")
async def list_agents(request: Request):
    workspace_id = get_workspace_id(request)
    pool = await get_pool()
    rows = await pool.fetch(
        """
        SELECT
          agent_name,
          COUNT(*)                                    AS total_runs,
          COUNT(*) FILTER (WHERE status = 'error')   AS error_runs,
          AVG(duration_ms)                            AS avg_duration_ms,
          MAX(started_at)                             AS last_seen
        FROM a2a.traces
        WHERE workspace_id = $1 AND agent_name IS NOT NULL
        GROUP BY agent_name
        ORDER BY last_seen DESC
        """,
        workspace_id,
    )
    return [dict(r) for r in rows]
