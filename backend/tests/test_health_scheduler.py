"""장비 헬스체크 스케줄러 구조 테스트."""

from importlib import import_module

_scheduler_module = import_module("total_llm.services.health_scheduler")
HealthCheckScheduler = _scheduler_module.HealthCheckScheduler
get_scheduler = _scheduler_module.get_scheduler


def test_scheduler_default_interval():
    """기본 interval 30초 확인."""
    s = HealthCheckScheduler()
    assert s._interval == 30


def test_scheduler_custom_interval():
    """커스텀 interval 설정 가능."""
    s = HealthCheckScheduler(interval_seconds=5)
    assert s._interval == 5


def test_scheduler_starts_not_running():
    """초기 상태: running=False, task=None."""
    s = HealthCheckScheduler()
    assert s._running is False
    assert s._task is None


def test_get_scheduler_singleton():
    """get_scheduler()는 싱글톤 반환."""
    s1 = get_scheduler()
    s2 = get_scheduler()
    assert s1 is s2


def test_scheduler_has_required_methods():
    """start, stop, _run_once 메서드 존재."""
    s = HealthCheckScheduler()
    assert hasattr(s, "start")
    assert hasattr(s, "stop")
    assert hasattr(s, "_run_once")
    assert hasattr(s, "_loop")
