import asyncio
import json
import logging
from datetime import datetime
from typing import Any
from typing import AsyncGenerator
from uuid import uuid4

import asyncpg
from redis.asyncio import Redis

from total_llm.core.exceptions import ValidationError
from total_llm.models.schemas import AlarmModel

logger = logging.getLogger(__name__)


ALARM_STATUSES = {
    "triggered",
    "acknowledged",
    "investigating",
    "resolved",
    "closed",
    "false_alarm",
}

ALARM_VALID_TRANSITIONS: dict[str, set[str]] = {
    "triggered": {"acknowledged", "false_alarm"},
    "acknowledged": {"investigating", "resolved", "false_alarm"},
    "investigating": {"resolved", "false_alarm"},
    "resolved": {"closed"},
    "closed": set(),
    "false_alarm": {"closed"},
}

ALARM_PRIORITIES = {"P1", "P2", "P3", "P4"}


class AlarmService:
    def __init__(self, redis_client: Redis | None = None) -> None:
        self._redis = redis_client
        self._stats_cache_key = "alarm:stats"
        self._subscribers: set[asyncio.Queue[str]] = set()
        self._subscriber_lock = asyncio.Lock()

    async def list_alarms(
        self,
        db_pool: asyncpg.Pool,
        severity: str | None = None,
        limit: int = 50,
        status: str | None = None,
        priority: str | None = None,
        *,
        severity_filter: str | None = None,
        status_filter: str | None = None,
        priority_filter: str | None = None,
    ) -> list[AlarmModel]:
        limit = max(1, min(limit, 500))
        severity = severity if severity is not None else severity_filter
        status = status if status is not None else status_filter
        priority = priority if priority is not None else priority_filter

        conditions: list[str] = []
        params: list[Any] = []

        if severity:
            params.append(severity)
            conditions.append(f"severity = ${len(params)}")
        if status:
            params.append(status)
            conditions.append(f"status = ${len(params)}")
        if priority:
            params.append(priority)
            conditions.append(f"priority = ${len(params)}")

        query = (
            "SELECT alarm_id, device_id, severity, description, timestamp, acknowledged "
            "FROM alarms"
        )
        if conditions:
            query += " WHERE " + " AND ".join(conditions)
        params.append(limit)
        query += f" ORDER BY timestamp DESC LIMIT ${len(params)}"

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

    async def create_alarm(
        self,
        db_pool: asyncpg.Pool,
        device_id: str,
        severity: str,
        description: str,
        priority: str = "P3",
        analysis_id: str | None = None,
        status: str = "triggered",
    ) -> AlarmModel:
        if status not in ALARM_STATUSES:
            raise ValidationError(f"유효하지 않은 상태: {status}")
        if priority not in ALARM_PRIORITIES:
            raise ValidationError(f"유효하지 않은 우선순위: {priority}")

        alarm_id = str(uuid4())
        query = (
            "INSERT INTO alarms (alarm_id, device_id, severity, description, status, priority, analysis_id) "
            "VALUES ($1, $2, $3, $4, $5, $6, $7) "
            "RETURNING alarm_id, device_id, severity, description, timestamp, acknowledged"
        )

        try:
            async with db_pool.acquire() as conn:
                async with conn.transaction():
                    row = await conn.fetchrow(
                        query,
                        alarm_id,
                        device_id,
                        severity,
                        description,
                        status,
                        priority,
                        analysis_id,
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

    async def update_alarm_status(
        self,
        db_pool: asyncpg.Pool,
        alarm_id: str,
        new_status: str,
        operator_id: str | None = None,
        notes: str | None = None,
    ) -> AlarmModel:
        if new_status not in ALARM_STATUSES:
            raise ValidationError(f"유효하지 않은 상태: {new_status}")

        select_query = "SELECT alarm_id, status FROM alarms WHERE alarm_id = $1"
        update_query = (
            "UPDATE alarms SET "
            "status = $2, "
            "acknowledged = CASE WHEN $2 = 'triggered' THEN acknowledged ELSE TRUE END, "
            "resolved_at = CASE "
            "    WHEN $2 IN ('resolved', 'closed') THEN COALESCE(resolved_at, NOW()) "
            "    ELSE resolved_at "
            "END, "
            "resolved_by = CASE "
            "    WHEN $2 IN ('resolved', 'closed') AND $3::TEXT IS NOT NULL THEN $3::TEXT "
            "    ELSE resolved_by "
            "END, "
            "investigation_notes = CASE "
            "    WHEN $4::TEXT IS NOT NULL THEN $4::TEXT "
            "    ELSE investigation_notes "
            "END "
            "WHERE alarm_id = $1 "
            "RETURNING alarm_id, device_id, severity, description, timestamp, acknowledged"
        )

        try:
            async with db_pool.acquire() as conn:
                async with conn.transaction():
                    current_row = await conn.fetchrow(select_query, alarm_id)
                    if current_row is None:
                        raise ValueError(f"Alarm not found: {alarm_id}")

                    current_status = current_row["status"]
                    allowed_next = ALARM_VALID_TRANSITIONS.get(current_status, set())
                    if new_status not in allowed_next:
                        raise ValidationError(
                            f"유효하지 않은 상태 전이: {current_status} → {new_status}"
                        )

                    row = await conn.fetchrow(
                        update_query,
                        alarm_id,
                        new_status,
                        operator_id,
                        notes,
                    )

            if row is None:
                raise RuntimeError(f"Failed to update alarm status: {alarm_id}")

            updated = AlarmModel.model_validate(dict(row))
            await self._invalidate_stats_cache()

            event_name = (
                "alarm_acknowledged" if new_status == "acknowledged" else "alarm_status_updated"
            )
            await self._broadcast_alarm(event_name, updated)
            return updated
        except Exception:
            logger.exception("Failed updating alarm status: %s -> %s", alarm_id, new_status)
            raise

    async def acknowledge_alarm(self, db_pool: asyncpg.Pool, alarm_id: str) -> AlarmModel:
        try:
            return await self.update_alarm_status(
                db_pool=db_pool,
                alarm_id=alarm_id,
                new_status="acknowledged",
            )
        except Exception:
            logger.exception("Failed acknowledging alarm: %s", alarm_id)
            raise

    async def get_stats(self, db_pool: asyncpg.Pool) -> dict:
        cached = await self._read_stats_cache()
        if cached is not None:
            return cached

        total_query = "SELECT COUNT(*)::int AS count FROM alarms"
        severity_query = (
            "SELECT severity, COUNT(*)::int AS count FROM alarms GROUP BY severity"
        )
        unack_query = "SELECT COUNT(*)::int AS count FROM alarms WHERE acknowledged = FALSE"
        trend_query = (
            "SELECT DATE(timestamp) AS day, COUNT(*)::int AS count "
            "FROM alarms "
            "WHERE timestamp >= NOW() - INTERVAL '7 days' "
            "GROUP BY DATE(timestamp) "
            "ORDER BY day"
        )

        try:
            async with db_pool.acquire() as conn:
                total_row = await conn.fetchrow(total_query)
                severity_rows = await conn.fetch(severity_query)
                unack_row = await conn.fetchrow(unack_query)
                trend_rows = await conn.fetch(trend_query)
        except Exception:
            logger.exception("Failed gathering alarm stats")
            raise

        stats = {
            "total": total_row["count"],
            "by_severity": {row["severity"]: row["count"] for row in severity_rows},
            "unacknowledged": unack_row["count"],
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
