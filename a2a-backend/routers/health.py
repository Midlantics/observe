from fastapi import APIRouter
from db import get_pool

router = APIRouter()


@router.get("/health")
async def health():
    pool = await get_pool()
    await pool.fetchval("SELECT 1")
    return {"status": "ok"}
