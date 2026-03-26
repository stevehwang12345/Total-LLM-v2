from __future__ import annotations

import asyncio
import importlib
import ipaddress
import logging
import socket
import urllib.parse
import uuid
from datetime import datetime
from typing import Any

import httpx
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

logger = logging.getLogger(__name__)

app = FastAPI(title="Security Scanner Sidecar", version="1.0.0")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

SECURITY_PORTS = [
    80,
    443,
    554,
    502,
    8000,
    8080,
    8443,
    8554,
    8888,
    9000,
    37777,
    34567,
]
SCAN_TIMEOUT = 4

_scan_store: dict[str, dict[str, Any]] = {}
_scan_lock = asyncio.Lock()


class ScanRequest(BaseModel):
    cidr: str
    timeout_sec: int = 90


@app.get("/health")
async def health():
    return {"status": "ok", "service": "scanner"}


@app.post("/scan")
async def start_scan(req: ScanRequest):
    parts = req.cidr.split("/")
    if len(parts) != 2:
        raise HTTPException(status_code=422, detail="Invalid CIDR format")
    prefix = int(parts[1])
    if prefix < 24:
        raise HTTPException(status_code=422, detail="Only /24 or smaller networks supported")

    async with _scan_lock:
        running = [s for s in _scan_store.values() if s["status"] == "running"]
        if running:
            raise HTTPException(status_code=409, detail="Scan already in progress")
        scan_id = str(uuid.uuid4())
        _scan_store[scan_id] = {
            "scan_id": scan_id, "cidr": req.cidr, "status": "running",
            "started_at": datetime.utcnow().isoformat(),
            "completed_at": None, "devices": [], "error": None,
        }

    asyncio.create_task(_run_scan(scan_id, req.cidr, req.timeout_sec))
    return {"scan_id": scan_id, "status": "running", "cidr": req.cidr}


@app.get("/status/{scan_id}")
async def get_scan_status(scan_id: str):
    if scan_id not in _scan_store:
        raise HTTPException(status_code=404, detail="Scan not found")
    scan = _scan_store[scan_id]
    return {
        "scan_id": scan_id, "status": scan["status"], "cidr": scan["cidr"],
        "started_at": scan["started_at"], "completed_at": scan["completed_at"],
        "total_found": len(scan["devices"]), "error": scan["error"],
    }


@app.get("/results/{scan_id}")
async def get_scan_results(scan_id: str):
    if scan_id not in _scan_store:
        raise HTTPException(status_code=404, detail="Scan not found")
    scan = _scan_store[scan_id]
    return {
        "scan_id": scan_id,
        "status": scan["status"],
        "cidr": scan["cidr"],
        "devices": scan["devices"],
        "total_found": len(scan["devices"]),
    }


async def _run_scan(scan_id: str, cidr: str, timeout_sec: int) -> None:
    try:
        logger.info("Starting scan: %s (%s)", scan_id, cidr)
        devices: dict[str, dict[str, Any]] = {}

        arp_results = await _arp_scan(cidr)
        for ip, mac in arp_results.items():
            devices[ip] = {
                "ip_address": ip,
                "mac_address": mac,
                "open_ports": [],
                "vendor": None,
                "http_banner": None,
                "onvif_info": None,
                "mdns_info": None,
                "hostname": None,
            }

        onvif_results = await _wsd_discover()
        for endpoint, info in onvif_results.items():
            ip = info.get("ip")
            if ip:
                if ip not in devices:
                    devices[ip] = {
                        "ip_address": ip,
                        "mac_address": None,
                        "open_ports": [],
                        "vendor": None,
                        "http_banner": None,
                        "onvif_info": None,
                        "mdns_info": None,
                        "hostname": None,
                    }
                devices[ip]["onvif_info"] = info

        mdns_results = await _mdns_discover()
        for ip, info in mdns_results.items():
            if ip not in devices:
                devices[ip] = {
                    "ip_address": ip,
                    "mac_address": None,
                    "open_ports": [],
                    "vendor": None,
                    "http_banner": None,
                    "onvif_info": None,
                    "mdns_info": None,
                    "hostname": None,
                }
            devices[ip]["mdns_info"] = info

        tasks = [_fingerprint_device(ip, info) for ip, info in devices.items()]
        if tasks:
            fingerprinted = await asyncio.wait_for(
                asyncio.gather(*tasks, return_exceptions=True),
                timeout=max(timeout_sec, SCAN_TIMEOUT + 5),
            )
            for result in fingerprinted:
                if isinstance(result, dict) and result.get("ip_address"):
                    devices[result["ip_address"]].update(result)

        _scan_store[scan_id]["devices"] = list(devices.values())
        _scan_store[scan_id]["status"] = "completed"
        _scan_store[scan_id]["completed_at"] = datetime.utcnow().isoformat()
        logger.info("Scan completed: %s, found %d devices", scan_id, len(devices))

    except Exception as exc:
        logger.exception("Scan failed: %s", scan_id)
        _scan_store[scan_id]["status"] = "failed"
        _scan_store[scan_id]["error"] = str(exc)
        _scan_store[scan_id]["completed_at"] = datetime.utcnow().isoformat()


async def _arp_scan(cidr: str) -> dict[str, str]:
    try:
        scapy_all = importlib.import_module("scapy.all")
        arp = scapy_all.ARP
        ether = scapy_all.Ether
        srp = scapy_all.srp

        net = ipaddress.ip_network(cidr, strict=False)
        packet = ether(dst="ff:ff:ff:ff:ff:ff") / arp(pdst=str(net))
        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(None, lambda: srp(packet, timeout=3, verbose=False)[0])
        return {received.psrc: received.hwsrc for _, received in result}
    except Exception as exc:
        logger.warning("ARP scan failed: %s", exc)
        return {}


async def _wsd_discover() -> dict[str, dict]:
    try:
        wsdiscovery_discovery = importlib.import_module("wsdiscovery.discovery")
        wsdiscovery_qname = importlib.import_module("wsdiscovery.qname")
        ws_discovery = wsdiscovery_discovery.ThreadedWSDiscovery
        q_name = wsdiscovery_qname.QName

        loop = asyncio.get_event_loop()

        def _do_wsd() -> dict[str, dict]:
            wsd = ws_discovery()
            wsd.start()
            try:
                types = [q_name("http://www.onvif.org/ver10/network/wsdl", "NetworkVideoTransmitter")]
                services = wsd.searchServices(types=types, timeout=3)
                results = {}
                for service in services:
                    xaddrs = service.getXAddrs()
                    if xaddrs:
                        endpoint = xaddrs[0]
                        parsed = urllib.parse.urlparse(endpoint)
                        ip = parsed.hostname
                        results[endpoint] = {
                            "ip": ip,
                            "endpoint": endpoint,
                            "scopes": [str(s) for s in service.getScopes()],
                        }
                return results
            finally:
                wsd.stop()

        return await loop.run_in_executor(None, _do_wsd)
    except Exception as exc:
        logger.warning("WS-Discovery failed: %s", exc)
        return {}


async def _mdns_discover() -> dict[str, dict]:
    try:
        zeroconf = importlib.import_module("zeroconf")
        service_browser = zeroconf.ServiceBrowser
        zeroconf_client = zeroconf.Zeroconf

        results: dict[str, dict] = {}

        class Handler:
            def add_service(self, zc, type_, name):
                info = zc.get_service_info(type_, name)
                if info and info.parsed_scoped_addresses():
                    ip = info.parsed_scoped_addresses()[0]
                    results[ip] = {"service_type": type_, "name": name, "port": info.port}

            def update_service(self, *args):
                return None

            def remove_service(self, *args):
                return None

        loop = asyncio.get_event_loop()

        def _do_mdns() -> dict[str, dict]:
            import time

            zc = zeroconf_client()
            try:
                services = ["_rtsp._tcp.local.", "_http._tcp.local.", "_onvif._tcp.local."]
                _browsers = [service_browser(zc, svc, Handler()) for svc in services]
                time.sleep(3)
                return results
            finally:
                zc.close()

        return await loop.run_in_executor(None, _do_mdns)
    except Exception as exc:
        logger.warning("mDNS discovery failed: %s", exc)
        return {}


async def _fingerprint_device(ip: str, current_info: dict[str, Any]) -> dict[str, Any]:
    result: dict[str, Any] = {"ip_address": ip}

    # hostname (reverse DNS)
    try:
        loop = asyncio.get_event_loop()
        hostname, _, _ = await loop.run_in_executor(
            None, socket.gethostbyaddr, ip
        )
        result["hostname"] = hostname
    except (socket.herror, OSError):
        result["hostname"] = None

    try:
        loop = asyncio.get_event_loop()
        ports_str = ",".join(str(p) for p in SECURITY_PORTS)

        def _nmap_scan() -> list[int]:
            nmap_module = importlib.import_module("nmap")
            nm = nmap_module.PortScanner()
            nm.scan(ip, ports_str, arguments=f"-Pn -T4 --open --host-timeout {SCAN_TIMEOUT}s")
            open_ports: list[int] = []
            if ip in nm.all_hosts():
                for proto in nm[ip].all_protocols():
                    for port, state in nm[ip][proto].items():
                        if state.get("state") == "open":
                            open_ports.append(port)
            return open_ports

        result["open_ports"] = await asyncio.wait_for(
            loop.run_in_executor(None, _nmap_scan), timeout=SCAN_TIMEOUT + 5
        )
    except Exception as exc:
        logger.warning("Port fingerprint failed for %s: %s", ip, exc)
        result["open_ports"] = []

    mac = current_info.get("mac_address")
    if mac:
        try:
            mac_vendor_lookup = importlib.import_module("mac_vendor_lookup")
            mac_lookup = mac_vendor_lookup.AsyncMacLookup()
            result["vendor"] = await mac_lookup.lookup(mac)
        except Exception as exc:
            logger.debug("Vendor lookup failed for %s (%s): %s", ip, mac, exc)
            result["vendor"] = None

    banner_ports = [p for p in (80, 8080, 443, 8443, 8000) if p in result.get("open_ports", [])]
    for port in banner_ports:
        if port in result.get("open_ports", []):
            try:
                scheme = "https" if port == 443 else "http"
                if port == 8443:
                    scheme = "https"
                async with httpx.AsyncClient(verify=False, timeout=4.0) as client:
                    resp = await client.get(f"{scheme}://{ip}:{port}", follow_redirects=False)
                    result["http_banner"] = {
                        "server": resp.headers.get("server", ""),
                        "www_auth": resp.headers.get("www-authenticate", ""),
                        "status_code": resp.status_code,
                    }
                    break
            except Exception as exc:
                logger.debug("HTTP banner probe failed for %s:%s: %s", ip, port, exc)
                continue

    return result
