from __future__ import annotations

import logging
from pathlib import Path

import asyncpg
from fastapi import APIRouter, Body, Depends
from fastapi.responses import FileResponse

from total_llm.core.dependencies import get_db_pool, get_settings
from total_llm.core.exceptions import ExternalServiceError, NotFoundError, ValidationError
from total_llm.services.report_service import ReportService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/reports", tags=["reports"])
report_service = ReportService()


@router.post("/generate")
async def generate_report(
    payload: dict | None = Body(default=None),
    db_pool: asyncpg.Pool = Depends(get_db_pool),
    settings=Depends(get_settings),
):
    _ = settings
    body = payload or {}
    report_type = str(body.get("report_type") or "security").strip() or "security"
    params = body.get("params") or {}
    if not isinstance(params, dict):
        raise ValidationError("params must be an object")

    try:
        return await report_service.generate_report(
            db_pool=db_pool,
            report_type=report_type,
            params=params,
        )
    except Exception as exc:
        logger.exception("Failed generating report")
        raise ExternalServiceError("Failed generating report") from exc


@router.get("")
async def list_reports(
    db_pool: asyncpg.Pool = Depends(get_db_pool),
    settings=Depends(get_settings),
):
    _ = settings
    try:
        return await report_service.list_reports(db_pool=db_pool)
    except Exception as exc:
        logger.exception("Failed listing reports")
        raise ExternalServiceError("Failed listing reports") from exc


@router.get("/{report_id}/download")
async def download_report(
    report_id: str,
    db_pool: asyncpg.Pool = Depends(get_db_pool),
    settings=Depends(get_settings),
):
    _ = settings
    query = "SELECT file_path, title FROM reports WHERE report_id = $1"
    try:
        async with db_pool.acquire() as conn:
            row = await conn.fetchrow(query, report_id)
    except Exception as exc:
        logger.exception("Failed loading report metadata: %s", report_id)
        raise ExternalServiceError("Failed loading report metadata") from exc

    if row is None:
        raise NotFoundError("Report not found")

    file_path = Path(row["file_path"]) if row["file_path"] else None
    if file_path is None or not file_path.exists():
        raise NotFoundError("Report file not found")

    return FileResponse(
        path=str(file_path),
        media_type="application/pdf",
        filename=f"{report_id}.pdf",
    )


@router.delete("/{report_id}")
async def delete_report(
    report_id: str,
    db_pool: asyncpg.Pool = Depends(get_db_pool),
    settings=Depends(get_settings),
):
    _ = settings
    try:
        deleted = await report_service.delete_report(db_pool=db_pool, report_id=report_id)
    except Exception as exc:
        logger.exception("Failed deleting report: %s", report_id)
        raise ExternalServiceError("Failed deleting report") from exc

    if not deleted:
        raise NotFoundError("Report not found")
    return {"deleted": True, "report_id": report_id}
