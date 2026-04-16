"""
Approval Layer — human-in-the-loop gate for high-risk agent actions.

Flow:
  1. Agent calls POST /approval/requests  → gets back a request_id + status=pending
  2. Agent polls GET  /approval/requests/{id} until status changes
  3. Reviewer opens dashboard, sees pending requests, clicks Approve or Reject
  4. PATCH /approval/requests/{id} sets status=approved|rejected + reviewer note
  5. Agent receives the verdict and proceeds or aborts

Timeout: if a request is not actioned within `timeout_seconds`, it auto-expires.
"""
from __future__ import annotations

import hashlib
import hmac
import json
from fastapi import APIRouter, Request, HTTPException
from fastapi.responses import HTMLResponse
from pydantic import BaseModel
from typing import Any
from db import get_pool
from auth import get_workspace_id
from config import get_settings
from mailer import send_email, approval_email_html
import httpx

router = APIRouter(prefix="/approval")


# ── HMAC helpers ──────────────────────────────────────────────────────────────

def _make_token(request_id: str, action: str) -> str:
    secret = get_settings().approval_link_secret.encode()
    msg = f"{request_id}:{action}".encode()
    return hmac.new(secret, msg, hashlib.sha256).hexdigest()


def _verify_token(request_id: str, action: str, token: str) -> bool:
    expected = _make_token(request_id, action)
    return hmac.compare_digest(expected, token)


async def _get_user_email(workspace_id: str) -> str | None:
    """Look up the user's email via Supabase admin API."""
    s = get_settings()
    if not s.supabase_url or not s.supabase_service_role_key:
        return None
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            res = await client.get(
                f"{s.supabase_url}/auth/v1/admin/users/{workspace_id}",
                headers={"apikey": s.supabase_service_role_key,
                         "Authorization": f"Bearer {s.supabase_service_role_key}"},
            )
            if res.status_code == 200:
                return res.json().get("email")
    except Exception:
        pass
    return None


# ── Models ────────────────────────────────────────────────────────────────────

class ApprovalRequest(BaseModel):
    action_type: str
    description: str
    payload: dict[str, Any] = {}
    trace_id: str | None = None
    agent_name: str | None = None
    timeout_seconds: int = 3600     # 1 hour default


class ApprovalDecision(BaseModel):
    status: str                     # approved | rejected
    reviewer_note: str = ""


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.post("/requests", status_code=201)
async def create_request(body: ApprovalRequest, request: Request):
    workspace_id = get_workspace_id(request)
    pool = await get_pool()
    row = await pool.fetchrow(
        """
        INSERT INTO a2a.approval_requests
          (workspace_id, trace_id, agent_name, action_type, description,
           payload, timeout_seconds)
        VALUES ($1,$2,$3,$4,$5,$6,$7)
        RETURNING id, status, created_at
        """,
        workspace_id,
        body.trace_id,
        body.agent_name,
        body.action_type,
        body.description,
        json.dumps(body.payload),
        body.timeout_seconds,
    )
    request_id = str(row["id"])

    # Send email notification (non-blocking — don't fail the request if email fails)
    try:
        reviewer_email = await _get_user_email(workspace_id)
        if reviewer_email:
            s = get_settings()
            approve_url = f"{s.api_url}/approval/decide?id={request_id}&action=approved&token={_make_token(request_id, 'approved')}"
            reject_url  = f"{s.api_url}/approval/decide?id={request_id}&action=rejected&token={_make_token(request_id, 'rejected')}"
            dashboard_url = f"{s.app_url}/dashboard/approval"
            await send_email(
                to=reviewer_email,
                subject=f"[Action required] {body.action_type}",
                html=approval_email_html(
                    action_type=body.action_type,
                    description=body.description,
                    agent_name=body.agent_name,
                    approve_url=approve_url,
                    reject_url=reject_url,
                    dashboard_url=dashboard_url,
                ),
            )
    except Exception:
        pass  # never fail the request because of email

    return {
        "request_id": request_id,
        "status": row["status"],
        "created_at": row["created_at"].isoformat(),
    }


@router.get("/requests")
async def list_requests(request: Request, status: str | None = None):
    workspace_id = get_workspace_id(request)
    pool = await get_pool()

    # Auto-expire timed-out pending requests
    await pool.execute(
        """
        UPDATE a2a.approval_requests
        SET status='expired', decided_at=NOW()
        WHERE workspace_id=$1
          AND status='pending'
          AND created_at + (timeout_seconds || ' seconds')::interval < NOW()
        """,
        workspace_id,
    )

    filters = ["workspace_id = $1"]
    params: list = [workspace_id]
    if status:
        filters.append(f"status = $2")
        params.append(status)

    rows = await pool.fetch(
        f"""
        SELECT id, trace_id, agent_name, action_type, description,
               payload, status, reviewer_note, timeout_seconds,
               created_at, decided_at
        FROM a2a.approval_requests
        WHERE {" AND ".join(filters)}
        ORDER BY created_at DESC LIMIT 100
        """,
        *params,
    )
    return [dict(r) for r in rows]


@router.get("/requests/{request_id}")
async def get_request(request_id: str, request: Request):
    workspace_id = get_workspace_id(request)
    pool = await get_pool()

    # Auto-expire if timed out
    await pool.execute(
        """
        UPDATE a2a.approval_requests
        SET status='expired', decided_at=NOW()
        WHERE id=$1 AND workspace_id=$2 AND status='pending'
          AND created_at + (timeout_seconds || ' seconds')::interval < NOW()
        """,
        request_id, workspace_id,
    )

    row = await pool.fetchrow(
        "SELECT * FROM a2a.approval_requests WHERE id=$1 AND workspace_id=$2",
        request_id, workspace_id,
    )
    if not row:
        raise HTTPException(status_code=404, detail="Request not found")
    return dict(row)


@router.patch("/requests/{request_id}")
async def decide(request_id: str, body: ApprovalDecision, request: Request):
    workspace_id = get_workspace_id(request)
    if body.status not in ("approved", "rejected"):
        raise HTTPException(status_code=400, detail="status must be approved or rejected")

    pool = await get_pool()
    result = await pool.execute(
        """
        UPDATE a2a.approval_requests
        SET status=$3, reviewer_note=$4, decided_at=NOW()
        WHERE id=$1 AND workspace_id=$2 AND status='pending'
        """,
        request_id, workspace_id, body.status, body.reviewer_note,
    )
    if result == "UPDATE 0":
        raise HTTPException(status_code=404, detail="Request not found or already decided")
    return {"ok": True, "status": body.status}


@router.get("/decide", response_class=HTMLResponse)
async def decide_via_link(id: str, action: str, token: str):
    """One-click approve/reject from email link. No auth required — HMAC-protected."""
    if action not in ("approved", "rejected"):
        return _decision_page("Invalid action.", success=False)

    if not _verify_token(id, action, token):
        return _decision_page("Invalid or expired link.", success=False)

    pool = await get_pool()
    result = await pool.execute(
        """
        UPDATE a2a.approval_requests
        SET status=$2, decided_at=NOW(), reviewer_note='via email link'
        WHERE id=$1 AND status='pending'
        """,
        id, action,
    )

    if result == "UPDATE 0":
        # Already decided or expired — show current state
        row = await pool.fetchrow(
            "SELECT status FROM a2a.approval_requests WHERE id=$1", id
        )
        if row:
            return _decision_page(f"This request was already {row['status']}.", success=False)
        return _decision_page("Request not found.", success=False)

    s = get_settings()
    label = "Approved" if action == "approved" else "Rejected"
    return _decision_page(
        f"Request {label.lower()} successfully.",
        success=True,
        dashboard_url=f"{s.app_url}/dashboard/approval",
    )


def _decision_page(message: str, *, success: bool, dashboard_url: str = "") -> HTMLResponse:
    color = "#16a34a" if success else "#b91c1c"
    icon = "✓" if success else "✗"
    link = f'<p style="text-align:center;margin:16px 0 0"><a href="{dashboard_url}" style="color:#6366f1;font-size:13px">Open dashboard →</a></p>' if dashboard_url else ""
    html = f"""<!DOCTYPE html>
<html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Approval</title></head>
<body style="background:#0f172a;font-family:-apple-system,sans-serif;display:flex;align-items:center;justify-content:center;min-height:100vh;margin:0">
  <div style="background:#1e293b;border:1px solid #334155;border-radius:16px;padding:40px;text-align:center;max-width:360px;width:90%">
    <div style="width:56px;height:56px;border-radius:50%;background:{color}20;border:2px solid {color};display:flex;align-items:center;justify-content:center;margin:0 auto 20px;font-size:24px;color:{color}">{icon}</div>
    <p style="color:#e2e8f0;font-size:16px;margin:0">{message}</p>
    {link}
  </div>
</body></html>"""
    return HTMLResponse(content=html)


@router.get("/stats")
async def stats(request: Request):
    workspace_id = get_workspace_id(request)
    pool = await get_pool()
    row = await pool.fetchrow(
        """
        SELECT
          COUNT(*) FILTER (WHERE status='pending')  AS pending,
          COUNT(*) FILTER (WHERE status='approved') AS approved,
          COUNT(*) FILTER (WHERE status='rejected') AS rejected,
          COUNT(*) FILTER (WHERE status='expired')  AS expired,
          AVG(EXTRACT(EPOCH FROM (decided_at - created_at)))
            FILTER (WHERE decided_at IS NOT NULL)   AS avg_decision_seconds
        FROM a2a.approval_requests
        WHERE workspace_id=$1
          AND created_at > NOW() - INTERVAL '24 hours'
        """,
        workspace_id,
    )
    return {
        "pending":  row["pending"],
        "approved": row["approved"],
        "rejected": row["rejected"],
        "expired":  row["expired"],
        "avg_decision_seconds": round(row["avg_decision_seconds"] or 0, 1),
    }
