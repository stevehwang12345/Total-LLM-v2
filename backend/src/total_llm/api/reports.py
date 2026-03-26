from __future__ import annotations

import logging
from pathlib import Path

import asyncpg
from fastapi.openapi.models import Example
from fastapi import APIRouter, Body, Depends
from fastapi.responses import FileResponse, Response

from total_llm.core.dependencies import get_db_pool, get_settings
from total_llm.core.exceptions import ExternalServiceError, NotFoundError, ValidationError
from total_llm.services.report_service import ReportService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/reports", tags=["reports"])
report_service = ReportService()

REPORT_GENERATE_EXAMPLES: dict[str, Example] = {
    "daily_log": Example(
        summary="Generate daily log report",
        value={"type": "daily_log", "params": {"date": "2026-03-26"}},
    ),
    "incident": Example(
        summary="Generate incident report",
        value={"type": "incident", "params": {"alarm_id": "alarm-uuid"}},
    ),
    "equipment": Example(
        summary="Generate equipment report",
        value={"type": "equipment", "params": {"date": "2026-03-26"}},
    ),
    "monthly": Example(
        summary="Generate monthly report",
        value={"type": "monthly", "params": {"year": "2026", "month": "3"}},
    ),
}


@router.post("/generate")
async def generate_report(
    payload: dict | None = Body(default=None, openapi_examples=REPORT_GENERATE_EXAMPLES),
    db_pool: asyncpg.Pool = Depends(get_db_pool),
    settings=Depends(get_settings),
):
    _ = settings
    body = payload or {}
    report_type = str(body.get("type") or body.get("report_type") or "security").strip() or "security"
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


@router.get("/{report_id}")
async def get_report_detail(
    report_id: str,
    db_pool: asyncpg.Pool = Depends(get_db_pool),
    settings=Depends(get_settings),
):
    _ = settings
    query = (
        "SELECT report_id, title, report_type, file_path, created_at, "
        "date_range_start, date_range_end, generated_by, data_snapshot "
        "FROM reports WHERE report_id = $1"
    )
    try:
        async with db_pool.acquire() as conn:
            row = await conn.fetchrow(query, report_id)
    except Exception as exc:
        logger.exception("Failed loading report detail: %s", report_id)
        raise ExternalServiceError("Failed loading report detail") from exc

    if row is None:
        raise NotFoundError("Report not found")

    result = dict(row)
    for key in ("created_at", "date_range_start", "date_range_end"):
        if result.get(key) is not None:
            result[key] = str(result[key])
    return result


@router.get("/{report_id}/preview")
async def preview_report(
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
        logger.exception("Failed loading report for preview: %s", report_id)
        raise ExternalServiceError("Failed loading report") from exc

    if row is None:
        raise NotFoundError("Report not found")

    file_path = Path(row["file_path"]) if row["file_path"] else None
    if file_path is None or not file_path.exists():
        raise NotFoundError("Report file not found")

    content = file_path.read_bytes()
    return Response(
        content=content,
        media_type="application/pdf",
        headers={"Content-Disposition": "inline"},
    )


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
