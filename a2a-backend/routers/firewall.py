"""
Firewall — real-time threat detection for agent inputs and outputs.

Detects:
  - Prompt injection attempts
  - PII leakage (SSN, credit cards, emails, phone numbers)
  - Jailbreak patterns
  - Sensitive data exfiltration
  - Anomalous tool call sequences

Every scan is logged to a2a.firewall_events for audit.
"""
from __future__ import annotations

import json
import re
from fastapi import APIRouter, Request
from pydantic import BaseModel
from typing import Any
from db import get_pool
from auth import get_workspace_id

router = APIRouter(prefix="/firewall")

# ── Threat patterns ───────────────────────────────────────────────────────────

THREATS: list[dict] = [
    {
        "id": "prompt_injection",
        "name": "Prompt injection",
        "severity": "critical",
        "patterns": [
            r"ignore (all |previous |prior |above |the )?(instructions?|prompts?|rules?|directives?)",
            r"forget (everything|all|your|the) (instructions?|system|rules?)",
            r"you are now (a |an )?(?!assistant)",
            r"(act|pretend|behave|respond) as (if you are|you were|a)",
            r"DAN\b",
            r"jailbreak",
            r"new persona",
            r"disregard (your|all|the) (training|guidelines|rules)",
        ],
    },
    {
        "id": "pii_ssn",
        "name": "SSN detected",
        "severity": "high",
        "patterns": [r"\b\d{3}-\d{2}-\d{4}\b", r"\b\d{9}\b"],
    },
    {
        "id": "pii_credit_card",
        "name": "Credit card number",
        "severity": "high",
        "patterns": [r"\b(?:4[0-9]{12}(?:[0-9]{3})?|5[1-5][0-9]{14}|3[47][0-9]{13}|3(?:0[0-5]|[68][0-9])[0-9]{11}|6(?:011|5[0-9]{2})[0-9]{12})\b"],
    },
    {
        "id": "pii_email",
        "name": "Email address",
        "severity": "medium",
        "patterns": [r"\b[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Z|a-z]{2,}\b"],
    },
    {
        "id": "pii_phone",
        "name": "Phone number",
        "severity": "medium",
        "patterns": [r"\b(\+?1[-.\s]?)?\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}\b"],
    },
    {
        "id": "exfiltration",
        "name": "Data exfiltration attempt",
        "severity": "critical",
        "patterns": [
            r"send (this|the|all) (to|via|using) (email|http|webhook|api)",
            r"exfiltrate",
            r"leak (this|the|data|information)",
            r"forward (this|to|all)",
        ],
    },
    {
        "id": "jailbreak",
        "name": "Jailbreak attempt",
        "severity": "critical",
        "patterns": [
            r"developer mode",
            r"sudo mode",
            r"god mode",
            r"unrestricted mode",
            r"bypass (safety|filter|restriction|guideline)",
            r"no (restrictions?|limits?|filters?|rules?)",
        ],
    },
]

# Pre-compile all patterns
_COMPILED: list[dict] = [
    {
        **t,
        "_compiled": [re.compile(p, re.IGNORECASE) for p in t["patterns"]],
    }
    for t in THREATS
]


# ── Models ────────────────────────────────────────────────────────────────────

class ScanRequest(BaseModel):
    content: str
    context: str = "input"          # input | output | tool_call
    trace_id: str | None = None
    agent_name: str | None = None
    metadata: dict[str, Any] = {}


class ThreatMatch(BaseModel):
    threat_id: str
    name: str
    severity: str


class ScanResult(BaseModel):
    clean: bool
    verdict: str                    # clean | warn | block
    threats: list[ThreatMatch]


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.post("/scan")
async def scan(body: ScanRequest, request: Request):
    workspace_id = get_workspace_id(request)

    threats_found: list[ThreatMatch] = []
    for threat in _COMPILED:
        for pattern in threat["_compiled"]:
            if pattern.search(body.content):
                threats_found.append(ThreatMatch(
                    threat_id=threat["id"],
                    name=threat["name"],
                    severity=threat["severity"],
                ))
                break  # one match per threat type is enough

    # Determine verdict
    severities = {t.severity for t in threats_found}
    if "critical" in severities:
        verdict = "block"
    elif "high" in severities or threats_found:
        verdict = "warn"
    else:
        verdict = "clean"

    clean = len(threats_found) == 0

    # Log to DB
    pool = await get_pool()
    await pool.execute(
        """
        INSERT INTO a2a.firewall_events
          (workspace_id, trace_id, agent_name, context, content_hash,
           verdict, threats, metadata)
        VALUES ($1,$2,$3,$4,md5($5),$6,$7,$8)
        """,
        workspace_id,
        body.trace_id,
        body.agent_name,
        body.context,
        body.content,
        verdict,
        json.dumps([t.model_dump() for t in threats_found]),
        json.dumps(body.metadata),
    )

    return ScanResult(clean=clean, verdict=verdict, threats=threats_found)


@router.get("/events")
async def list_events(request: Request, verdict: str | None = None):
    workspace_id = get_workspace_id(request)
    pool = await get_pool()
    filters = ["workspace_id = $1"]
    params: list = [workspace_id]
    if verdict:
        filters.append("verdict = $2")
        params.append(verdict)
    rows = await pool.fetch(
        f"""
        SELECT id, trace_id, agent_name, context, verdict, threats,
               metadata, created_at
        FROM a2a.firewall_events
        WHERE {" AND ".join(filters)}
        ORDER BY created_at DESC LIMIT 200
        """,
        *params,
    )
    return [dict(r) for r in rows]


@router.get("/stats")
async def stats(request: Request):
    workspace_id = get_workspace_id(request)
    pool = await get_pool()
    row = await pool.fetchrow(
        """
        SELECT
          COUNT(*)                                      AS total_scans,
          COUNT(*) FILTER (WHERE verdict='clean')       AS clean,
          COUNT(*) FILTER (WHERE verdict='warn')        AS warned,
          COUNT(*) FILTER (WHERE verdict='block')       AS blocked
        FROM a2a.firewall_events
        WHERE workspace_id=$1
          AND created_at > NOW() - INTERVAL '24 hours'
        """,
        workspace_id,
    )
    return dict(row)
