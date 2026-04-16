"""API Key management — create, list, revoke workspace API keys."""
from __future__ import annotations

import hashlib
import secrets
from fastapi import APIRouter, Request, HTTPException
from pydantic import BaseModel
from db import get_pool
from auth import get_workspace_id

router = APIRouter(prefix="/keys")

_PREFIX = "a2a_sk_"


def _generate() -> tuple[str, str]:
    """Return (raw_key, sha256_hash). Raw key is shown once and never stored."""
    raw = _PREFIX + secrets.token_urlsafe(32)
    hashed = hashlib.sha256(raw.encode()).hexdigest()
    return raw, hashed


class KeyCreate(BaseModel):
    name: str


@router.post("", status_code=201)
async def create_key(body: KeyCreate, request: Request):
    workspace_id = get_workspace_id(request)
    raw, hashed = _generate()
    pool = await get_pool()
    row = await pool.fetchrow(
        """
        INSERT INTO a2a.api_keys (workspace_id, name, key_hash)
        VALUES ($1, $2, $3)
        RETURNING id, name, created_at
        """,
        workspace_id, body.name, hashed,
    )
    return {
        "id": str(row["id"]),
        "name": row["name"],
        "key": raw,          # shown once — never returned again
        "created_at": row["created_at"].isoformat(),
    }


@router.get("")
async def list_keys(request: Request):
    workspace_id = get_workspace_id(request)
    pool = await get_pool()
    rows = await pool.fetch(
        """
        SELECT id, name, created_at, last_used_at, revoked
        FROM a2a.api_keys
        WHERE workspace_id = $1
        ORDER BY created_at DESC
        """,
        workspace_id,
    )
    return [dict(r) for r in rows]


@router.delete("/{key_id}", status_code=204)
async def revoke_key(key_id: str, request: Request):
    workspace_id = get_workspace_id(request)
    pool = await get_pool()
    result = await pool.execute(
        "UPDATE a2a.api_keys SET revoked=true WHERE id=$1 AND workspace_id=$2",
        key_id, workspace_id,
    )
    if result == "UPDATE 0":
        raise HTTPException(status_code=404, detail="Key not found")
