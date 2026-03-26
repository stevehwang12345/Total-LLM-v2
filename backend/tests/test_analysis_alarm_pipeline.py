from total_llm.api.analysis import ALARM_AUTO_THRESHOLD, RISK_TO_PRIORITY


def test_risk_to_priority_mapping() -> None:
    assert RISK_TO_PRIORITY[3] == "P3"
    assert RISK_TO_PRIORITY[4] == "P2"
    assert RISK_TO_PRIORITY[5] == "P1"


def test_auto_threshold() -> None:
    assert ALARM_AUTO_THRESHOLD == 3


def test_low_risk_no_alarm() -> None:
    for level in [1, 2]:
        assert level < ALARM_AUTO_THRESHOLD


def test_high_risk_triggers_alarm() -> None:
    for level in [3, 4, 5]:
        assert level >= ALARM_AUTO_THRESHOLD
        assert level in RISK_TO_PRIORITY


def test_highest_risk_is_p1() -> None:
    assert RISK_TO_PRIORITY[5] == "P1"
