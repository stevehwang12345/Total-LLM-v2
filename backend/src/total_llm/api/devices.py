from __future__ import annotations

import logging

import asyncpg
from fastapi import APIRouter, Body, Depends, Query

from ..core.dependencies import get_db_pool, get_settings
from ..core.exceptions import DeviceControlError, NotFoundError, ValidationError
from ..models.schemas import DeviceModel
from ..services.device_control import DeviceService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/devices", tags=["devices"])
device_service = DeviceService()


@router.get("")
async def list_devices(
    device_type: str | None = Query(default=None),
    status: str | None = Query(default=None),
    db_pool: asyncpg.Pool = Depends(get_db_pool),
    settings=Depends(get_settings),
):
    _ = settings
    try:
        return await device_service.list_devices(
            db_pool=db_pool,
            type_filter=device_type,
            status_filter=status,
        )
    except Exception as exc:
        logger.exception("Failed listing devices")
        raise DeviceControlError("Failed listing devices") from exc


@router.get("/{device_id}")
async def get_device(
    device_id: str,
    db_pool: asyncpg.Pool = Depends(get_db_pool),
    settings=Depends(get_settings),
):
    _ = settings
    try:
        return await device_service.get_device(db_pool=db_pool, device_id=device_id)
    except ValueError as exc:
        raise NotFoundError(str(exc)) from exc
    except Exception as exc:
        logger.exception("Failed getting device: %s", device_id)
        raise DeviceControlError("Failed getting device") from exc


@router.post("")
async def register_device(
    device: DeviceModel,
    db_pool: asyncpg.Pool = Depends(get_db_pool),
    settings=Depends(get_settings),
):
    _ = settings
    try:
        return await device_service.register_device(db_pool=db_pool, device=device)
    except Exception as exc:
        logger.exception("Failed registering device: %s", device.device_id)
        raise DeviceControlError("Failed registering device") from exc


@router.put("/{device_id}")
async def update_device(
    device_id: str,
    updates: dict | None = Body(default=None),
    db_pool: asyncpg.Pool = Depends(get_db_pool),
    settings=Depends(get_settings),
):
    _ = settings
    if updates is None:
        updates = {}

    if not isinstance(updates, dict):
        raise ValidationError("updates must be an object")

    try:
        return await device_service.update_device(
            db_pool=db_pool,
            device_id=device_id,
            updates=updates,
        )
    except ValueError as exc:
        error_text = str(exc)
        if "not found" in error_text.lower():
            raise NotFoundError(error_text) from exc
        raise ValidationError(error_text) from exc
    except Exception as exc:
        logger.exception("Failed updating device: %s", device_id)
        raise DeviceControlError("Failed updating device") from exc


@router.delete("/{device_id}")
async def delete_device(
    device_id: str,
    db_pool: asyncpg.Pool = Depends(get_db_pool),
    settings=Depends(get_settings),
):
    _ = settings
    try:
        deleted = await device_service.delete_device(db_pool=db_pool, device_id=device_id)
    except Exception as exc:
        logger.exception("Failed deleting device: %s", device_id)
        raise DeviceControlError("Failed deleting device") from exc

    if not deleted:
        raise NotFoundError("Device not found")
    return {"deleted": True, "device_id": device_id}
