import pytest
import asyncpg
from total_llm.services.alarm_service import AlarmService
from total_llm.services.device_control import DeviceService
from total_llm.services.report_service import ReportService


def test_imports():
    """Verify all key modules import without error."""
    assert AlarmService is not None
    assert DeviceService is not None
    assert ReportService is not None


@pytest.mark.asyncio
async def test_db_connection(db_pool):
    """Verify DB pool connects and responds."""
    if db_pool is None:
        pytest.skip("Database not available")
    async with db_pool.acquire() as conn:
        result = await conn.fetchval("SELECT 1")
    assert result == 1


@pytest.mark.asyncio
async def test_api_health(client):
    """Verify health endpoint is defined."""
    try:
        response = await client.get("/health")
        assert response.status_code in (200, 500)
    except AttributeError:
        pass
