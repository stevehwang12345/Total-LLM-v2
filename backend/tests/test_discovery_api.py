from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from total_llm.app import app
from total_llm.core.dependencies import get_db_pool, get_llm_client, get_settings
from total_llm.services.discovery_service import DiscoveryService


@pytest.fixture
def override_dependencies():
    app.dependency_overrides[get_db_pool] = lambda: object()
    app.dependency_overrides[get_settings] = lambda: SimpleNamespace(scanner_base_url="http://scanner:9003")
    app.dependency_overrides[get_llm_client] = lambda: object()
    yield
    app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_start_discovery_scan(client, override_dependencies):
    with patch.object(
        DiscoveryService,
        "start_scan",
        new=AsyncMock(return_value={"scan_id": "scan-123", "cidr": "192.168.1.0/24", "status": "running"}),
    ):
        response = await client.post(
            "/api/discovery/scans",
            json={"cidr": "192.168.1.0/24", "timeout_sec": 90},
        )

    assert response.status_code == 200
    payload = response.json()
    assert payload["scan_id"] == "scan-123"
    assert payload["status"] == "running"


@pytest.mark.asyncio
async def test_list_discovery_scans(client, override_dependencies):
    with patch.object(
        DiscoveryService,
        "list_scans",
        new=AsyncMock(return_value=[{"scan_id": "scan-001", "status": "completed"}]),
    ):
        response = await client.get("/api/discovery/scans?limit=10")

    assert response.status_code == 200
    payload = response.json()
    assert "items" in payload
    assert len(payload["items"]) == 1
    assert payload["items"][0]["scan_id"] == "scan-001"


@pytest.mark.asyncio
async def test_get_discovery_scan_status_not_found(client, override_dependencies):
    with patch.object(DiscoveryService, "get_scan_status", new=AsyncMock(side_effect=LookupError("Scan not found: scan-x"))):
        response = await client.get("/api/discovery/scans/scan-x")

    assert response.status_code == 404
    payload = response.json()
    assert payload["error"]["code"] == "NOT_FOUND"


@pytest.mark.asyncio
async def test_get_discovery_scan_results(client, override_dependencies):
    with patch.object(
        DiscoveryService,
        "get_scan_results",
        new=AsyncMock(
            return_value={
                "scan": {"scan_id": "scan-55", "status": "completed"},
                "devices": [{"ip_address": "192.168.1.100"}],
                "total_found": 1,
            }
        ),
    ):
        response = await client.get("/api/discovery/scans/scan-55/results")

    assert response.status_code == 200
    payload = response.json()
    assert payload["total_found"] == 1
    assert payload["devices"][0]["ip_address"] == "192.168.1.100"


@pytest.mark.asyncio
async def test_profile_discovered_device(client, override_dependencies):
    with patch.object(
        DiscoveryService,
        "profile_discovered_device",
        new=AsyncMock(
            return_value={
                "scan_id": "scan-2",
                "discovered_id": 10,
                "llm_profile": {"device_type": "CCTV", "confidence": 0.83},
            }
        ),
    ):
        response = await client.post("/api/discovery/scans/scan-2/devices/10/profile")

    assert response.status_code == 200
    payload = response.json()
    assert payload["discovered_id"] == 10
    assert payload["llm_profile"]["device_type"] == "CCTV"


@pytest.mark.asyncio
async def test_profile_auto_flow_consistent(client, override_dependencies):
    with patch.object(
        DiscoveryService,
        "profile_discovered_device",
        new=AsyncMock(
            return_value={
                "scan_id": "s1",
                "discovered_id": 1,
                "llm_profile": {
                    "device_type": "CCTV",
                    "confidence": 0.9,
                    "consistency_result": {"consistent": True, "score": 0.9, "mismatches": []},
                },
            }
        ),
    ):
        response = await client.post("/api/discovery/scans/s1/devices/1/profile")

    assert response.status_code == 200
    data = response.json()
    assert data["llm_profile"]["consistency_result"]["consistent"] is True


@pytest.mark.asyncio
async def test_profile_auto_flow_inconsistent(client, override_dependencies):
    with patch.object(
        DiscoveryService,
        "profile_discovered_device",
        new=AsyncMock(
            return_value={
                "scan_id": "s1",
                "discovered_id": 1,
                "llm_profile": {
                    "device_type": "ACU",
                    "confidence": 0.8,
                    "consistency_result": {
                        "consistent": False,
                        "score": 0.2,
                        "mismatches": [{"field": "device_type", "severity": "high"}],
                    },
                },
            }
        ),
    ):
        response = await client.post("/api/discovery/scans/s1/devices/1/profile")

    assert response.status_code == 200
    data = response.json()
    assert data["llm_profile"]["consistency_result"]["consistent"] is False


@pytest.mark.asyncio
async def test_register_discovered_device(client, override_dependencies):
    with patch.object(
        DiscoveryService,
        "register_discovered_device",
        new=AsyncMock(
            return_value={
                "scan_id": "scan-2",
                "discovered_id": 10,
                "registered_device": {"device_id": "CCTV-010", "status": "online"},
            }
        ),
    ):
        response = await client.post(
            "/api/discovery/scans/scan-2/devices/10/register",
            json={"location": "Gate A", "status": "online"},
        )

    assert response.status_code == 200
    payload = response.json()
    assert payload["registered_device"]["device_id"] == "CCTV-010"


@pytest.mark.asyncio
async def test_register_inconsistent_without_manual_override(client, override_dependencies):
    with patch.object(
        DiscoveryService,
        "register_discovered_device",
        new=AsyncMock(side_effect=ValueError("정합성 검증 실패. 수동 입력이 필요합니다.")),
    ):
        response = await client.post(
            "/api/discovery/scans/scan-2/devices/10/register",
            json={"location": "Test", "status": "online", "manual_override": False},
        )

    assert response.status_code == 422
    assert "수동 입력" in response.json()["error"]["message"]


@pytest.mark.asyncio
async def test_register_inconsistent_with_manual_override(client, override_dependencies):
    with patch.object(
        DiscoveryService,
        "register_discovered_device",
        new=AsyncMock(
            return_value={
                "scan_id": "scan-2",
                "discovered_id": 10,
                "registered_device": {"device_id": "CCTV-010", "status": "online"},
            }
        ),
    ):
        response = await client.post(
            "/api/discovery/scans/scan-2/devices/10/register",
            json={
                "device_type": "CCTV",
                "protocol": "RTSP",
                "port": 554,
                "location": "Manual Input",
                "status": "online",
                "manual_override": True,
            },
        )

    assert response.status_code == 200
    assert response.json()["registered_device"]["device_id"] == "CCTV-010"


@pytest.mark.asyncio
async def test_register_discovered_device_not_found(client, override_dependencies):
    with patch.object(
        DiscoveryService,
        "register_discovered_device",
        new=AsyncMock(side_effect=LookupError("Discovered device not found")),
    ):
        response = await client.post(
            "/api/discovery/scans/scan-2/devices/99/register",
            json={"location": "Gate A", "status": "online"},
        )

    assert response.status_code == 404
    payload = response.json()
    assert payload["error"]["code"] == "NOT_FOUND"
