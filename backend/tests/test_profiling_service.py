from __future__ import annotations

import importlib.util
from pathlib import Path
from types import SimpleNamespace

import pytest


def _load_profiling_service():
    service_path = Path(__file__).resolve().parents[1] / "src" / "total_llm" / "services" / "profiling_service.py"
    spec = importlib.util.spec_from_file_location("profiling_service_test", service_path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.ProfilingService


class _FakeCompletions:
    def __init__(self, content: str):
        self._content = content

    async def create(self, **kwargs):
        _ = kwargs
        message = SimpleNamespace(content=self._content)
        choice = SimpleNamespace(message=message)
        return SimpleNamespace(choices=[choice])


class _FakeClient:
    def __init__(self, content: str):
        self.chat = SimpleNamespace(completions=_FakeCompletions(content))


class _PromptCaptureFakeClient:
    """프롬프트 내용을 캡처하는 fake LLM client"""

    def __init__(self, content: str):
        self.captured_messages = None
        self._content = content
        self.chat = SimpleNamespace(completions=SimpleNamespace(create=self._create))

    async def _create(self, **kwargs):
        self.captured_messages = kwargs.get("messages", [])
        message = SimpleNamespace(content=self._content)
        choice = SimpleNamespace(message=message)
        return SimpleNamespace(choices=[choice])


@pytest.mark.asyncio
async def test_profile_device_success():
    ProfilingService = _load_profiling_service()
    content = (
        '{"device_type":"CCTV","manufacturer":"Hanwha Vision","model_name":"XNV-8080R",'
        '"protocol":"RTSP","confidence":0.86,"reasoning":"RTSP port and ONVIF scope evidence",'
        '"suggested_device_id":"CCTV-NEW-001"}'
    )
    client = _FakeClient(content)

    service = ProfilingService()
    result = await service.profile_device(
        client,
        {
            "ip_address": "192.168.10.10",
            "open_ports": [554, 80],
            "onvif_info": {"endpoint": "http://192.168.10.10/onvif/device_service"},
        },
    )

    assert result["device_type"] == "CCTV"
    assert result["manufacturer"] == "Hanwha Vision"
    assert result["protocol"] == "RTSP"
    assert result["confidence"] == 0.86


@pytest.mark.asyncio
async def test_profile_device_fallback_when_invalid_json():
    ProfilingService = _load_profiling_service()
    client = _FakeClient("not-json-response")
    service = ProfilingService()

    result = await service.profile_device(client, {"ip_address": "192.168.1.20"})

    assert result["device_type"] == "Unknown"
    assert result["confidence"] == 0.0
    assert "Failed to parse" in result["reasoning"]


@pytest.mark.asyncio
async def test_re_verify_profile_returns_device_profile():
    ProfilingService = _load_profiling_service()
    content = (
        '{"device_type":"Firewall","manufacturer":"Palo Alto Networks","model_name":"PA-5220",'
        '"protocol":"HTTPS","confidence":0.92,"reasoning":"Corrected based on re-analysis",'
        '"suggested_device_id":"FW-CORRECTED-001"}'
    )
    client = _PromptCaptureFakeClient(content)

    service = ProfilingService()
    result = await service.re_verify_profile(
        client,
        {"ip_address": "192.168.1.1", "open_ports": [443, 22]},
        {"device_type": "Unknown", "manufacturer": "Unknown", "confidence": 0.0},
        [{"field": "device_type", "expected": "Firewall", "actual": "Unknown", "evidence": "port 443"}],
    )

    assert result["device_type"] == "Firewall"
    assert result["manufacturer"] == "Palo Alto Networks"
    assert result["confidence"] == 0.92


@pytest.mark.asyncio
async def test_re_verify_prompt_contains_previous_profile():
    ProfilingService = _load_profiling_service()
    content = (
        '{"device_type":"Router","manufacturer":"Cisco","model_name":"ISR4451",'
        '"protocol":"SSH","confidence":0.88,"reasoning":"Re-verified",'
        '"suggested_device_id":"ROUTER-001"}'
    )
    client = _PromptCaptureFakeClient(content)

    service = ProfilingService()
    previous_profile = {"device_type": "Switch", "manufacturer": "Cisco", "confidence": 0.5}
    await service.re_verify_profile(
        client,
        {"ip_address": "192.168.1.254"},
        previous_profile,
        [{"field": "device_type", "expected": "Router", "actual": "Switch", "evidence": "routing table"}],
    )

    assert client.captured_messages is not None
    user_message = next((m for m in client.captured_messages if m["role"] == "user"), None)
    assert user_message is not None
    assert "Previous profile" in user_message["content"]


@pytest.mark.asyncio
async def test_re_verify_prompt_contains_inconsistencies():
    ProfilingService = _load_profiling_service()
    content = (
        '{"device_type":"IDS","manufacturer":"Suricata","model_name":"v7",'
        '"protocol":"TCP","confidence":0.85,"reasoning":"Inconsistencies resolved",'
        '"suggested_device_id":"IDS-001"}'
    )
    client = _PromptCaptureFakeClient(content)

    service = ProfilingService()
    mismatches = [
        {"field": "device_type", "expected": "IDS", "actual": "Unknown", "evidence": "port 8080"},
        {"field": "protocol", "expected": "TCP", "actual": "UDP", "evidence": "packet analysis"},
    ]
    await service.re_verify_profile(
        client,
        {"ip_address": "192.168.1.100"},
        {"device_type": "Unknown", "protocol": "UDP"},
        mismatches,
    )

    assert client.captured_messages is not None
    user_message = next((m for m in client.captured_messages if m["role"] == "user"), None)
    assert user_message is not None
    assert "Inconsistencies found" in user_message["content"]
    assert "device_type: expected IDS, got Unknown (evidence: port 8080)" in user_message["content"]
    assert "protocol: expected TCP, got UDP (evidence: packet analysis)" in user_message["content"]
