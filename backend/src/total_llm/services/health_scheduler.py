from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING

import asyncpg

if TYPE_CHECKING:
    pass

from total_llm.services.alarm_service import AlarmService
from total_llm.services.device_control import DeviceService

logger = logging.getLogger(__name__)

_device_service = DeviceService()
_alarm_service = AlarmService()


class HealthCheckScheduler:
    def __init__(self, interval_seconds: int = 30) -> None:
        self._interval = interval_seconds
        self._task: asyncio.Task | None = None
        self._running = False

    async def start(self, db_pool: asyncpg.Pool) -> None:
        if self._running:
            return
        self._running = True
        self._task = asyncio.create_task(self._loop(db_pool))
        logger.info("HealthCheckScheduler started (interval=%ds)", self._interval)

    async def stop(self) -> None:
        self._running = False
        if self._task and not self._task.done():
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        logger.info("HealthCheckScheduler stopped")

    async def _loop(self, db_pool: asyncpg.Pool) -> None:
        while self._running:
            try:
                await self._run_once(db_pool)
            except Exception:
                logger.exception("HealthCheckScheduler error in run cycle")
            await asyncio.sleep(self._interval)

    async def _run_once(self, db_pool: asyncpg.Pool) -> None:
        devices = await _device_service.list_devices(db_pool)
        for device in devices:
            try:
                result = await _device_service.check_device_health(device)
                await _device_service.log_health_check(db_pool, device.device_id, result)

                if result.get("status") == "offline":
                    in_cooldown = await _device_service.is_in_cooldown(db_pool, device.device_id)
                    if not in_cooldown:
                        await _alarm_service.create_alarm(
                            db_pool=db_pool,
                            device_id=device.device_id,
                            severity="높음",
                            description=(
                                f"[장비장애] {device.device_id} ({device.location}) "
                                f"응답 없음 — IP: {device.ip_address}:{device.port}"
                            ),
                            priority="P2",
                        )
            except Exception:
                logger.exception("Health check failed for device %s", device.device_id)


# Singleton
_scheduler: HealthCheckScheduler | None = None


def get_scheduler(interval_seconds: int = 30) -> HealthCheckScheduler:
    global _scheduler
    if _scheduler is None:
        _scheduler = HealthCheckScheduler(interval_seconds=interval_seconds)
    return _scheduler
