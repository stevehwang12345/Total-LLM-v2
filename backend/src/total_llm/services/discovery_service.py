from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Any

import aiohttp
import asyncpg
from pydantic import BaseModel, Field

from .profiling_service import ProfilingService

logger = logging.getLogger(__name__)


class ConsistencyMismatch(BaseModel):
    field: str
    expected: str
    actual: str
    evidence: str
    severity: str  # "high" | "medium" | "low"


class ConsistencyResult(BaseModel):
    consistent: bool
    score: float = Field(ge=0.0, le=1.0)
    mismatches: list[ConsistencyMismatch] = []
    checked_at: str = ""


class DiscoveryService:
    # Rule constants for profile consistency checking
    RULE_ONVIF_PRESENT = "onvif_present"
    RULE_MDNS_RTSP = "mdns_rtsp"
    RULE_PORT_554_8554 = "port_554_8554"
    RULE_PORT_502 = "port_502"
    RULE_DIGEST_AUTH = "digest_auth"
    RULE_VENDOR_CAMERA = "vendor_camera"
    RULE_LOW_CONFIDENCE = "low_confidence"

    CAMERA_VENDORS = {"hikvision", "dahua", "axis", "hanwha", "bosch", "pelco", "vivotek"}

    def __init__(self, scanner_base_url: str):
        self.scanner_base_url = scanner_base_url.rstrip("/")

    async def start_scan(self, db_pool: asyncpg.Pool, cidr: str, timeout_sec: int) -> dict[str, Any]:
        payload = {"cidr": cidr, "timeout_sec": timeout_sec}
        scanner_result = await self._request("POST", "/scan", json=payload)
        scan_id = scanner_result.get("scan_id")
        if not scan_id:
            raise RuntimeError("Scanner returned invalid response: missing scan_id")

        async with db_pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO scan_sessions (scan_id, cidr, status)
                VALUES ($1, $2, $3)
                ON CONFLICT (scan_id) DO UPDATE
                SET cidr = EXCLUDED.cidr,
                    status = EXCLUDED.status,
                    started_at = NOW(),
                    completed_at = NULL,
                    total_found = 0,
                    error_message = NULL
                """,
                scan_id,
                cidr,
                "running",
            )

        return {
            "scan_id": scan_id,
            "cidr": cidr,
            "status": "running",
        }

    async def list_scans(self, db_pool: asyncpg.Pool, limit: int) -> list[dict[str, Any]]:
        async with db_pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT scan_id, cidr, status, started_at, completed_at, total_found, error_message
                FROM scan_sessions
                ORDER BY started_at DESC
                LIMIT $1
                """,
                limit,
            )
        return [dict(row) for row in rows]

    async def get_scan_status(self, db_pool: asyncpg.Pool, scan_id: str) -> dict[str, Any]:
        scan_row = await self._fetch_scan_row(db_pool, scan_id)
        if scan_row is None:
            raise LookupError(f"Scan not found: {scan_id}")

        scanner_payload: dict[str, Any] | None = None
        if scan_row["status"] in {"running", "queued"}:
            try:
                scanner_payload = await self._request("GET", f"/status/{scan_id}")
            except LookupError:
                scanner_payload = None

        if scanner_payload is not None:
            status = scanner_payload.get("status", scan_row["status"])
            total_found = int(scanner_payload.get("total_found", scan_row["total_found"] or 0))
            error_message = scanner_payload.get("error")
            completed_at_raw = scanner_payload.get("completed_at")
            completed_at = self._parse_datetime(completed_at_raw)

            async with db_pool.acquire() as conn:
                await conn.execute(
                    """
                    UPDATE scan_sessions
                    SET status = $2,
                        completed_at = $3,
                        total_found = $4,
                        error_message = $5
                    WHERE scan_id = $1
                    """,
                    scan_id,
                    status,
                    completed_at,
                    total_found,
                    error_message,
                )

            if status == "completed":
                await self._sync_results(db_pool, scan_id)

        updated_row = await self._fetch_scan_row(db_pool, scan_id)
        if updated_row is None:
            raise LookupError(f"Scan not found after update: {scan_id}")
        return dict(updated_row)

    async def get_scan_results(self, db_pool: asyncpg.Pool, scan_id: str) -> dict[str, Any]:
        await self.get_scan_status(db_pool, scan_id)

        async with db_pool.acquire() as conn:
            scan_row = await conn.fetchrow(
                """
                SELECT scan_id, cidr, status, started_at, completed_at, total_found, error_message
                FROM scan_sessions
                WHERE scan_id = $1
                """,
                scan_id,
            )
            if scan_row is None:
                raise LookupError(f"Scan not found: {scan_id}")

            device_rows = await conn.fetch(
                """
                SELECT
                    id,
                    scan_id,
                    ip_address,
                    mac_address,
                    hostname,
                    vendor,
                    open_ports,
                    http_banner,
                    onvif_info,
                    mdns_info,
                    llm_profile,
                    discovered_at,
                    status,
                    device_id
                FROM discovered_devices
                WHERE scan_id = $1
                ORDER BY id ASC
                """,
                scan_id,
            )

        return {
            "scan": dict(scan_row),
            "devices": [self._normalize_discovered_row(row) for row in device_rows],
            "total_found": len(device_rows),
        }

    async def profile_discovered_device(
        self,
        db_pool: asyncpg.Pool,
        llm_client: Any,
        scan_id: str,
        discovered_id: int,
    ) -> dict[str, Any]:
        async with db_pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                SELECT id, scan_id, ip_address, mac_address, hostname, vendor,
                       open_ports, http_banner, onvif_info, mdns_info, llm_profile,
                       status, device_id
                FROM discovered_devices
                WHERE scan_id = $1 AND id = $2
                """,
                scan_id,
                discovered_id,
            )
        if row is None:
            raise LookupError(f"Discovered device not found: scan={scan_id}, id={discovered_id}")

        payload = {
            "ip_address": row["ip_address"],
            "mac_address": row["mac_address"],
            "hostname": row["hostname"],
            "vendor": row["vendor"],
            "open_ports": self._coerce_json_list(row["open_ports"]),
            "http_banner": row["http_banner"],
            "onvif_info": self._coerce_json_dict(row["onvif_info"]),
            "mdns_info": self._coerce_json_dict(row["mdns_info"]),
        }

        profiling_service = ProfilingService()
        profile = await profiling_service.profile_device(llm_client, payload)

        consistency_result = DiscoveryService.check_profile_consistency(payload, profile)
        if not consistency_result.consistent:
            re_verified = await profiling_service.re_verify_profile(
                llm_client,
                payload,
                profile,
                [mismatch.model_dump() for mismatch in consistency_result.mismatches],
            )
            consistency_result_2 = DiscoveryService.check_profile_consistency(payload, re_verified)
            profile = re_verified
            consistency_result = consistency_result_2

        profile["consistency_result"] = consistency_result.model_dump()

        async with db_pool.acquire() as conn:
            await conn.execute(
                """
                UPDATE discovered_devices
                SET llm_profile = $3::jsonb,
                    status = CASE WHEN status = 'registered' THEN status ELSE 'profiled' END
                WHERE scan_id = $1 AND id = $2
                """,
                scan_id,
                discovered_id,
                self._jsonb_dumps(profile),
            )

        return {
            "scan_id": scan_id,
            "discovered_id": discovered_id,
            "llm_profile": profile,
        }

    @staticmethod
    def check_profile_consistency(
        device_data: dict[str, Any],
        profile: dict[str, Any],
    ) -> ConsistencyResult:
        """
        7 rules to validate consistency between scan evidence and LLM profile.

        Rules:
        1. onvif_info present → device_type == CCTV (severity: high)
        2. mdns_info.service_type == "_rtsp._tcp" → device_type == CCTV (severity: medium)
        3. port 554/8554 open → device_type == CCTV AND protocol == RTSP (severity: high)
        4. port 502 open → device_type == ACU AND protocol == Modbus (severity: high)
        5. http_banner.www_auth contains "Digest" → device_type likely CCTV (severity: low)
        6. vendor in CAMERA_VENDORS → device_type == CCTV (severity: medium)
        7. confidence < 0.5 → inconsistent (severity: high)
        """
        mismatches: list[ConsistencyMismatch] = []

        device_type = str(profile.get("device_type") or "").upper()
        protocol = str(profile.get("protocol") or "").upper()
        try:
            confidence = float(profile.get("confidence") or 0.0)
        except (TypeError, ValueError):
            confidence = 0.0

        open_ports = [int(port) for port in (device_data.get("open_ports") or []) if str(port).isdigit()]
        onvif_info = device_data.get("onvif_info") or {}
        mdns_info = device_data.get("mdns_info") or {}
        http_banner = device_data.get("http_banner") or {}
        vendor = str(device_data.get("vendor") or "").lower()

        if onvif_info and device_type not in {"CCTV", "UNKNOWN", ""}:
            mismatches.append(
                ConsistencyMismatch(
                    field="device_type",
                    expected="CCTV",
                    actual=device_type,
                    evidence="onvif_info present",
                    severity="high",
                )
            )

        if mdns_info.get("service_type") == "_rtsp._tcp" and device_type not in {"CCTV", "UNKNOWN", ""}:
            mismatches.append(
                ConsistencyMismatch(
                    field="device_type",
                    expected="CCTV",
                    actual=device_type,
                    evidence="mDNS service_type=_rtsp._tcp",
                    severity="medium",
                )
            )

        if 554 in open_ports or 8554 in open_ports:
            if device_type not in {"CCTV", "UNKNOWN", ""}:
                mismatches.append(
                    ConsistencyMismatch(
                        field="device_type",
                        expected="CCTV",
                        actual=device_type,
                        evidence="RTSP port (554/8554) open",
                        severity="high",
                    )
                )
            if protocol not in {"RTSP", "UNKNOWN", ""}:
                mismatches.append(
                    ConsistencyMismatch(
                        field="protocol",
                        expected="RTSP",
                        actual=protocol,
                        evidence="RTSP port (554/8554) open",
                        severity="high",
                    )
                )

        if 502 in open_ports:
            if device_type not in {"ACU", "UNKNOWN", ""}:
                mismatches.append(
                    ConsistencyMismatch(
                        field="device_type",
                        expected="ACU",
                        actual=device_type,
                        evidence="Modbus port 502 open",
                        severity="high",
                    )
                )
            if protocol not in {"MODBUS", "UNKNOWN", ""}:
                mismatches.append(
                    ConsistencyMismatch(
                        field="protocol",
                        expected="MODBUS",
                        actual=protocol,
                        evidence="Modbus port 502 open",
                        severity="high",
                    )
                )

        www_auth = str(http_banner.get("www_auth") or "")
        if "digest" in www_auth.lower() and device_type not in {"CCTV", "UNKNOWN", ""}:
            mismatches.append(
                ConsistencyMismatch(
                    field="device_type",
                    expected="CCTV",
                    actual=device_type,
                    evidence="HTTP WWW-Authenticate contains Digest",
                    severity="low",
                )
            )

        if any(camera_vendor in vendor for camera_vendor in DiscoveryService.CAMERA_VENDORS) and device_type not in {
            "CCTV",
            "UNKNOWN",
            "",
        }:
            mismatches.append(
                ConsistencyMismatch(
                    field="device_type",
                    expected="CCTV",
                    actual=device_type,
                    evidence="vendor matches known camera manufacturers",
                    severity="medium",
                )
            )

        if confidence < 0.5:
            mismatches.append(
                ConsistencyMismatch(
                    field="confidence",
                    expected=">= 0.5",
                    actual=str(confidence),
                    evidence="LLM confidence below threshold",
                    severity="high",
                )
            )

        high_count = sum(1 for mismatch in mismatches if mismatch.severity == "high")
        medium_count = sum(1 for mismatch in mismatches if mismatch.severity == "medium")
        low_count = sum(1 for mismatch in mismatches if mismatch.severity == "low")

        weighted = (high_count * 1.0) + (medium_count * 0.5) + (low_count * 0.2)
        max_weight = 5.0
        score = max(0.0, 1.0 - (weighted / max_weight))

        consistent = score >= 0.6 and high_count == 0

        return ConsistencyResult(
            consistent=consistent,
            score=round(score, 3),
            mismatches=mismatches,
            checked_at=datetime.now(timezone.utc).isoformat(),
        )

    async def register_discovered_device(
        self,
        db_pool: asyncpg.Pool,
        scan_id: str,
        discovered_id: int,
        register_payload: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        register_payload = register_payload or {}

        async with db_pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                SELECT id, scan_id, ip_address, vendor, open_ports, llm_profile, status, device_id
                FROM discovered_devices
                WHERE scan_id = $1 AND id = $2
                """,
                scan_id,
                discovered_id,
            )
        if row is None:
            raise LookupError(f"Discovered device not found: scan={scan_id}, id={discovered_id}")

        llm_profile = self._coerce_json_dict(row["llm_profile"])
        consistency_result = llm_profile.get("consistency_result") or {}
        manual_override = register_payload.get("manual_override", False)

        if consistency_result and not consistency_result.get("consistent", True):
            if not manual_override:
                raise ValueError(
                    "정합성 검증 실패. 수동 입력이 필요합니다. "
                    f"불일치 항목: {[m.get('field') for m in consistency_result.get('mismatches', [])]}"
                )

        open_ports = self._coerce_json_list(row["open_ports"])

        device_type = self._normalize_device_type(
            register_payload.get("device_type") or llm_profile.get("device_type") or self._infer_device_type(open_ports)
        )
        manufacturer = register_payload.get("manufacturer") or llm_profile.get("manufacturer") or row["vendor"] or "Unknown"
        protocol = self._normalize_protocol(
            register_payload.get("protocol") or llm_profile.get("protocol") or self._infer_protocol(open_ports),
            device_type,
        )
        port = int(register_payload.get("port") or self._select_port(open_ports, device_type=device_type, protocol=protocol))
        location = register_payload.get("location") or "Auto-Discovered"
        status = register_payload.get("status") or "online"

        existing_device = await self._find_existing_device_by_ip(db_pool=db_pool, ip_address=row["ip_address"])
        if existing_device is not None:
            async with db_pool.acquire() as conn:
                await conn.execute(
                    """
                    UPDATE discovered_devices
                    SET status = 'registered',
                        device_id = $3
                    WHERE scan_id = $1 AND id = $2
                    """,
                    scan_id,
                    discovered_id,
                    existing_device["device_id"],
                )
            return {
                "scan_id": scan_id,
                "discovered_id": discovered_id,
                "registered_device": dict(existing_device),
            }

        requested_device_id = register_payload.get("device_id") or llm_profile.get("suggested_device_id")
        device_id = await self._resolve_device_id(
            db_pool=db_pool,
            requested_device_id=requested_device_id,
            device_type=device_type,
            discovered_id=discovered_id,
        )

        async with db_pool.acquire() as conn:
            async with conn.transaction():
                await conn.execute(
                    """
                    INSERT INTO devices (
                        device_id,
                        device_type,
                        manufacturer,
                        ip_address,
                        port,
                        protocol,
                        location,
                        status
                    ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
                    """,
                    device_id,
                    device_type,
                    manufacturer,
                    row["ip_address"],
                    port,
                    protocol,
                    location,
                    status,
                )

                await conn.execute(
                    """
                    UPDATE discovered_devices
                    SET status = 'registered',
                        device_id = $3
                    WHERE scan_id = $1 AND id = $2
                    """,
                    scan_id,
                    discovered_id,
                    device_id,
                )

                registered = await conn.fetchrow(
                    """
                    SELECT device_id, device_type, manufacturer, ip_address, port, protocol, location, status
                    FROM devices
                    WHERE device_id = $1
                    """,
                    device_id,
                )

        if registered is None:
            raise RuntimeError("Device registration failed")

        return {
            "scan_id": scan_id,
            "discovered_id": discovered_id,
            "registered_device": dict(registered),
        }

    async def _sync_results(self, db_pool: asyncpg.Pool, scan_id: str) -> None:
        payload = await self._request("GET", f"/results/{scan_id}")
        devices = payload.get("devices") or []

        async with db_pool.acquire() as conn:
            async with conn.transaction():
                await conn.execute("DELETE FROM discovered_devices WHERE scan_id = $1", scan_id)

                for device in devices:
                    await conn.execute(
                        """
                        INSERT INTO discovered_devices (
                            scan_id,
                            ip_address,
                            mac_address,
                            hostname,
                            vendor,
                            open_ports,
                            http_banner,
                            onvif_info,
                            mdns_info,
                            llm_profile,
                            status,
                            device_id
                        ) VALUES (
                            $1, $2, $3, $4, $5, $6::jsonb, $7, $8::jsonb, $9::jsonb, $10::jsonb, $11, $12
                        )
                        """,
                        scan_id,
                        device.get("ip_address"),
                        device.get("mac_address"),
                        device.get("hostname"),
                        device.get("vendor"),
                        self._jsonb_dumps(device.get("open_ports") or []),
                        device.get("http_banner"),
                        self._jsonb_dumps(device.get("onvif_info") or {}),
                        self._jsonb_dumps(device.get("mdns_info") or {}),
                        self._jsonb_dumps(device.get("llm_profile") or {}),
                        "pending",
                        None,
                    )

                await conn.execute(
                    """
                    UPDATE scan_sessions
                    SET total_found = $2,
                        status = COALESCE(NULLIF(status, ''), 'completed')
                    WHERE scan_id = $1
                    """,
                    scan_id,
                    len(devices),
                )

    async def _fetch_scan_row(self, db_pool: asyncpg.Pool, scan_id: str) -> asyncpg.Record | None:
        async with db_pool.acquire() as conn:
            return await conn.fetchrow(
                """
                SELECT scan_id, cidr, status, started_at, completed_at, total_found, error_message
                FROM scan_sessions
                WHERE scan_id = $1
                """,
                scan_id,
            )

    async def _request(self, method: str, path: str, json: dict[str, Any] | None = None) -> dict[str, Any]:
        timeout = aiohttp.ClientTimeout(total=8)
        url = f"{self.scanner_base_url}{path}"

        try:
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.request(method, url, json=json) as response:
                    if response.status == 404:
                        raise LookupError("Scan not found on scanner")
                    if response.status >= 400:
                        detail = await response.text()
                        raise RuntimeError(f"Scanner error {response.status}: {detail}")
                    payload = await response.json()
                    if not isinstance(payload, dict):
                        raise RuntimeError("Scanner returned non-object JSON")
                    return payload
        except LookupError:
            raise
        except Exception as exc:
            logger.exception("Scanner request failed: %s %s", method, url)
            raise RuntimeError("Failed to communicate with scanner service") from exc

    @staticmethod
    def _parse_datetime(value: Any) -> datetime | None:
        if value is None:
            return None
        if isinstance(value, datetime):
            return value
        if isinstance(value, str) and value:
            normalized = value.replace("Z", "+00:00")
            dt = datetime.fromisoformat(normalized)
            if dt.tzinfo is None:
                return dt.replace(tzinfo=timezone.utc)
            return dt
        return None

    @staticmethod
    def _jsonb_dumps(value: Any) -> str:
        return json.dumps(value, ensure_ascii=False)

    @staticmethod
    def _coerce_json_list(value: Any) -> list[Any]:
        if isinstance(value, list):
            return value
        if isinstance(value, str) and value:
            try:
                parsed = json.loads(value)
                if isinstance(parsed, list):
                    return parsed
            except json.JSONDecodeError:
                return []
        return []

    @staticmethod
    def _coerce_json_dict(value: Any) -> dict[str, Any]:
        if isinstance(value, dict):
            return value
        if isinstance(value, str) and value:
            try:
                parsed = json.loads(value)
                if isinstance(parsed, dict):
                    return parsed
            except json.JSONDecodeError:
                return {}
        return {}

    def _normalize_discovered_row(self, row: asyncpg.Record) -> dict[str, Any]:
        payload = dict(row)
        payload["open_ports"] = self._coerce_json_list(payload.get("open_ports"))
        payload["onvif_info"] = self._coerce_json_dict(payload.get("onvif_info"))
        payload["mdns_info"] = self._coerce_json_dict(payload.get("mdns_info"))
        payload["llm_profile"] = self._coerce_json_dict(payload.get("llm_profile"))
        return payload

    @staticmethod
    def _infer_device_type(open_ports: list[Any]) -> str:
        ports = {int(port) for port in open_ports if isinstance(port, (int, float, str)) and str(port).isdigit()}
        if 554 in ports or 8554 in ports:
            return "CCTV"
        if 502 in ports:
            return "ACU"
        return "Unknown"

    @staticmethod
    def _infer_protocol(open_ports: list[Any]) -> str:
        ports = {int(port) for port in open_ports if isinstance(port, (int, float, str)) and str(port).isdigit()}
        if 554 in ports or 8554 in ports:
            return "RTSP"
        if 443 in ports:
            return "HTTPS"
        if 80 in ports or 8080 in ports:
            return "HTTP"
        if 502 in ports:
            return "Modbus"
        return "Unknown"

    @classmethod
    def _select_port(cls, open_ports: list[Any], device_type: str | None = None, protocol: str | None = None) -> int:
        preferred_order = [554, 8554, 443, 80, 8080, 502]
        normalized = [int(port) for port in open_ports if isinstance(port, (int, float, str)) and str(port).isdigit()]
        for preferred in preferred_order:
            if preferred in normalized:
                return preferred
        default_port = cls._default_port(device_type, protocol)
        if default_port is not None:
            return default_port
        if normalized:
            return normalized[0]
        return 80

    @staticmethod
    def _normalize_device_type(raw_device_type: Any) -> str:
        value = str(raw_device_type or "").strip().upper()
        if value in {"CCTV", "CAMERA", "NVR"}:
            return "CCTV"
        if value in {"ACU", "ACCESS_CONTROL", "ACCESS"}:
            return "ACU"
        if value:
            return value
        return "Unknown"

    @classmethod
    def _normalize_protocol(cls, raw_protocol: Any, device_type: str) -> str:
        value = str(raw_protocol or "").strip().upper()
        if value and value != "UNKNOWN":
            return value
        if device_type == "CCTV":
            return "RTSP"
        if device_type == "ACU":
            return "Modbus"
        return "Unknown"

    @staticmethod
    def _default_port(device_type: str | None, protocol: str | None) -> int | None:
        normalized_type = str(device_type or "").upper()
        normalized_protocol = str(protocol or "").upper()
        if normalized_type == "CCTV" or normalized_protocol == "RTSP":
            return 554
        if normalized_type == "ACU" or normalized_protocol == "MODBUS":
            return 502
        if normalized_protocol == "HTTPS":
            return 443
        if normalized_protocol == "HTTP":
            return 80
        return None

    async def _find_existing_device_by_ip(self, db_pool: asyncpg.Pool, ip_address: str) -> asyncpg.Record | None:
        async with db_pool.acquire() as conn:
            return await conn.fetchrow(
                """
                SELECT device_id, device_type, manufacturer, ip_address, port, protocol, location, status
                FROM devices
                WHERE ip_address = $1
                ORDER BY created_at DESC
                LIMIT 1
                """,
                ip_address,
            )

    async def _resolve_device_id(
        self,
        db_pool: asyncpg.Pool,
        requested_device_id: str | None,
        device_type: str,
        discovered_id: int,
    ) -> str:
        base = (requested_device_id or "").strip()
        if not base:
            normalized_type = (device_type or "DEVICE").upper().replace(" ", "_")
            base = f"{normalized_type}-{discovered_id:03d}"

        candidate = base
        suffix = 1
        async with db_pool.acquire() as conn:
            while True:
                exists = await conn.fetchval(
                    "SELECT 1 FROM devices WHERE device_id = $1",
                    candidate,
                )
                if not exists:
                    return candidate
                candidate = f"{base}-{suffix}"
                suffix += 1
