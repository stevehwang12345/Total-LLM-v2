import importlib.util
import socket
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient


def _load_scanner_main():
    scanner_main = Path(__file__).resolve().parents[2] / "scanner" / "main.py"
    spec = importlib.util.spec_from_file_location("scanner_main_test", scanner_main)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_security_port_list():
    main = _load_scanner_main()
    assert 554 in main.SECURITY_PORTS
    assert 80 in main.SECURITY_PORTS
    assert 443 in main.SECURITY_PORTS
    assert 8080 in main.SECURITY_PORTS


def test_cidr_validation():
    import ipaddress

    net = ipaddress.ip_network("192.168.1.0/24", strict=False)
    assert net.prefixlen == 24
    assert 16 < 24


@pytest.mark.asyncio
async def test_arp_scan_mock():
    main = _load_scanner_main()

    mock_received = MagicMock()
    mock_received.psrc = "192.168.1.100"
    mock_received.hwsrc = "AA:BB:CC:DD:EE:FF"

    mock_ether_instance = MagicMock()
    mock_ether_instance.__truediv__.return_value = "packet"
    fake_scapy = SimpleNamespace(
        ARP=MagicMock(return_value="arp"),
        Ether=MagicMock(return_value=mock_ether_instance),
        srp=MagicMock(return_value=([("sent", mock_received)], [])),
    )

    with patch.object(main.importlib, "import_module", return_value=fake_scapy):
        result = await main._arp_scan("192.168.1.0/24")
        assert result == {"192.168.1.100": "AA:BB:CC:DD:EE:FF"}


def test_scan_store_409():
    main = _load_scanner_main()
    main._scan_store["fake-id"] = {
        "status": "running",
        "cidr": "192.168.1.0/24",
        "devices": [],
    }

    try:
        with TestClient(main.app) as client:
            resp = client.post("/scan", json={"cidr": "192.168.1.0/24"})
            assert resp.status_code == 409
    finally:
        del main._scan_store["fake-id"]


def test_scan_prefix_validation():
    main = _load_scanner_main()
    with TestClient(main.app) as client:
        resp = client.post("/scan", json={"cidr": "192.168.0.0/16"})
        assert resp.status_code == 422


@pytest.mark.asyncio
async def test_fingerprint_device_hostname_resolved():
    """DNS 조회 성공 시 hostname 반환"""
    main = _load_scanner_main()
    with patch("socket.gethostbyaddr", return_value=("device.local", [], ["192.168.1.1"])):
        result = await main._fingerprint_device("192.168.1.1", {})
    assert result.get("hostname") == "device.local"


@pytest.mark.asyncio
async def test_fingerprint_device_hostname_none_on_failure():
    """DNS 조회 실패 시 hostname=None (에러 없음)"""
    main = _load_scanner_main()
    with patch("socket.gethostbyaddr", side_effect=socket.herror):
        result = await main._fingerprint_device("192.168.1.1", {})
    assert result.get("hostname") is None
