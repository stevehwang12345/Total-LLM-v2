from __future__ import annotations

import base64
import json
import logging
from datetime import datetime
from uuid import uuid4

import asyncpg
from fastapi import APIRouter, Depends, File, Form, Query, UploadFile

from ..core.dependencies import get_db_pool, get_settings, get_vlm_client
from ..core.exceptions import ExternalServiceError, NotFoundError, VLMError, ValidationError
from ..services.vlm_service import VLMService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/analysis", tags=["analysis"])


@router.post("/upload")
async def upload_analysis(
    file: UploadFile = File(...),
    location: str | None = Form(None),
    db_pool: asyncpg.Pool = Depends(get_db_pool),
    vlm_client=Depends(get_vlm_client),
    settings=Depends(get_settings),
):
    _ = settings
    await _ensure_analysis_table(db_pool)

    if not file.filename:
        raise ValidationError("filename is required")

    content_type = file.content_type or "application/octet-stream"
    if not content_type.startswith("image/"):
        raise ValidationError("only image uploads are supported")

    raw = await file.read()
    if not raw:
        raise ValidationError("uploaded file is empty")

    image_base64 = base64.b64encode(raw).decode("utf-8")
    analysis_service = VLMService()

    try:
        result = await analysis_service.analyze_image(
            client=vlm_client,
            image_base64=image_base64,
            location=location,
            timestamp=datetime.utcnow(),
        )
    except Exception as exc:
        logger.exception("Image analysis failed")
        raise VLMError("Failed to analyze image") from exc

    analysis_id = str(uuid4())
    payload = result.model_dump(mode="json") if hasattr(result, "model_dump") else dict(result)

    query = (
        "INSERT INTO analyses (analysis_id, filename, size, content_type, location, result) "
        "VALUES ($1, $2, $3, $4, $5, $6::jsonb)"
    )
    try:
        async with db_pool.acquire() as conn:
            await conn.execute(
                query,
                analysis_id,
                file.filename,
                len(raw),
                content_type,
                location,
                json.dumps(payload, ensure_ascii=False),
            )
    except Exception as exc:
        logger.exception("Failed storing analysis metadata")
        raise ExternalServiceError("Failed storing analysis result") from exc

    return {
        "analysis_id": analysis_id,
        "filename": file.filename,
        "location": location,
        "incident_type": payload.get("incident_type", "정상활동"),
        "incident_type_en": payload.get("incident_type_en", "Normal"),
        "severity": payload.get("severity", "정보"),
        "risk_level": payload.get("risk_level", 1),
        "confidence": payload.get("confidence", 0.5),
        "qa_results": payload.get("qa_results", {}),
        "report": payload.get("report", ""),
        "recommended_actions": payload.get("recommended_actions", []),
        "sop_reference": payload.get("sop_reference"),
        "result": payload,
    }


@router.get("/{analysis_id}")
async def get_analysis(
    analysis_id: str,
    db_pool: asyncpg.Pool = Depends(get_db_pool),
    settings=Depends(get_settings),
):
    _ = settings
    await _ensure_analysis_table(db_pool)

    query = (
        "SELECT analysis_id, filename, size, content_type, location, created_at, result "
        "FROM analyses WHERE analysis_id = $1"
    )
    try:
        async with db_pool.acquire() as conn:
            row = await conn.fetchrow(query, analysis_id)
    except Exception as exc:
        logger.exception("Failed fetching analysis: %s", analysis_id)
        raise ExternalServiceError("Failed loading analysis") from exc

    if row is None:
        raise NotFoundError("Analysis not found")

    data = dict(row)
    data["result"] = data.get("result") or {}
    return data


@router.get("")
async def list_analyses(
    limit: int = Query(default=20, ge=1, le=100),
    db_pool: asyncpg.Pool = Depends(get_db_pool),
    settings=Depends(get_settings),
):
    _ = settings
    await _ensure_analysis_table(db_pool)

    query = (
        "SELECT analysis_id, filename, size, content_type, location, created_at, "
        "COALESCE(result->>'incident_type', '정상활동') AS incident_type, "
        "COALESCE(result->>'severity', '정보') AS severity, "
        "COALESCE((result->>'risk_level')::int, 1) AS risk_level, "
        "COALESCE((result->>'confidence')::float, 0.5) AS confidence "
        "FROM analyses ORDER BY created_at DESC LIMIT $1"
    )
    try:
        async with db_pool.acquire() as conn:
            rows = await conn.fetch(query, limit)
    except Exception as exc:
        logger.exception("Failed listing analyses")
        raise ExternalServiceError("Failed listing analyses") from exc

    return [dict(row) for row in rows]


async def _ensure_analysis_table(db_pool: asyncpg.Pool) -> None:
    create_table = (
        "CREATE TABLE IF NOT EXISTS analyses ("
        "analysis_id TEXT PRIMARY KEY, "
        "filename TEXT NOT NULL, "
        "size BIGINT NOT NULL, "
        "content_type TEXT, "
        "location TEXT, "
        "created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(), "
        "result JSONB NOT NULL"
        ")"
    )

    try:
        async with db_pool.acquire() as conn:
            await conn.execute(create_table)
    except Exception as exc:
        logger.exception("Failed ensuring analyses table")
        raise ExternalServiceError("Database initialization failed") from exc
