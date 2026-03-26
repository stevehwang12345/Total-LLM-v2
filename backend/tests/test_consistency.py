from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from total_llm.services.discovery_service import DiscoveryService


def _fields(result):
    return [m.field for m in result.mismatches]


def _severities(result):
    return [m.severity for m in result.mismatches]


class TestRule1OnvifPresent:
    def test_rule1_onvif_present_expects_cctv_pass(self):
        device_data = {
            "ip_address": "192.168.1.10",
            "onvif_info": {"endpoint": "http://192.168.1.10/onvif/device_service"},
            "open_ports": [554],
        }
        profile = {
            "device_type": "CCTV",
            "confidence": 0.9,
        }
        result = DiscoveryService.check_profile_consistency(device_data, profile)
        assert result.consistent is True
        assert result.score == 1.0
        assert result.mismatches == []
        assert result.checked_at

    def test_rule1_onvif_present_but_acu_fails(self):
        device_data = {
            "ip_address": "192.168.1.10",
            "onvif_info": {"endpoint": "http://192.168.1.10/onvif/device_service"},
            "open_ports": [502],
        }
        profile = {
            "device_type": "ACU",
            "confidence": 0.8,
        }
        result = DiscoveryService.check_profile_consistency(device_data, profile)
        assert result.consistent is False
        assert result.score == 0.8
        assert len(result.mismatches) == 1
        assert _fields(result) == ["device_type"]
        assert _severities(result) == ["high"]


class TestRule2MdnsRtsp:
    def test_rule2_mdns_rtsp_expects_cctv_pass(self):
        device_data = {
            "ip_address": "192.168.1.11",
            "mdns_info": {"service_type": "_rtsp._tcp"},
            "open_ports": [554],
        }
        profile = {
            "device_type": "CCTV",
            "confidence": 0.85,
        }
        result = DiscoveryService.check_profile_consistency(device_data, profile)
        assert result.consistent is True
        assert result.score == 1.0
        assert result.mismatches == []

    def test_rule2_mdns_rtsp_but_acu_fails(self):
        device_data = {
            "ip_address": "192.168.1.11",
            "mdns_info": {"service_type": "_rtsp._tcp"},
            "open_ports": [502],
        }
        profile = {
            "device_type": "ACU",
            "confidence": 0.75,
        }
        result = DiscoveryService.check_profile_consistency(device_data, profile)
        assert result.consistent is True
        assert result.score == 0.9
        assert len(result.mismatches) == 1
        assert _fields(result) == ["device_type"]
        assert _severities(result) == ["medium"]


class TestRule3Port554:
    def test_rule3_port554_cctv_consistent(self):
        device_data = {
            "ip_address": "192.168.1.12",
            "open_ports": [554, 80],
        }
        profile = {
            "device_type": "CCTV",
            "protocol": "RTSP",
            "confidence": 0.9,
        }
        result = DiscoveryService.check_profile_consistency(device_data, profile)
        assert result.consistent is True
        assert result.score == 1.0
        assert result.mismatches == []

    def test_rule3_port554_classified_as_acu(self):
        device_data = {
            "ip_address": "192.168.1.12",
            "open_ports": [554, 80],
        }
        profile = {
            "device_type": "ACU",
            "protocol": "Modbus",
            "confidence": 0.7,
        }
        result = DiscoveryService.check_profile_consistency(device_data, profile)
        assert result.consistent is False
        assert result.score == 0.6
        assert len(result.mismatches) == 2
        assert _fields(result) == ["device_type", "protocol"]
        assert _severities(result) == ["high", "high"]


class TestRule4Port502:
    def test_rule4_port502_acu_consistent(self):
        device_data = {
            "ip_address": "192.168.1.13",
            "open_ports": [502, 80],
        }
        profile = {
            "device_type": "ACU",
            "protocol": "Modbus",
            "confidence": 0.88,
        }
        result = DiscoveryService.check_profile_consistency(device_data, profile)
        assert result.consistent is True
        assert result.score == 1.0
        assert result.mismatches == []

    def test_rule4_port502_classified_as_cctv(self):
        device_data = {
            "ip_address": "192.168.1.13",
            "open_ports": [502, 80],
        }
        profile = {
            "device_type": "CCTV",
            "protocol": "RTSP",
            "confidence": 0.6,
        }
        result = DiscoveryService.check_profile_consistency(device_data, profile)
        assert result.consistent is False
        assert result.score == 0.6
        assert len(result.mismatches) == 2
        assert _fields(result) == ["device_type", "protocol"]
        assert _severities(result) == ["high", "high"]


class TestRule5DigestAuth:
    def test_rule5_digest_auth_low_severity(self):
        device_data = {
            "ip_address": "192.168.1.14",
            "http_banner": {"www_auth": "Digest realm=Camera"},
            "open_ports": [80],
        }
        profile = {
            "device_type": "CCTV",
            "confidence": 0.7,
        }
        result = DiscoveryService.check_profile_consistency(device_data, profile)
        assert result.consistent is True
        assert result.score == 1.0
        assert result.mismatches == []

    def test_rule5_digest_auth_but_acu_classified(self):
        device_data = {
            "ip_address": "192.168.1.14",
            "http_banner": {"www_auth": "Digest realm=Camera"},
            "open_ports": [80],
        }
        profile = {
            "device_type": "ACU",
            "confidence": 0.5,
        }
        result = DiscoveryService.check_profile_consistency(device_data, profile)
        assert result.consistent is True
        assert result.score == 0.96
        assert len(result.mismatches) == 1
        assert _fields(result) == ["device_type"]
        assert _severities(result) == ["low"]


class TestRule6VendorCamera:
    def test_rule6_vendor_hikvision_cctv_pass(self):
        device_data = {
            "ip_address": "192.168.1.15",
            "vendor": "hikvision",
            "open_ports": [554],
        }
        profile = {
            "device_type": "CCTV",
            "manufacturer": "Hikvision",
            "confidence": 0.92,
        }
        result = DiscoveryService.check_profile_consistency(device_data, profile)
        assert result.consistent is True
        assert result.score == 1.0
        assert result.mismatches == []

    def test_rule6_vendor_hikvision_classified_as_acu(self):
        device_data = {
            "ip_address": "192.168.1.15",
            "vendor": "hikvision",
            "open_ports": [554],
        }
        profile = {
            "device_type": "ACU",
            "manufacturer": "Hikvision",
            "confidence": 0.65,
        }
        result = DiscoveryService.check_profile_consistency(device_data, profile)
        assert result.consistent is False
        assert result.score == 0.7
        assert len(result.mismatches) == 2
        assert _fields(result) == ["device_type", "device_type"]
        assert _severities(result) == ["high", "medium"]


class TestRule7LowConfidence:
    def test_rule7_low_confidence_inconsistent(self):
        device_data = {
            "ip_address": "192.168.1.16",
            "open_ports": [80],
        }
        profile = {
            "device_type": "CCTV",
            "confidence": 0.3,
        }
        result = DiscoveryService.check_profile_consistency(device_data, profile)
        assert result.consistent is False
        assert result.score == 0.8
        assert len(result.mismatches) == 1
        assert _fields(result) == ["confidence"]
        assert _severities(result) == ["high"]

    def test_rule7_high_confidence_no_mismatch(self):
        device_data = {
            "ip_address": "192.168.1.16",
            "open_ports": [80],
        }
        profile = {
            "device_type": "CCTV",
            "confidence": 0.95,
        }
        result = DiscoveryService.check_profile_consistency(device_data, profile)
        assert result.consistent is True
        assert result.score == 1.0
        assert result.mismatches == []


class TestNoEvidence:
    def test_no_evidence_accepts_llm_judgment(self):
        device_data = {
            "ip_address": "192.168.1.17",
            "open_ports": [80],
        }
        profile = {
            "device_type": "Unknown",
            "confidence": 0.5,
        }
        result = DiscoveryService.check_profile_consistency(device_data, profile)
        assert result.consistent is True
        assert result.score == 1.0
        assert result.mismatches == []
