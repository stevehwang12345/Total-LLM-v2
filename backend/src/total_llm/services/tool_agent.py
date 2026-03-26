from __future__ import annotations

import json
import logging
from collections.abc import AsyncGenerator
from typing import Any

import asyncpg

from .device_tools import DeviceTools

logger = logging.getLogger(__name__)


async def stream_tool_response(
    *,
    db_pool: asyncpg.Pool,
    llm_client: Any,
    model_name: str,
    message: str,
    conversation_id: str,
) -> AsyncGenerator[dict[str, Any], None]:
    tools_runtime = DeviceTools(db_pool)
    tool_specs = DeviceTools.tool_specs()

    messages: list[dict[str, Any]] = [
        {
            "role": "system",
            "content": (
                "You are a security operations assistant. "
                "When needed, call tools to retrieve exact device/scan data. "
                "Answer in concise Korean unless the user requests another language."
            ),
        },
        {"role": "user", "content": message},
    ]

    first_response = await llm_client.chat.completions.create(
        model=model_name,
        messages=messages,
        tools=tool_specs,
        tool_choice="auto",
        temperature=0.1,
        extra_body={"chat_template_kwargs": {"enable_thinking": False}},
    )

    if not first_response.choices:
        yield {
            "done": True,
            "conversation_id": conversation_id,
            "final_text": "",
        }
        return

    message_obj = first_response.choices[0].message
    assistant_text = (getattr(message_obj, "content", None) or "").strip()
    tool_calls = _extract_tool_calls(message_obj)

    if not tool_calls:
        if assistant_text:
            yield {"content": assistant_text}
        yield {
            "done": True,
            "conversation_id": conversation_id,
            "final_text": assistant_text,
        }
        return

    assistant_message_for_history: dict[str, Any] = {
        "role": "assistant",
        "content": assistant_text,
        "tool_calls": [],
    }
    messages.append(assistant_message_for_history)

    for tool_call in tool_calls:
        call_id = tool_call["id"]
        name = tool_call["name"]
        arguments = tool_call["arguments"]

        assistant_message_for_history["tool_calls"].append(
            {
                "id": call_id,
                "type": "function",
                "function": {
                    "name": name,
                    "arguments": json.dumps(arguments, ensure_ascii=False),
                },
            }
        )

        yield {
            "event": "tool_call",
            "tool_name": name,
            "arguments": arguments,
        }

        try:
            result = await tools_runtime.execute(name, arguments)
        except Exception as exc:
            logger.exception("Tool execution failed: %s", name)
            result = {"error": str(exc), "tool_name": name}

        yield {
            "event": "tool_result",
            "tool_name": name,
            "result": result,
        }

        messages.append(
            {
                "role": "tool",
                "tool_call_id": call_id,
                "content": json.dumps(result, ensure_ascii=False),
            }
        )


    final_text = ""
    try:
        stream = await llm_client.chat.completions.create(
            model=model_name,
            messages=messages,
            temperature=0.1,
            stream=True,
            extra_body={"chat_template_kwargs": {"enable_thinking": False}},
        )
        async for chunk in stream:
            if not chunk.choices:
                continue
            delta = chunk.choices[0].delta
            token = (delta.content or "") if delta else ""
            if not token:
                continue
            final_text += token
            yield {"content": token}
    except Exception:
        logger.exception("Tool-agent streaming failed, using fallback non-stream completion")
        completion = await llm_client.chat.completions.create(
            model=model_name,
            messages=messages,
            temperature=0.1,
            extra_body={"chat_template_kwargs": {"enable_thinking": False}},
        )
        if completion.choices:
            final_text = (completion.choices[0].message.content or "").strip()
            if final_text:
                yield {"content": final_text}

    yield {
        "done": True,
        "conversation_id": conversation_id,
        "final_text": final_text.strip(),
    }


def _extract_tool_calls(message_obj: Any) -> list[dict[str, Any]]:
    raw_calls = getattr(message_obj, "tool_calls", None) or []
    calls: list[dict[str, Any]] = []

    for raw in raw_calls:
        call_id = getattr(raw, "id", None) or ""
        function_obj = getattr(raw, "function", None)
        if function_obj is None:
            continue
        name = getattr(function_obj, "name", None) or ""
        raw_arguments = getattr(function_obj, "arguments", None) or "{}"

        arguments: dict[str, Any]
        if isinstance(raw_arguments, dict):
            arguments = raw_arguments
        else:
            try:
                parsed = json.loads(str(raw_arguments))
                arguments = parsed if isinstance(parsed, dict) else {}
            except json.JSONDecodeError:
                arguments = {}

        if not name:
            continue
        calls.append({"id": str(call_id or name), "name": str(name), "arguments": arguments})

    return calls
