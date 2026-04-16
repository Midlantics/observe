import hashlib
from fastapi import Request, HTTPException
from jose import jwt, JWTError
from config import get_settings

_PREFIX = "a2a_sk_"


def _extract_token(request: Request) -> str | None:
    auth = request.headers.get("Authorization", "")
    if auth.startswith("Bearer "):
        return auth[7:]
    return None


def verify_token(token: str) -> dict:
    settings = get_settings()
    try:
        payload = jwt.decode(
            token,
            settings.supabase_jwt_secret,
            algorithms=["HS256"],
            options={"verify_aud": False},
        )
        return payload
    except JWTError as e:
        raise HTTPException(status_code=401, detail=f"Invalid token: {e}")


async def _resolve_api_key(raw_key: str) -> str | None:
    """Look up an API key by hash. Returns workspace_id or None."""
    from db import get_pool
    hashed = hashlib.sha256(raw_key.encode()).hexdigest()
    pool = await get_pool()
    row = await pool.fetchrow(
        """
        UPDATE a2a.api_keys
        SET last_used_at = NOW()
        WHERE key_hash = $1 AND revoked = false
        RETURNING workspace_id
        """,
        hashed,
    )
    return str(row["workspace_id"]) if row else None


async def get_workspace_id(request: Request) -> str:
    """Resolve workspace_id from Bearer token (API key or Supabase JWT). Raises 401 if missing/invalid."""
    token = _extract_token(request)
    if not token:
        raise HTTPException(status_code=401, detail="Authorization header required")

    # API key path
    if token.startswith(_PREFIX):
        workspace_id = await _resolve_api_key(token)
        if not workspace_id:
            raise HTTPException(status_code=401, detail="Invalid or revoked API key")
        return workspace_id

    # Supabase JWT path
    payload = verify_token(token)
    sub = payload.get("sub")
    if not sub:
        raise HTTPException(status_code=401, detail="Token missing sub claim")
    return sub


async def get_workspace_id_optional(request: Request) -> str | None:
    """Same as get_workspace_id but returns None instead of raising."""
    token = _extract_token(request)
    if not token:
        return None
    try:
        if token.startswith(_PREFIX):
            return await _resolve_api_key(token)
        payload = verify_token(token)
        return payload.get("sub")
    except HTTPException:
        return None
