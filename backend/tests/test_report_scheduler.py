from importlib import import_module
from pathlib import Path
from unittest.mock import patch

with patch.object(Path, "mkdir"):
    _scheduler_module = import_module("total_llm.services.report_scheduler")

ReportScheduler = _scheduler_module.ReportScheduler
get_report_scheduler = _scheduler_module.get_report_scheduler


def test_scheduler_initial_state():
    s = ReportScheduler()
    assert s._running is False
    assert s._task is None


def test_singleton():
    s1 = get_report_scheduler()
    s2 = get_report_scheduler()
    assert s1 is s2


def test_has_required_methods():
    s = ReportScheduler()
    assert hasattr(s, "start")
    assert hasattr(s, "stop")
    assert hasattr(s, "_run_daily")
    assert hasattr(s, "_run_monthly")
    assert hasattr(s, "_loop")
