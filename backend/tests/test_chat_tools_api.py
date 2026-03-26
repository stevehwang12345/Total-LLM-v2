from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from total_llm.api import chat as chat_api
from total_llm.app import app
from total_llm.core.dependencies import (
    get_db_pool,
    get_embedding_service,
    get_llm_client,
    get_qdrant_service,
    get_settings,
)


@pytest.fixture
def override_chat_tool_dependencies():
    app.dependency_overrides[get_db_pool] = lambda: object()
    app.dependency_overrides[get_llm_client] = lambda: object()
    app.dependency_overrides[get_qdrant_service] = lambda: object()
    app.dependency_overrides[get_embedding_service] = lambda: object()
    app.dependency_overrides[get_settings] = lambda: SimpleNamespace(llm=SimpleNamespace(model_name="Qwen/Qwen3.5-9B"))
    yield
    app.dependency_overrides.clear()


async def _fake_stream_tool_response(**kwargs):
    _ = kwargs
    yield {"event": "tool_call", "tool_name": "list_devices", "arguments": {"status": "online"}}
    yield {"event": "tool_result", "tool_name": "list_devices", "result": {"count": 2}}
    yield {"content": "온라인 장비는 2대입니다."}
    yield {"done": True, "conversation_id": "conv-tool", "final_text": "온라인 장비는 2대입니다."}


@pytest.mark.asyncio
async def test_chat_use_tools_streams_tool_events(client, override_chat_tool_dependencies):
    with (
        patch.object(chat_api, "_ensure_conversation", new=AsyncMock(return_value=None)),
        patch.object(chat_api, "_save_message", new=AsyncMock(return_value=None)),
        patch.object(chat_api, "stream_tool_response", new=_fake_stream_tool_response),
    ):
        response = await client.post(
            "/api/chat",
            json={"message": "온라인 장비 알려줘", "use_tools": True, "use_rag": False},
        )

    assert response.status_code == 200
    body = response.text
    assert '"event": "tool_call"' in body
    assert '"event": "tool_result"' in body
    assert "온라인 장비는 2대입니다." in body
