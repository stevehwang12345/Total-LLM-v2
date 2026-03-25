import asyncio
import json
import logging
from datetime import datetime
from typing import AsyncGenerator
from uuid import uuid4

import asyncpg
from redis.asyncio import Redis

from total_llm.models.schemas import AlarmModel

logger = logging.getLogger(__name__)


class AlarmService:
    def __init__(self, redis_client: Redis | None = None) -> None:
        self._redis = redis_client
        self._stats_cache_key = "alarm:stats"
        self._subscribers: set[asyncio.Queue[str]] = set()
        self._subscriber_lock = asyncio.Lock()

    async def list_alarms(
        self,
        db_pool: asyncpg.Pool,
        limit: int = 50,
        severity_filter: str | None = None,
    ) -> list[AlarmModel]:
        limit = max(1, min(limit, 500))
        if severity_filter:
            query = (
                "SELECT alarm_id, device_id, severity, description, timestamp, acknowledged "
                "FROM alarms WHERE severity = $1 ORDER BY timestamp DESC LIMIT $2"
            )
            params = (severity_filter, limit)
        else:
            query = (
                "SELECT alarm_id, device_id, severity, description, timestamp, acknowledged "
                "FROM alarms ORDER BY timestamp DESC LIMIT $1"
            )
            params = (limit,)

        try:
            async with db_pool.acquire() as conn:
                rows = await conn.fetch(query, *params)
            return [AlarmModel.model_validate(dict(row)) for row in rows]
        except Exception:
            logger.exception("Failed listing alarms")
            raise

    async def get_alarm(self, db_pool: asyncpg.Pool, alarm_id: str) -> AlarmModel:
        query = (
            "SELECT alarm_id, device_id, severity, description, timestamp, acknowledged "
            "FROM alarms WHERE alarm_id = $1"
        )
        try:
            async with db_pool.acquire() as conn:
                row = await conn.fetchrow(query, alarm_id)
            if row is None:
                raise ValueError(f"Alarm not found: {alarm_id}")
            return AlarmModel.model_validate(dict(row))
        except Exception:
            logger.exception("Failed getting alarm: %s", alarm_id)
            raise

    async def create_alarm(self, db_pool: asyncpg.Pool, alarm: AlarmModel) -> AlarmModel:
        alarm_id = alarm.alarm_id or str(uuid4())
        query = (
            "INSERT INTO alarms (alarm_id, device_id, severity, description, timestamp, acknowledged) "
            "VALUES ($1, $2, $3, $4, $5, $6) "
            "RETURNING alarm_id, device_id, severity, description, timestamp, acknowledged"
        )

        try:
            async with db_pool.acquire() as conn:
                row = await conn.fetchrow(
                    query,
                    alarm_id,
                    alarm.device_id,
                    alarm.severity,
                    alarm.description,
                    alarm.timestamp,
                    alarm.acknowledged,
                )
            if row is None:
                raise RuntimeError("Failed to create alarm")

            created = AlarmModel.model_validate(dict(row))
            await self._invalidate_stats_cache()
            await self._broadcast_alarm("alarm_created", created)
            return created
        except Exception:
            logger.exception("Failed creating alarm: %s", alarm_id)
            raise

    async def acknowledge_alarm(self, db_pool: asyncpg.Pool, alarm_id: str) -> AlarmModel:
        query = (
            "UPDATE alarms SET acknowledged = TRUE "
            "WHERE alarm_id = $1 "
            "RETURNING alarm_id, device_id, severity, description, timestamp, acknowledged"
        )
        try:
            async with db_pool.acquire() as conn:
                row = await conn.fetchrow(query, alarm_id)
            if row is None:
                raise ValueError(f"Alarm not found: {alarm_id}")

            updated = AlarmModel.model_validate(dict(row))
            await self._invalidate_stats_cache()
            await self._broadcast_alarm("alarm_acknowledged", updated)
            return updated
        except Exception:
            logger.exception("Failed acknowledging alarm: %s", alarm_id)
            raise

    async def get_stats(self, db_pool: asyncpg.Pool) -> dict:
        cached = await self._read_stats_cache()
        if cached is not None:
            return cached

        severity_query = (
            "SELECT severity, COUNT(*)::int AS count FROM alarms GROUP BY severity"
        )
        trend_query = (
            "SELECT DATE(timestamp) AS day, COUNT(*)::int AS count "
            "FROM alarms "
            "WHERE timestamp >= NOW() - INTERVAL '7 days' "
            "GROUP BY DATE(timestamp) "
            "ORDER BY day"
        )

        try:
            async with db_pool.acquire() as conn:
                severity_rows = await conn.fetch(severity_query)
                trend_rows = await conn.fetch(trend_query)
        except Exception:
            logger.exception("Failed gathering alarm stats")
            raise

        stats = {
            "severity_counts": {row["severity"]: row["count"] for row in severity_rows},
            "daily_trends": [
                {"date": row["day"].isoformat(), "count": row["count"]}
                for row in trend_rows
            ],
            "generated_at": datetime.utcnow().isoformat(),
        }

        await self._write_stats_cache(stats)
        return stats

    async def stream_alarms(self) -> AsyncGenerator[str, None]:
        queue: asyncio.Queue[str] = asyncio.Queue()

        async with self._subscriber_lock:
            self._subscribers.add(queue)

        try:
            while True:
                try:
                    payload = await asyncio.wait_for(queue.get(), timeout=15)
                    yield payload
                except asyncio.TimeoutError:
                    yield "event: heartbeat\ndata: {}\n\n"
        finally:
            async with self._subscriber_lock:
                self._subscribers.discard(queue)

    async def _broadcast_alarm(self, event_name: str, alarm: AlarmModel) -> None:
        event = (
            f"event: {event_name}\n"
            f"data: {json.dumps(alarm.model_dump(mode='json'), ensure_ascii=False)}\n\n"
        )

        async with self._subscriber_lock:
            subscribers = list(self._subscribers)

        for queue in subscribers:
            queue.put_nowait(event)

    async def _read_stats_cache(self) -> dict | None:
        if self._redis is None:
            return None

        try:
            raw = await self._redis.get(self._stats_cache_key)
            if not raw:
                return None
            return json.loads(raw)
        except Exception:
            logger.exception("Failed reading alarm stats cache")
            return None

    async def _write_stats_cache(self, stats: dict) -> None:
        if self._redis is None:
            return

        try:
            await self._redis.set(
                self._stats_cache_key,
                json.dumps(stats, ensure_ascii=False),
                ex=60,
            )
        except Exception:
            logger.exception("Failed writing alarm stats cache")

    async def _invalidate_stats_cache(self) -> None:
        if self._redis is None:
            return

        try:
            await self._redis.delete(self._stats_cache_key)
        except Exception:
            logger.exception("Failed invalidating alarm stats cache")
