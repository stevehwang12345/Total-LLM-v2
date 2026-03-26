from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta

import asyncpg

from total_llm.services.report_service import ReportService

logger = logging.getLogger(__name__)

_report_service = ReportService()


class ReportScheduler:
    def __init__(self) -> None:
        self._task: asyncio.Task | None = None
        self._running = False

    async def start(self, db_pool: asyncpg.Pool) -> None:
        if self._running:
            return
        self._running = True
        self._task = asyncio.create_task(self._loop(db_pool))
        logger.info("ReportScheduler started")

    async def stop(self) -> None:
        self._running = False
        if self._task and not self._task.done():
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        logger.info("ReportScheduler stopped")

    async def _loop(self, db_pool: asyncpg.Pool) -> None:
        while self._running:
            now = datetime.utcnow()
            tomorrow = (now + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
            wait_seconds = (tomorrow - now).total_seconds()
            await asyncio.sleep(wait_seconds)
            if not self._running:
                break
            await self._run_daily(db_pool)
            today = datetime.utcnow()
            if today.day == 1:
                yesterday = today - timedelta(days=1)
                await self._run_monthly(db_pool, yesterday.year, yesterday.month)

    async def _run_daily(self, db_pool: asyncpg.Pool) -> None:
        today = datetime.utcnow().strftime("%Y-%m-%d")
        try:
            await _report_service.generate_report(
                db_pool=db_pool,
                report_type="daily_log",
                params={"date": today},
            )
            logger.info("Auto-generated daily report for %s", today)
        except Exception:
            logger.exception("Failed auto-generating daily report for %s", today)

    async def _run_monthly(self, db_pool: asyncpg.Pool, year: int, month: int) -> None:
        try:
            await _report_service.generate_report(
                db_pool=db_pool,
                report_type="monthly",
                params={"year": str(year), "month": str(month)},
            )
            logger.info("Auto-generated monthly report for %d/%d", year, month)
        except Exception:
            logger.exception("Failed auto-generating monthly report for %d/%d", year, month)


_scheduler: ReportScheduler | None = None


def get_report_scheduler() -> ReportScheduler:
    global _scheduler
    if _scheduler is None:
        _scheduler = ReportScheduler()
    return _scheduler
