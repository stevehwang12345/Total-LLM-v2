from __future__ import annotations

import inspect
import logging
import time

import aiohttp
import asyncpg
from fastapi import APIRouter, Depends

from ..core.dependencies import (
    get_db_pool,
    get_embedding_service,
    get_qdrant_service,
    get_redis,
    get_settings,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/system", tags=["system"])


@router.get("/servers")
async def server_status(settings=Depends(get_settings)):
    llm_health_url = _to_health_url(settings.llm.base_url)
    vlm_health_url = _to_health_url(settings.vlm.base_url)

    llm_status = await _http_health(llm_health_url)
    vlm_status = await _http_health(vlm_health_url)

    return {
        "llm": {
            "base_url": settings.llm.base_url,
            "health_url": llm_health_url,
            "model": settings.llm.model_name,
            **llm_status,
        },
        "vlm": {
            "base_url": settings.vlm.base_url,
            "health_url": vlm_health_url,
            "model": settings.vlm.model_name,
            **vlm_status,
        },
    }


@router.get("/health")
async def system_health(
    db_pool: asyncpg.Pool = Depends(get_db_pool),
    redis_client=Depends(get_redis),
    qdrant_service=Depends(get_qdrant_service),
    embedding_service=Depends(get_embedding_service),
    settings=Depends(get_settings),
):
    llm_health_url = _to_health_url(settings.llm.base_url)
    vlm_health_url = _to_health_url(settings.vlm.base_url)

    database_status = await _database_health(db_pool)
    redis_status = await _redis_health(redis_client)
    qdrant_status = await _qdrant_health(qdrant_service, settings.qdrant.collection_name)
    embedding_status = _embedding_health(embedding_service)
    llm_status = await _http_health(llm_health_url)
    vlm_status = await _http_health(vlm_health_url)

    services = {
        "database": database_status,
        "redis": redis_status,
        "qdrant": qdrant_status,
        "embedding": embedding_status,
        "llm": llm_status,
        "vlm": vlm_status,
    }
    overall = "up" if all(item.get("up") for item in services.values()) else "degraded"
    return {
        "status": overall,
        "services": services,
    }


def _to_health_url(base_url: str) -> str:
    normalized = (base_url or "").rstrip("/")
    if normalized.endswith("/v1"):
        normalized = normalized[:-3]
    return f"{normalized}/health"


async def _http_health(url: str) -> dict:
    started = time.perf_counter()
    timeout = aiohttp.ClientTimeout(total=4)
    try:
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.get(url) as response:
                latency_ms = int((time.perf_counter() - started) * 1000)
                return {
                    "up": 200 <= response.status < 300,
                    "status_code": response.status,
                    "latency_ms": latency_ms,
                }
    except Exception as exc:
        latency_ms = int((time.perf_counter() - started) * 1000)
        return {
            "up": False,
            "error": str(exc),
            "latency_ms": latency_ms,
        }


async def _database_health(db_pool: asyncpg.Pool) -> dict:
    try:
        async with db_pool.acquire() as conn:
            await conn.fetchval("SELECT 1")
        return {"up": True}
    except Exception as exc:
        logger.exception("Database health check failed")
        return {"up": False, "error": str(exc)}


async def _redis_health(redis_client) -> dict:
    if redis_client is None:
        return {"up": False, "error": "redis client unavailable"}
    try:
        pong = await redis_client.ping()
        return {"up": bool(pong)}
    except Exception as exc:
        logger.exception("Redis health check failed")
        return {"up": False, "error": str(exc)}


async def _qdrant_health(qdrant_service, collection_name: str) -> dict:
    if qdrant_service is None:
        return {"up": False, "error": "qdrant service unavailable"}

    if hasattr(qdrant_service, "count"):
        try:
            result = qdrant_service.count()
            if inspect.isawaitable(result):
                result = await result
            if isinstance(result, int):
                return {"up": True, "points": result}
            if hasattr(result, "count"):
                return {"up": True, "points": int(result.count)}
            return {"up": True}
        except Exception as exc:
            logger.exception("Qdrant count check failed")
            return {"up": False, "error": str(exc)}

    if hasattr(qdrant_service, "collection_exists"):
        try:
            result = qdrant_service.collection_exists(collection_name)
            if inspect.isawaitable(result):
                result = await result
            return {"up": bool(result), "collection": collection_name}
        except Exception as exc:
            logger.exception("Qdrant collection check failed")
            return {"up": False, "error": str(exc)}

    return {"up": False, "error": "unsupported qdrant client type"}


def _embedding_health(embedding_service) -> dict:
    if embedding_service is None:
        return {"up": False, "error": "embedding service unavailable"}

    if isinstance(embedding_service, dict):
        model_name = embedding_service.get("model_name")
        return {
            "up": bool(model_name),
            "model": model_name,
            "device": embedding_service.get("device"),
        }

    model_name = getattr(embedding_service, "model_name", None)
    dimension = getattr(embedding_service, "dimension", None)
    return {
        "up": True,
        "model": model_name,
        "dimension": dimension,
    }
