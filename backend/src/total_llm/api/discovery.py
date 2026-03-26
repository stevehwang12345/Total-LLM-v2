from __future__ import annotations

import logging
from typing import Any

import asyncpg
from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field

from ..core.dependencies import get_db_pool, get_llm_client, get_settings
from ..core.exceptions import ExternalServiceError, NotFoundError, ValidationError
from ..services.discovery_service import DiscoveryService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/discovery", tags=["discovery"])


class StartScanRequest(BaseModel):
    cidr: str = Field(..., min_length=9)
    timeout_sec: int = Field(default=90, ge=5, le=600)


class RegisterDiscoveredRequest(BaseModel):
    device_id: str | None = None
    device_type: str | None = None
    manufacturer: str | None = None
    protocol: str | None = None
    port: int | None = Field(default=None, ge=1, le=65535)
    location: str | None = None
    status: str = "online"
    manual_override: bool = False


@router.post("/scans")
async def start_discovery_scan(
    payload: StartScanRequest,
    db_pool: asyncpg.Pool = Depends(get_db_pool),
    settings=Depends(get_settings),
):
    discovery_service = DiscoveryService(settings.scanner_base_url)
    try:
        return await discovery_service.start_scan(db_pool, payload.cidr, payload.timeout_sec)
    except ValueError as exc:
        raise ValidationError(str(exc)) from exc
    except RuntimeError as exc:
        raise ExternalServiceError(str(exc)) from exc
    except Exception as exc:
        logger.exception("Failed to start discovery scan")
        raise ExternalServiceError("Failed to start discovery scan") from exc


@router.get("/scans")
async def list_discovery_scans(
    limit: int = Query(default=20, ge=1, le=100),
    db_pool: asyncpg.Pool = Depends(get_db_pool),
    settings=Depends(get_settings),
):
    discovery_service = DiscoveryService(settings.scanner_base_url)
    try:
        return {"items": await discovery_service.list_scans(db_pool, limit)}
    except Exception as exc:
        logger.exception("Failed to list discovery scans")
        raise ExternalServiceError("Failed to list discovery scans") from exc


@router.get("/scans/{scan_id}")
async def get_discovery_scan_status(
    scan_id: str,
    db_pool: asyncpg.Pool = Depends(get_db_pool),
    settings=Depends(get_settings),
):
    discovery_service = DiscoveryService(settings.scanner_base_url)
    try:
        return await discovery_service.get_scan_status(db_pool, scan_id)
    except LookupError as exc:
        raise NotFoundError(str(exc)) from exc
    except RuntimeError as exc:
        raise ExternalServiceError(str(exc)) from exc
    except Exception as exc:
        logger.exception("Failed to get discovery scan status: %s", scan_id)
        raise ExternalServiceError("Failed to get discovery scan status") from exc


@router.get("/scans/{scan_id}/results")
async def get_discovery_scan_results(
    scan_id: str,
    db_pool: asyncpg.Pool = Depends(get_db_pool),
    settings=Depends(get_settings),
):
    discovery_service = DiscoveryService(settings.scanner_base_url)
    try:
        return await discovery_service.get_scan_results(db_pool, scan_id)
    except LookupError as exc:
        raise NotFoundError(str(exc)) from exc
    except RuntimeError as exc:
        raise ExternalServiceError(str(exc)) from exc
    except Exception as exc:
        logger.exception("Failed to get discovery scan results: %s", scan_id)
        raise ExternalServiceError("Failed to get discovery scan results") from exc


@router.post("/scans/{scan_id}/devices/{discovered_id}/profile")
async def profile_discovered_device(
    scan_id: str,
    discovered_id: int,
    db_pool: asyncpg.Pool = Depends(get_db_pool),
    llm_client: Any = Depends(get_llm_client),
    settings=Depends(get_settings),
):
    discovery_service = DiscoveryService(settings.scanner_base_url)
    try:
        return await discovery_service.profile_discovered_device(
            db_pool=db_pool,
            llm_client=llm_client,
            scan_id=scan_id,
            discovered_id=discovered_id,
        )
    except LookupError as exc:
        raise NotFoundError(str(exc)) from exc
    except RuntimeError as exc:
        raise ExternalServiceError(str(exc)) from exc
    except Exception as exc:
        logger.exception("Failed to profile discovered device: %s/%s", scan_id, discovered_id)
        raise ExternalServiceError("Failed to profile discovered device") from exc


@router.post("/scans/{scan_id}/devices/{discovered_id}/register")
async def register_discovered_device(
    scan_id: str,
    discovered_id: int,
    payload: RegisterDiscoveredRequest,
    db_pool: asyncpg.Pool = Depends(get_db_pool),
    settings=Depends(get_settings),
):
    discovery_service = DiscoveryService(settings.scanner_base_url)
    try:
        return await discovery_service.register_discovered_device(
            db_pool=db_pool,
            scan_id=scan_id,
            discovered_id=discovered_id,
            register_payload=payload.model_dump(exclude_none=True),
        )
    except LookupError as exc:
        raise NotFoundError(str(exc)) from exc
    except ValueError as exc:
        raise ValidationError(str(exc)) from exc
    except RuntimeError as exc:
        raise ExternalServiceError(str(exc)) from exc
    except Exception as exc:
        logger.exception("Failed to register discovered device: %s/%s", scan_id, discovered_id)
        raise ExternalServiceError("Failed to register discovered device") from exc
