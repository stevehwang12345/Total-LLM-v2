from __future__ import annotations

import json
import logging
from collections.abc import AsyncGenerator
from uuid import uuid4

import asyncpg
from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse

from ..core.dependencies import (
    get_db_pool,
    get_embedding_service,
    get_llm_client,
    get_qdrant_service,
    get_settings,
)
from ..core.exceptions import ExternalServiceError, ValidationError
from ..models.schemas import ChatRequest
from ..services.embedding import EmbeddingService
from ..services.rag_agent import create_rag_graph, stream_rag_response

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/chat", tags=["chat"])


@router.post("")
async def chat(
    request: ChatRequest,
    db_pool: asyncpg.Pool = Depends(get_db_pool),
    llm_client=Depends(get_llm_client),
    qdrant_service=Depends(get_qdrant_service),
    embedding_service=Depends(get_embedding_service),
    settings=Depends(get_settings),
):
    message = (request.message or "").strip()
    if not message:
        raise ValidationError("message is required")

    conversation_id = request.conversation_id or str(uuid4())
    model_name = settings.llm.model_name

    await _ensure_conversation(db_pool, conversation_id)
    await _save_message(db_pool, conversation_id, role="user", content=message)

    embedding_runtime = embedding_service
    if not hasattr(embedding_runtime, "embed_query"):
        embedding_runtime = EmbeddingService()

    async def generate() -> AsyncGenerator[str, None]:
        yield _sse({"conversation_id": conversation_id})
        assistant_parts: list[str] = []

        try:
            if request.use_rag:
                graph = create_rag_graph(
                    qdrant_service=qdrant_service,
                    embedding_service=embedding_runtime,
                    llm_client=llm_client,
                    model_name=model_name,
                )

                async for event in stream_rag_response(
                    graph=graph,
                    query=message,
                    conversation_id=conversation_id,
                ):
                    if event.get("content"):
                        token = str(event["content"])
                        assistant_parts.append(token)
                        yield _sse({"content": token})
                    if event.get("done"):
                        break
            else:
                stream = await llm_client.chat.completions.create(
                    model=model_name,
                    messages=[{"role": "user", "content": message}],
                    temperature=0.2,
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
                    assistant_parts.append(token)
                    yield _sse({"content": token})

        except Exception as exc:
            logger.exception("Chat streaming failed")
            yield _sse(
                {
                    "error": {
                        "code": "RAG_ERROR" if request.use_rag else "EXTERNAL_SERVICE_ERROR",
                        "message": str(exc),
                    },
                    "done": True,
                }
            )
            return

        assistant_message = "".join(assistant_parts).strip()
        if assistant_message:
            try:
                await _save_message(
                    db_pool,
                    conversation_id,
                    role="assistant",
                    content=assistant_message,
                )
            except Exception:
                logger.exception("Failed saving assistant message: %s", conversation_id)

        yield _sse({"done": True})

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


def _sse(payload: dict) -> str:
    return f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"


async def _ensure_conversation(db_pool: asyncpg.Pool, conversation_id: str) -> None:
    query = (
        "INSERT INTO conversations (conversation_id, updated_at) VALUES ($1, NOW()) "
        "ON CONFLICT (conversation_id) DO UPDATE SET updated_at = NOW()"
    )
    try:
        async with db_pool.acquire() as conn:
            await conn.execute(query, conversation_id)
    except Exception as exc:
        logger.exception("Failed ensuring conversation: %s", conversation_id)
        raise ExternalServiceError("Failed to persist conversation") from exc


async def _save_message(
    db_pool: asyncpg.Pool,
    conversation_id: str,
    role: str,
    content: str,
) -> None:
    query = (
        "INSERT INTO messages (conversation_id, role, content) "
        "VALUES ($1, $2, $3)"
    )
    try:
        async with db_pool.acquire() as conn:
            await conn.execute(query, conversation_id, role, content)
            await conn.execute(
                "UPDATE conversations SET updated_at = NOW() WHERE conversation_id = $1",
                conversation_id,
            )
    except Exception as exc:
        logger.exception("Failed storing message: %s", conversation_id)
        raise ExternalServiceError("Failed to persist message") from exc
