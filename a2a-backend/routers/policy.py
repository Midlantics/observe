"""
Policy Engine — evaluate agent actions against workspace rules.

A policy is a list of rules. Each rule has:
  - name:        human-readable label
  - description: optional explanation
  - match:       dict of conditions (field -> value or regex pattern)
  - action:      block | flag | allow
  - severity:    critical | high | medium | low  (for flag actions)

Example policy (stored as JSONB in a2a.policies):
  rules:
    - name: "block large purchases"
      match:
        action_type: "purchase"
        amount_gt: 10000
      action: block

    - name: "flag PII fields"
      match:
        output_contains: "(\\d{3}-\\d{2}-\\d{4}|\\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\\.[A-Z]{2,}\\b)"
      action: flag
      severity: high
"""
from __future__ import annotations

import json
import re
from fastapi import APIRouter, Request, HTTPException
from pydantic import BaseModel
from typing import Any
from db import get_pool
from auth import get_workspace_id
router = APIRouter(prefix="/policy")


# ── Models ────────────────────────────────────────────────────────────────────

class PolicyRule(BaseModel):
    name: str
    description: str = ""
    match: dict[str, Any]
    action: str = "flag"        # block | flag | allow
    severity: str = "medium"    # critical | high | medium | low


class PolicyUpsert(BaseModel):
    name: str
    description: str = ""
    enabled: bool = True
    rules: list[PolicyRule]


class EvaluateRequest(BaseModel):
    action_type: str
    payload: dict[str, Any] = {}
    trace_id: str | None = None
    agent_name: str | None = None


class EvaluateResult(BaseModel):
    verdict: str                # allow | flag | block
    triggered_rules: list[dict]


# ── CRUD ──────────────────────────────────────────────────────────────────────

@router.get("/policies")
async def list_policies(request: Request):
    workspace_id = get_workspace_id(request)

    pool = await get_pool()
    rows = await pool.fetch(
        "SELECT id, name, description, enabled, rules, created_at, updated_at "
        "FROM a2a.policies WHERE workspace_id = $1 ORDER BY created_at DESC",
        workspace_id,
    )
    return [dict(r) for r in rows]


@router.get("/policies/{policy_id}")
async def get_policy(policy_id: str, request: Request):
    workspace_id = get_workspace_id(request)
    pool = await get_pool()
    row = await pool.fetchrow(
        "SELECT * FROM a2a.policies WHERE id = $1 AND workspace_id = $2",
        policy_id, workspace_id,
    )
    if not row:
        raise HTTPException(status_code=404, detail="Policy not found")
    return dict(row)


@router.post("/policies", status_code=201)
async def create_policy(body: PolicyUpsert, request: Request):
    workspace_id = get_workspace_id(request)

    pool = await get_pool()
    row = await pool.fetchrow(
        """
        INSERT INTO a2a.policies (workspace_id, name, description, enabled, rules)
        VALUES ($1, $2, $3, $4, $5)
        RETURNING id
        """,
        workspace_id,
        body.name,
        body.description,
        body.enabled,
        json.dumps([r.model_dump() for r in body.rules]),
    )
    return {"ok": True, "id": str(row["id"])}


@router.put("/policies/{policy_id}")
async def update_policy(policy_id: str, body: PolicyUpsert, request: Request):
    workspace_id = get_workspace_id(request)
    pool = await get_pool()
    result = await pool.execute(
        """
        UPDATE a2a.policies
        SET name=$3, description=$4, enabled=$5, rules=$6, updated_at=NOW()
        WHERE id=$1 AND workspace_id=$2
        """,
        policy_id, workspace_id,
        body.name, body.description, body.enabled,
        json.dumps([r.model_dump() for r in body.rules]),
    )
    if result == "UPDATE 0":
        raise HTTPException(status_code=404, detail="Policy not found")
    return {"ok": True}


@router.delete("/policies/{policy_id}", status_code=204)
async def delete_policy(policy_id: str, request: Request):
    workspace_id = get_workspace_id(request)
    pool = await get_pool()
    await pool.execute(
        "DELETE FROM a2a.policies WHERE id=$1 AND workspace_id=$2",
        policy_id, workspace_id,
    )


# ── Evaluation ────────────────────────────────────────────────────────────────

@router.post("/evaluate")
async def evaluate(body: EvaluateRequest, request: Request):
    workspace_id = get_workspace_id(request)

    pool = await get_pool()

    rows = await pool.fetch(
        "SELECT rules FROM a2a.policies WHERE workspace_id=$1 AND enabled=true",
        workspace_id,
    )

    all_rules: list[dict] = []
    for row in rows:
        rules = row["rules"]
        if isinstance(rules, str):
            rules = json.loads(rules)
        all_rules.extend(rules)

    triggered: list[dict] = []
    verdict = "allow"

    flat_payload = _flatten({"action_type": body.action_type, **body.payload})

    for rule in all_rules:
        if _matches(rule.get("match", {}), flat_payload):
            action = rule.get("action", "flag")
            triggered.append({
                "name": rule.get("name"),
                "action": action,
                "severity": rule.get("severity", "medium"),
            })
            if action == "block":
                verdict = "block"
            elif action == "flag" and verdict != "block":
                verdict = "flag"

    # Persist evaluation result
    await pool.execute(
        """
        INSERT INTO a2a.policy_events
          (workspace_id, trace_id, agent_name, action_type, payload, verdict, triggered_rules)
        VALUES ($1,$2,$3,$4,$5,$6,$7)
        """,
        workspace_id,
        body.trace_id,
        body.agent_name,
        body.action_type,
        json.dumps(body.payload),
        verdict,
        json.dumps(triggered),
    )

    return EvaluateResult(verdict=verdict, triggered_rules=triggered)


@router.get("/events")
async def list_events(request: Request):
    workspace_id = get_workspace_id(request)
    pool = await get_pool()
    rows = await pool.fetch(
        """
        SELECT id, trace_id, agent_name, action_type, verdict,
               triggered_rules, created_at
        FROM a2a.policy_events
        WHERE workspace_id=$1
        ORDER BY created_at DESC LIMIT 100
        """,
        workspace_id,
    )
    return [dict(r) for r in rows]


# ── Helpers ───────────────────────────────────────────────────────────────────

def _flatten(d: dict, prefix: str = "") -> dict[str, str]:
    """Flatten nested dict to dot-notation string values for matching."""
    out: dict[str, str] = {}
    for k, v in d.items():
        key = f"{prefix}.{k}" if prefix else k
        if isinstance(v, dict):
            out.update(_flatten(v, key))
        else:
            out[key] = str(v)
    return out


def _matches(conditions: dict, flat: dict[str, str]) -> bool:
    for condition, pattern in conditions.items():
        # amount_gt / amount_lt numeric comparisons
        if condition.endswith("_gt"):
            field = condition[:-3]
            val = flat.get(field)
            if val is None:
                return False
            try:
                if float(val) <= float(pattern):
                    return False
            except ValueError:
                return False
        elif condition.endswith("_lt"):
            field = condition[:-3]
            val = flat.get(field)
            if val is None:
                return False
            try:
                if float(val) >= float(pattern):
                    return False
            except ValueError:
                return False
        elif condition == "output_contains":
            # Check regex against all values
            combined = " ".join(flat.values())
            if not re.search(str(pattern), combined, re.IGNORECASE):
                return False
        else:
            val = flat.get(condition)
            if val is None:
                return False
            if not re.search(str(pattern), val, re.IGNORECASE):
                return False
    return True
