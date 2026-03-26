"""보고서 PDF 생성 테스트."""
import tempfile
from pathlib import Path

from total_llm.services.report_service import ReportService


service = ReportService(report_dir=tempfile.mkdtemp())

DAILY_LOG_DATA = {
    "date": "2026-03-26",
    "alarms": {"total": 5, "closed_count": 3, "open_count": 2, "false_alarm_count": 1},
    "devices": {"total": 4, "online_count": 3, "offline_count": 1},
    "notes": "특이사항 없음",
}

INCIDENT_DATA = {
    "alarm_id": "test-alarm-001",
    "severity": "높음",
    "priority": "P2",
    "timestamp": "2026-03-26 10:00:00",
    "location": "정문",
    "status": "resolved",
    "device_id": "CCTV-001",
    "description": "테스트 사건 발생",
    "investigation_notes": "현장 확인 완료",
    "analysis": None,
}

EQUIPMENT_DATA = {
    "date": "2026-03-26",
    "total": 4,
    "online": 3,
    "offline": 1,
    "devices": [
        {
            "device_id": "CCTV-001",
            "device_type": "CCTV",
            "location": "정문",
            "status": "online",
            "security_grade": "GRADE_2",
            "last_health_check": None,
        },
    ],
}

MONTHLY_DATA = {
    "period": {"year": 2026, "month": 3, "start": "2026-03-01", "end": "2026-04-01"},
    "alarms": {
        "total": 42,
        "false_alarm_count": 8,
        "false_alarm_rate": 19.0,
        "by_severity": {},
        "daily_trend": [],
    },
    "analyses": {"total": 30, "high_risk_count": 5},
    "devices": {"total": 4, "online": 3, "availability_rate": 75.0},
}


def _assert_valid_pdf(path: Path) -> None:
    assert path.exists()
    assert path.stat().st_size > 1000
    assert path.read_bytes().startswith(b"%PDF")


def test_build_daily_log_pdf():
    with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as f:
        path = Path(f.name)
    try:
        service._build_daily_log_pdf(path, DAILY_LOG_DATA)
        _assert_valid_pdf(path)
    finally:
        path.unlink(missing_ok=True)


def test_build_incident_report_pdf():
    with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as f:
        path = Path(f.name)
    try:
        service._build_incident_report_pdf(path, INCIDENT_DATA)
        _assert_valid_pdf(path)
    finally:
        path.unlink(missing_ok=True)


def test_build_equipment_report_pdf():
    with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as f:
        path = Path(f.name)
    try:
        service._build_equipment_report_pdf(path, EQUIPMENT_DATA)
        _assert_valid_pdf(path)
    finally:
        path.unlink(missing_ok=True)


def test_build_monthly_report_pdf():
    with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as f:
        path = Path(f.name)
    try:
        service._build_monthly_report_pdf(path, MONTHLY_DATA)
        _assert_valid_pdf(path)
    finally:
        path.unlink(missing_ok=True)
