from __future__ import annotations

import json
import logging

import asyncpg
from fastapi import APIRouter, Depends, Query
from fastapi.responses import StreamingResponse

from ..core.dependencies import get_db_pool, get_redis, get_settings
from ..core.exceptions import ExternalServiceError, NotFoundError
from ..services.alarm_service import AlarmService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/alarms", tags=["alarms"])

_alarm_service: AlarmService | None = None


def _get_alarm_service(redis_client) -> AlarmService:
    global _alarm_service
    if _alarm_service is None:
        _alarm_service = AlarmService(redis_client=redis_client)
    return _alarm_service


@router.get("")
async def list_alarms(
    severity: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=500),
    db_pool: asyncpg.Pool = Depends(get_db_pool),
    redis_client=Depends(get_redis),
    settings=Depends(get_settings),
):
    _ = settings
    alarm_service = _get_alarm_service(redis_client)
    try:
        return await alarm_service.list_alarms(
            db_pool=db_pool,
            severity_filter=severity,
            limit=limit,
        )
    except Exception as exc:
        logger.exception("Failed listing alarms")
        raise ExternalServiceError("Failed listing alarms") from exc


@router.get("/stream")
async def stream_alarms(
    redis_client=Depends(get_redis),
    settings=Depends(get_settings),
):
    _ = settings
    alarm_service = _get_alarm_service(redis_client)

    async def event_generator():
        try:
            async for event in alarm_service.stream_alarms():
                yield event
        except Exception as exc:
            logger.exception("Alarm stream failed")
            yield (
                "event: error\n"
                f"data: {json.dumps({'code': 'EXTERNAL_SERVICE_ERROR', 'message': str(exc)})}\n\n"
            )

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


@router.get("/stats")
async def alarm_stats(
    db_pool: asyncpg.Pool = Depends(get_db_pool),
    redis_client=Depends(get_redis),
    settings=Depends(get_settings),
):
    _ = settings
    alarm_service = _get_alarm_service(redis_client)
    try:
        return await alarm_service.get_stats(db_pool=db_pool)
    except Exception as exc:
        logger.exception("Failed loading alarm stats")
        raise ExternalServiceError("Failed loading alarm stats") from exc


@router.post("/{alarm_id}/acknowledge")
async def acknowledge_alarm(
    alarm_id: str,
    db_pool: asyncpg.Pool = Depends(get_db_pool),
    redis_client=Depends(get_redis),
    settings=Depends(get_settings),
):
    _ = settings
    alarm_service = _get_alarm_service(redis_client)
    try:
        return await alarm_service.acknowledge_alarm(db_pool=db_pool, alarm_id=alarm_id)
    except ValueError as exc:
        raise NotFoundError(str(exc)) from exc
    except Exception as exc:
        logger.exception("Failed acknowledging alarm: %s", alarm_id)
        raise ExternalServiceError("Failed acknowledging alarm") from exc
