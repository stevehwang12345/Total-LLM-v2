import asyncio
import os
import pytest
import asyncpg
from pathlib import Path
from unittest.mock import patch
from httpx import AsyncClient, ASGITransport
from total_llm.core.config import get_settings

# Mock directory creation at import time to avoid permission errors
with patch.object(Path, 'mkdir'):
    from total_llm.app import app


@pytest.fixture(scope="session")
def event_loop():
    """Create a session-scoped event loop."""
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


@pytest.fixture(scope="session")
async def db_pool():
    """Session-scoped DB pool — shared across all tests."""
    settings = get_settings()
    
    host = os.environ.get("POSTGRES_HOST", settings.database.host)
    port = int(os.environ.get("POSTGRES_PORT", settings.database.port))
    database = os.environ.get("POSTGRES_DB", settings.database.database)
    user = os.environ.get("POSTGRES_USER", settings.database.username)
    password = os.environ.get("POSTGRES_PASSWORD", settings.database.password)
    
    try:
        pool = await asyncpg.create_pool(
            host=host,
            port=port,
            database=database,
            user=user,
            password=password,
            min_size=1,
            max_size=5,
        )
        yield pool
        await pool.close()
    except (ConnectionRefusedError, asyncpg.CannotConnectNowError, OSError):
        yield None


@pytest.fixture
async def db_conn(db_pool):
    """Per-test transaction that rolls back after each test."""
    async with db_pool.acquire() as conn:
        tr = conn.transaction()
        await tr.start()
        yield conn
        await tr.rollback()


@pytest.fixture
async def client():
    """FastAPI AsyncClient for API tests."""
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as ac:
        yield ac
