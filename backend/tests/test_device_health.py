import inspect

from total_llm.services.device_control import DeviceService


service = DeviceService()


def test_health_result_structure():
    required_keys = {
        "device_id",
        "ip_address",
        "port",
        "reachable",
        "port_open",
        "latency_ms",
        "status",
    }
    source = inspect.getsource(DeviceService.check_device_health)

    for key in required_keys:
        assert f'"{key}"' in source
    assert hasattr(service, "check_device_health")
    assert hasattr(service, "log_health_check")
    assert hasattr(service, "get_health_history")
    assert hasattr(service, "is_in_cooldown")


def test_cooldown_seconds_default():
    sig = inspect.signature(service.is_in_cooldown)
    assert sig.parameters["cooldown_seconds"].default == 300


def test_health_history_limit_default():
    sig = inspect.signature(service.get_health_history)
    assert sig.parameters["limit"].default == 50


def test_log_health_check_exists():
    sig = inspect.signature(service.log_health_check)
    params = list(sig.parameters.keys())
    assert "db_pool" in params
    assert "device_id" in params
    assert "result" in params
