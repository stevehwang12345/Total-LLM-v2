import asyncio
import logging
import time
from typing import Any

import asyncpg

from total_llm.models.schemas import DeviceModel

logger = logging.getLogger(__name__)


class DeviceService:
    async def list_devices(
        self,
        db_pool: asyncpg.Pool,
        type_filter: str | None = None,
        status_filter: str | None = None,
    ) -> list[DeviceModel]:
        conditions: list[str] = []
        values: list[Any] = []

        if type_filter:
            values.append(type_filter)
            conditions.append(f"device_type = ${len(values)}")
        if status_filter:
            values.append(status_filter)
            conditions.append(f"status = ${len(values)}")

        query = (
            "SELECT device_id, device_type, manufacturer, ip_address, port, protocol, location, status "
            "FROM devices"
        )
        if conditions:
            query += " WHERE " + " AND ".join(conditions)
        query += " ORDER BY created_at DESC"

        try:
            async with db_pool.acquire() as conn:
                rows = await conn.fetch(query, *values)
            return [DeviceModel.model_validate(dict(row)) for row in rows]
        except Exception:
            logger.exception("Failed listing devices")
            raise

    async def get_device(self, db_pool: asyncpg.Pool, device_id: str) -> DeviceModel:
        query = (
            "SELECT device_id, device_type, manufacturer, ip_address, port, protocol, location, status "
            "FROM devices WHERE device_id = $1"
        )
        try:
            async with db_pool.acquire() as conn:
                row = await conn.fetchrow(query, device_id)
            if row is None:
                raise ValueError(f"Device not found: {device_id}")
            return DeviceModel.model_validate(dict(row))
        except Exception:
            logger.exception("Failed getting device: %s", device_id)
            raise

    async def register_device(self, db_pool: asyncpg.Pool, device: DeviceModel) -> DeviceModel:
        query = (
            "INSERT INTO devices (device_id, device_type, manufacturer, ip_address, port, protocol, location, status) "
            "VALUES ($1, $2, $3, $4, $5, $6, $7, $8) "
            "RETURNING device_id, device_type, manufacturer, ip_address, port, protocol, location, status"
        )
        try:
            async with db_pool.acquire() as conn:
                row = await conn.fetchrow(
                    query,
                    device.device_id,
                    device.device_type,
                    device.manufacturer,
                    device.ip_address,
                    device.port,
                    device.protocol,
                    device.location,
                    device.status,
                )
            if row is None:
                raise RuntimeError("Device registration failed")
            return DeviceModel.model_validate(dict(row))
        except Exception:
            logger.exception("Failed registering device: %s", device.device_id)
            raise

    async def update_device(
        self,
        db_pool: asyncpg.Pool,
        device_id: str,
        updates: dict[str, Any],
    ) -> DeviceModel:
        if not updates:
            return await self.get_device(db_pool, device_id)

        allowed_fields = {
            "device_type",
            "manufacturer",
            "ip_address",
            "port",
            "protocol",
            "location",
            "status",
        }
        invalid = [key for key in updates if key not in allowed_fields]
        if invalid:
            raise ValueError(f"Unsupported update fields: {', '.join(invalid)}")

        set_clauses: list[str] = []
        values: list[Any] = []
        for key, value in updates.items():
            values.append(value)
            set_clauses.append(f"{key} = ${len(values)}")
        values.append(device_id)

        query = (
            "UPDATE devices SET "
            + ", ".join(set_clauses)
            + f" WHERE device_id = ${len(values)} "
            "RETURNING device_id, device_type, manufacturer, ip_address, port, protocol, location, status"
        )

        try:
            async with db_pool.acquire() as conn:
                row = await conn.fetchrow(query, *values)
            if row is None:
                raise ValueError(f"Device not found: {device_id}")
            return DeviceModel.model_validate(dict(row))
        except Exception:
            logger.exception("Failed updating device: %s", device_id)
            raise

    async def delete_device(self, db_pool: asyncpg.Pool, device_id: str) -> bool:
        query = "DELETE FROM devices WHERE device_id = $1"
        try:
            async with db_pool.acquire() as conn:
                result = await conn.execute(query, device_id)
            return result.endswith("1")
        except Exception:
            logger.exception("Failed deleting device: %s", device_id)
            raise

    async def check_device_health(self, device: DeviceModel) -> dict[str, Any]:
        ping_result = await self._ping_host(device.ip_address)
        port_result = await self._check_port(device.ip_address, device.port)

        healthy = ping_result["reachable"] and port_result["port_open"]
        return {
            "device_id": device.device_id,
            "ip_address": device.ip_address,
            "port": device.port,
            "reachable": ping_result["reachable"],
            "port_open": port_result["port_open"],
            "latency_ms": ping_result["latency_ms"],
            "check_duration_ms": ping_result["duration_ms"] + port_result["duration_ms"],
            "status": "online" if healthy else "offline",
        }

    async def _ping_host(self, ip_address: str) -> dict[str, Any]:
        started = time.perf_counter()
        try:
            process = await asyncio.create_subprocess_exec(
                "ping",
                "-c",
                "1",
                "-W",
                "1",
                ip_address,
                stdout=asyncio.subprocess.DEVNULL,
                stderr=asyncio.subprocess.DEVNULL,
            )
            return_code = await process.wait()
            duration_ms = int((time.perf_counter() - started) * 1000)
            return {
                "reachable": return_code == 0,
                "latency_ms": duration_ms if return_code == 0 else None,
                "duration_ms": duration_ms,
            }
        except Exception:
            logger.exception("Ping failed for host: %s", ip_address)
            duration_ms = int((time.perf_counter() - started) * 1000)
            return {
                "reachable": False,
                "latency_ms": None,
                "duration_ms": duration_ms,
            }

    async def _check_port(self, ip_address: str, port: int) -> dict[str, Any]:
        started = time.perf_counter()
        writer = None
        try:
            reader, writer = await asyncio.wait_for(
                asyncio.open_connection(ip_address, port),
                timeout=1.5,
            )
            _ = reader
            duration_ms = int((time.perf_counter() - started) * 1000)
            return {
                "port_open": True,
                "duration_ms": duration_ms,
            }
        except Exception:
            duration_ms = int((time.perf_counter() - started) * 1000)
            return {
                "port_open": False,
                "duration_ms": duration_ms,
            }
        finally:
            if writer is not None:
                writer.close()
                await writer.wait_closed()
