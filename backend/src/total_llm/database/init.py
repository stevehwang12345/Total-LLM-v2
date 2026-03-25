import os
from pathlib import Path

import asyncpg

from total_llm.core.config import get_settings

_pool: asyncpg.Pool | None = None


async def create_pool() -> asyncpg.Pool:
    global _pool
    if _pool is None:
        cfg = get_settings().database
        host = os.environ.get("POSTGRES_HOST", cfg.host)
        port = int(os.environ.get("POSTGRES_PORT", cfg.port))
        database = os.environ.get("POSTGRES_DB", cfg.database)
        user = os.environ.get("POSTGRES_USER", cfg.username)
        password = os.environ.get("POSTGRES_PASSWORD", cfg.password)
        _pool = await asyncpg.create_pool(
            host=host,
            port=port,
            database=database,
            user=user,
            password=password,
            min_size=1,
            max_size=10,
        )
    return _pool


async def init_db(pool: asyncpg.Pool) -> None:
    exists_query = """
    SELECT EXISTS (
        SELECT 1 FROM information_schema.tables
        WHERE table_schema = 'public' AND table_name = 'devices'
    );
    """
    async with pool.acquire() as conn:
        exists = await conn.fetchval(exists_query)
        if not exists:
            schema_path = Path(__file__).with_name("schema.sql")
            await conn.execute(schema_path.read_text(encoding="utf-8"))


def get_pool() -> asyncpg.Pool | None:
    return _pool
