from __future__ import annotations

from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, patch

import pytest

from total_llm.services.tool_agent import stream_tool_response


class _FakeStream:
    def __init__(self, tokens: list[str]):
        self._tokens = tokens
        self._idx = 0

    def __aiter__(self):
        return self

    async def __anext__(self):
        if self._idx >= len(self._tokens):
            raise StopAsyncIteration
        token = self._tokens[self._idx]
        self._idx += 1
        delta = SimpleNamespace(content=token)
        choice = SimpleNamespace(delta=delta)
        return SimpleNamespace(choices=[choice])


class _FakeCompletions:
    def __init__(self):
        self._call_count = 0

    async def create(self, **kwargs):
        self._call_count += 1
        if self._call_count == 1:
            function = SimpleNamespace(name="list_devices", arguments='{"status":"online"}')
            tool_call = SimpleNamespace(id="tc-1", function=function)
            message = SimpleNamespace(content="", tool_calls=[tool_call])
            choice = SimpleNamespace(message=message)
            return SimpleNamespace(choices=[choice])

        if kwargs.get("stream"):
            return _FakeStream(["온라인 ", "장비는 ", "2대입니다."])

        message = SimpleNamespace(content="온라인 장비는 2대입니다.")
        choice = SimpleNamespace(message=message)
        return SimpleNamespace(choices=[choice])


class _FakeClient:
    def __init__(self):
        self.chat = SimpleNamespace(completions=_FakeCompletions())


@pytest.mark.asyncio
async def test_stream_tool_response_emits_tool_events_and_final_text():
    fake_client = _FakeClient()
    fake_pool: Any = object()

    with patch("total_llm.services.tool_agent.DeviceTools.execute", new=AsyncMock(return_value={"count": 2})):
        events = []
        async for event in stream_tool_response(
            db_pool=fake_pool,
            llm_client=fake_client,
            model_name="Qwen/Qwen3.5-9B",
            message="온라인 장비 조회해줘",
            conversation_id="conv-1",
        ):
            events.append(event)

    assert any(item.get("event") == "tool_call" for item in events)
    assert any(item.get("event") == "tool_result" for item in events)
    final_event = events[-1]
    assert final_event.get("done") is True
    assert "2대" in final_event.get("final_text", "")
