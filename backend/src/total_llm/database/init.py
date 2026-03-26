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
            max_size=20,
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
        await conn.execute(
            "ALTER TABLE reports ADD COLUMN IF NOT EXISTS report_type TEXT DEFAULT 'security'"
        )
        await conn.execute(
            "ALTER TABLE documents_meta ADD COLUMN IF NOT EXISTS chunk_count INTEGER DEFAULT 0"
        )
        await conn.execute(
            "ALTER TABLE alarms ADD COLUMN IF NOT EXISTS status TEXT NOT NULL DEFAULT 'triggered'"
        )
        await conn.execute(
            "ALTER TABLE alarms ADD COLUMN IF NOT EXISTS priority TEXT NOT NULL DEFAULT 'P3'"
        )
        await conn.execute("ALTER TABLE alarms ADD COLUMN IF NOT EXISTS analysis_id TEXT")
        await conn.execute("ALTER TABLE alarms ADD COLUMN IF NOT EXISTS resolved_at TIMESTAMPTZ")
        await conn.execute("ALTER TABLE alarms ADD COLUMN IF NOT EXISTS resolved_by TEXT")
        await conn.execute(
            "ALTER TABLE alarms ADD COLUMN IF NOT EXISTS investigation_notes TEXT"
        )
        await conn.execute(
            "ALTER TABLE devices ADD COLUMN IF NOT EXISTS security_grade TEXT NOT NULL DEFAULT 'GRADE_1'"
        )
        await conn.execute("ALTER TABLE devices ADD COLUMN IF NOT EXISTS firmware_version TEXT")
        await conn.execute(
            "ALTER TABLE devices ADD COLUMN IF NOT EXISTS last_health_check TIMESTAMPTZ"
        )
        await conn.execute("ALTER TABLE reports ADD COLUMN IF NOT EXISTS date_range_start DATE")
        await conn.execute("ALTER TABLE reports ADD COLUMN IF NOT EXISTS date_range_end DATE")
        await conn.execute("ALTER TABLE reports ADD COLUMN IF NOT EXISTS generated_by TEXT")
        await conn.execute("ALTER TABLE reports ADD COLUMN IF NOT EXISTS data_snapshot JSONB")
        await conn.execute(
            """
            CREATE TABLE IF NOT EXISTS device_health_logs (
                id BIGSERIAL PRIMARY KEY,
                device_id TEXT NOT NULL REFERENCES devices(device_id) ON DELETE CASCADE,
                checked_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                reachable BOOLEAN NOT NULL,
                port_open BOOLEAN NOT NULL,
                latency_ms INTEGER,
                status TEXT NOT NULL
            )
            """
        )
        await conn.execute(
            """
            CREATE TABLE IF NOT EXISTS analyses (
                analysis_id TEXT PRIMARY KEY,
                filename TEXT NOT NULL,
                size BIGINT NOT NULL,
                content_type TEXT,
                location TEXT,
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                result JSONB NOT NULL,
                media_type TEXT NOT NULL DEFAULT 'image'
            )
            """
        )
        await conn.execute(
            "ALTER TABLE analyses ADD COLUMN IF NOT EXISTS media_type TEXT NOT NULL DEFAULT 'image'"
        )
        await conn.execute("CREATE INDEX IF NOT EXISTS idx_alarms_status ON alarms(status)")
        await conn.execute("CREATE INDEX IF NOT EXISTS idx_alarms_device_id ON alarms(device_id)")
        await conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_alarms_timestamp ON alarms(timestamp DESC)"
        )
        await conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_health_logs_device ON device_health_logs(device_id, checked_at DESC)"
        )
        await conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_analyses_created ON analyses(created_at DESC)"
        )
        await conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_reports_type ON reports(report_type, created_at DESC)"
        )


def get_pool() -> asyncpg.Pool | None:
    return _pool
