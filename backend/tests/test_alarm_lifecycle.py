from total_llm.services.alarm_service import ALARM_VALID_TRANSITIONS


def test_valid_transitions_defined():
    assert "triggered" in ALARM_VALID_TRANSITIONS
    assert "acknowledged" in ALARM_VALID_TRANSITIONS["triggered"]
    assert "false_alarm" in ALARM_VALID_TRANSITIONS["triggered"]
    assert len(ALARM_VALID_TRANSITIONS["closed"]) == 0


def test_triggered_to_acknowledged():
    assert "acknowledged" in ALARM_VALID_TRANSITIONS["triggered"]


def test_acknowledged_to_investigating():
    assert "investigating" in ALARM_VALID_TRANSITIONS["acknowledged"]


def test_investigating_to_resolved():
    assert "resolved" in ALARM_VALID_TRANSITIONS["investigating"]


def test_resolved_to_closed():
    assert "closed" in ALARM_VALID_TRANSITIONS["resolved"]


def test_any_to_false_alarm():
    assert "false_alarm" in ALARM_VALID_TRANSITIONS["triggered"]
    assert "false_alarm" in ALARM_VALID_TRANSITIONS["acknowledged"]
    assert "false_alarm" in ALARM_VALID_TRANSITIONS["investigating"]


def test_invalid_triggered_to_resolved():
    assert "resolved" not in ALARM_VALID_TRANSITIONS["triggered"]


def test_invalid_closed_any():
    assert len(ALARM_VALID_TRANSITIONS["closed"]) == 0


def test_invalid_resolved_to_triggered():
    assert "triggered" not in ALARM_VALID_TRANSITIONS["resolved"]
