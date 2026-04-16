import asyncpg
from config import get_settings

_pool: asyncpg.Pool | None = None


async def get_pool() -> asyncpg.Pool:
    global _pool
    if _pool is None:
        _pool = await asyncpg.create_pool(
            get_settings().database_url,
            min_size=2,
            max_size=10,
            command_timeout=30,
            statement_cache_size=0,  # required for pgbouncer transaction mode
        )
    return _pool


async def close_pool() -> None:
    global _pool
    if _pool:
        await _pool.close()
        _pool = None
