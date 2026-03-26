from __future__ import annotations

from typing import Any

import asyncpg

from .device_control import DeviceService


class DeviceTools:
    def __init__(self, db_pool: asyncpg.Pool):
        self.db_pool = db_pool
        self.device_service = DeviceService()

    @staticmethod
    def tool_specs() -> list[dict[str, Any]]:
        return [
            {
                "type": "function",
                "function": {
                    "name": "list_devices",
                    "description": "List registered devices with optional filters",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "status": {"type": "string"},
                            "device_type": {"type": "string"},
                            "limit": {"type": "integer", "minimum": 1, "maximum": 200},
                        },
                        "additionalProperties": False,
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "get_device_health",
                    "description": "Check current health status of a specific device",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "device_id": {"type": "string"},
                        },
                        "required": ["device_id"],
                        "additionalProperties": False,
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "get_device_health_history",
                    "description": "Get recent health check history for a specific device",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "device_id": {"type": "string"},
                            "limit": {"type": "integer", "minimum": 1, "maximum": 200},
                        },
                        "required": ["device_id"],
                        "additionalProperties": False,
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "list_scan_sessions",
                    "description": "List discovery scan sessions and statuses",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "limit": {"type": "integer", "minimum": 1, "maximum": 100},
                            "status": {"type": "string"},
                        },
                        "additionalProperties": False,
                    },
                },
            },
        ]

    async def execute(self, name: str, arguments: dict[str, Any]) -> Any:
        if name == "list_devices":
            return await self._list_devices(arguments)
        if name == "get_device_health":
            return await self._get_device_health(arguments)
        if name == "get_device_health_history":
            return await self._get_device_health_history(arguments)
        if name == "list_scan_sessions":
            return await self._list_scan_sessions(arguments)
        raise ValueError(f"Unsupported tool: {name}")

    async def _list_devices(self, arguments: dict[str, Any]) -> dict[str, Any]:
        status = arguments.get("status")
        device_type = arguments.get("device_type")
        limit = int(arguments.get("limit") or 50)
        devices = await self.device_service.list_devices(
            db_pool=self.db_pool,
            type_filter=device_type,
            status_filter=status,
        )
        return {
            "items": [device.model_dump() for device in devices[:limit]],
            "count": min(len(devices), limit),
        }

    async def _get_device_health(self, arguments: dict[str, Any]) -> dict[str, Any]:
        device_id = str(arguments.get("device_id") or "").strip()
        if not device_id:
            raise ValueError("device_id is required")
        device = await self.device_service.get_device(self.db_pool, device_id)
        health = await self.device_service.check_device_health(device)
        return health

    async def _get_device_health_history(self, arguments: dict[str, Any]) -> dict[str, Any]:
        device_id = str(arguments.get("device_id") or "").strip()
        if not device_id:
            raise ValueError("device_id is required")
        limit = int(arguments.get("limit") or 20)
        history = await self.device_service.get_health_history(self.db_pool, device_id, limit)
        return {
            "device_id": device_id,
            "items": history,
            "count": len(history),
        }

    async def _list_scan_sessions(self, arguments: dict[str, Any]) -> dict[str, Any]:
        limit = int(arguments.get("limit") or 20)
        status = str(arguments.get("status") or "").strip()

        conditions: list[str] = []
        values: list[Any] = []
        if status:
            values.append(status)
            conditions.append(f"status = ${len(values)}")
        values.append(limit)

        query = (
            "SELECT scan_id, cidr, status, started_at, completed_at, total_found, error_message "
            "FROM scan_sessions"
        )
        if conditions:
            query += " WHERE " + " AND ".join(conditions)
        query += f" ORDER BY started_at DESC LIMIT ${len(values)}"

        async with self.db_pool.acquire() as conn:
            rows = await conn.fetch(query, *values)

        items = [dict(row) for row in rows]
        return {
            "items": items,
            "count": len(items),
        }
