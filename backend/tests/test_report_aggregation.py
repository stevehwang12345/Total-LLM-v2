import inspect

from total_llm.services.report_service import ReportService


service = ReportService(report_dir=".")


def test_aggregate_methods_exist():
    assert hasattr(service, "aggregate_daily_log")
    assert hasattr(service, "aggregate_incident_report")
    assert hasattr(service, "aggregate_equipment_report")
    assert hasattr(service, "aggregate_monthly_report")


def test_aggregate_daily_log_signature():
    sig = inspect.signature(service.aggregate_daily_log)
    assert "db_pool" in sig.parameters
    assert "target_date" in sig.parameters


def test_aggregate_incident_report_signature():
    sig = inspect.signature(service.aggregate_incident_report)
    assert "alarm_id" in sig.parameters


def test_aggregate_equipment_report_signature():
    sig = inspect.signature(service.aggregate_equipment_report)
    assert "target_date" in sig.parameters


def test_aggregate_monthly_report_signature():
    sig = inspect.signature(service.aggregate_monthly_report)
    assert "year" in sig.parameters
    assert "month" in sig.parameters
