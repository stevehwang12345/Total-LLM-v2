from __future__ import annotations

import base64
import json
import logging
from datetime import datetime
from pathlib import Path
from uuid import uuid4

import asyncpg
from fastapi import APIRouter, Depends, File, Form, Query, UploadFile
from fastapi.responses import FileResponse

from ..core.dependencies import get_db_pool, get_settings, get_vlm_client
from ..core.exceptions import ExternalServiceError, NotFoundError, VLMError, ValidationError
from ..services.alarm_service import AlarmService
from ..services.vlm_service import VLMService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/analysis", tags=["analysis"])

UPLOAD_DIR = Path("/app/data/uploads")
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
MAX_VIDEO_SIZE = 200 * 1024 * 1024

_alarm_service = AlarmService()
RISK_TO_PRIORITY = {3: "P3", 4: "P2", 5: "P1"}
ALARM_AUTO_THRESHOLD = 3


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
    is_image = content_type.startswith("image/")
    is_video = content_type == "video/mp4"
    if not is_image and not is_video:
        raise ValidationError("이미지(JPG/PNG/WebP/BMP) 또는 MP4 영상만 업로드 가능합니다")

    raw = await file.read()
    if not raw:
        raise ValidationError("uploaded file is empty")
    if is_video and len(raw) > MAX_VIDEO_SIZE:
        raise ValidationError(
            f"영상 파일이 너무 큽니다 (최대 200MB, 현재 {len(raw) / 1024 / 1024:.1f}MB)"
        )

    analysis_id = str(uuid4())
    suffix = Path(file.filename).suffix.lower() or (".jpg" if is_image else ".mp4")
    saved_path = UPLOAD_DIR / f"{analysis_id}{suffix}"
    saved_path.write_bytes(raw)

    analysis_service = VLMService()

    try:
        if is_image:
            image_base64 = base64.b64encode(raw).decode("utf-8")
            result = await analysis_service.analyze_image(
                client=vlm_client,
                image_base64=image_base64,
                location=location,
                timestamp=datetime.utcnow(),
            )
        else:
            result = await analysis_service.analyze_video(
                client=vlm_client,
                video_path=saved_path,
                location=location,
                timestamp=datetime.utcnow(),
            )
    except Exception as exc:
        logger.exception("Media analysis failed")
        raise VLMError("Failed to analyze media") from exc

    payload = result.model_dump(mode="json") if hasattr(result, "model_dump") else dict(result)
    media_type_value = "video" if is_video else "image"

    query = (
        "INSERT INTO analyses (analysis_id, filename, size, content_type, location, result, media_type) "
        "VALUES ($1, $2, $3, $4, $5, $6::jsonb, $7)"
    )
    risk_level = payload.get("risk_level", 1)
    try:
        async with db_pool.acquire() as conn:
            async with conn.transaction():
                await conn.execute(
                    query,
                    analysis_id,
                    file.filename,
                    len(raw),
                    content_type,
                    location,
                    json.dumps(payload, ensure_ascii=False),
                    media_type_value,
                )

                if risk_level >= ALARM_AUTO_THRESHOLD:
                    priority = RISK_TO_PRIORITY.get(risk_level, "P3")
                    incident_type = payload.get("incident_type", "Unknown")
                    severity_map = {1: "정보", 2: "낮음", 3: "중간", 4: "높음", 5: "매우높음"}
                    severity = severity_map.get(risk_level, "중간")
                    first_device = await conn.fetchval("SELECT device_id FROM devices LIMIT 1")

                    if first_device:
                        description = (
                            f"[자동감지] {incident_type} - {location or '위치 미상'} "
                            f"(분석 ID: {analysis_id}, 위험도: {risk_level}/5)"
                        )
                        try:
                            await _alarm_service.create_alarm(
                                db_pool=db_pool,
                                device_id=first_device,
                                severity=severity,
                                description=description,
                                priority=priority,
                                analysis_id=analysis_id,
                            )
                        except Exception:
                            logger.exception("Auto alarm creation failed for analysis %s", analysis_id)
    except Exception as exc:
        logger.exception("Failed storing analysis metadata")
        raise ExternalServiceError("Failed storing analysis result") from exc

    return {
        "analysis_id": analysis_id,
        "filename": file.filename,
        "location": location,
        "media_type": media_type_value,
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


@router.get("/{analysis_id}/image")
async def get_analysis_image(analysis_id: str):
    """원본 분석 이미지를 반환한다."""
    for ext in (".jpg", ".jpeg", ".png", ".bmp", ".webp"):
        candidate = UPLOAD_DIR / f"{analysis_id}{ext}"
        if candidate.exists():
            media = {
                ".jpg": "image/jpeg", ".jpeg": "image/jpeg",
                ".png": "image/png", ".bmp": "image/bmp",
                ".webp": "image/webp",
            }.get(ext, "application/octet-stream")
            return FileResponse(path=str(candidate), media_type=media)
    raise NotFoundError("Image not found")


@router.get("/{analysis_id}/media")
async def get_analysis_media(analysis_id: str):
    """원본 분석 미디어(이미지 또는 영상)를 반환한다."""
    for ext in (".jpg", ".jpeg", ".png", ".bmp", ".webp", ".mp4"):
        candidate = UPLOAD_DIR / f"{analysis_id}{ext}"
        if candidate.exists():
            media = {
                ".jpg": "image/jpeg", ".jpeg": "image/jpeg",
                ".png": "image/png", ".bmp": "image/bmp",
                ".webp": "image/webp",
                ".mp4": "video/mp4",
            }.get(ext, "application/octet-stream")
            return FileResponse(path=str(candidate), media_type=media)
    raise NotFoundError("Media not found")


@router.get("/{analysis_id}")
async def get_analysis(
    analysis_id: str,
    db_pool: asyncpg.Pool = Depends(get_db_pool),
    settings=Depends(get_settings),
):
    _ = settings
    await _ensure_analysis_table(db_pool)

    query = (
        "SELECT analysis_id, filename, size, content_type, media_type, location, created_at, result "
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
    raw_result = data.get("result") or "{}"
    if isinstance(raw_result, (bytes, bytearray, memoryview)):
        raw_result = bytes(raw_result).decode("utf-8", errors="ignore")
    if isinstance(raw_result, str):
        try:
            raw_result = json.loads(raw_result)
        except (json.JSONDecodeError, TypeError):
            raw_result = {}
    if not isinstance(raw_result, dict):
        raw_result = {}
    data["result"] = raw_result
    data["incident_type"] = raw_result.get("incident_type", "정상활동")
    data["incident_type_en"] = raw_result.get("incident_type_en", "Normal")
    data["severity"] = raw_result.get("severity", "정보")
    data["risk_level"] = raw_result.get("risk_level", 1)
    data["confidence"] = raw_result.get("confidence", 0.5)
    data["qa_results"] = raw_result.get("qa_results", {})
    data["report"] = raw_result.get("report", "")
    data["recommended_actions"] = raw_result.get("recommended_actions", [])
    data["sop_reference"] = raw_result.get("sop_reference")
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
        "COALESCE(media_type, 'image') AS media_type, "
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
        "result JSONB NOT NULL, "
        "media_type TEXT NOT NULL DEFAULT 'image'"
        ")"
    )
    
    # Migration: Add media_type column to existing tables
    add_column = (
        "ALTER TABLE analyses "
        "ADD COLUMN IF NOT EXISTS media_type TEXT NOT NULL DEFAULT 'image'"
    )

    try:
        async with db_pool.acquire() as conn:
            await conn.execute(create_table)
            await conn.execute(add_column)
    except Exception as exc:
        logger.exception("Failed ensuring analyses table")
        raise ExternalServiceError("Database initialization failed") from exc
