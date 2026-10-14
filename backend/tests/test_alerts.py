import logging
from datetime import datetime, timezone

from agentwatch_api.alerts import SnsPublisher, format_alert, publish_alert
from agentwatch_api.validation import Event, validate_event

NOW = datetime(2026, 10, 8, 12, tzinfo=timezone.utc)
TS = "2026-10-08T10:00:00.000Z"


def blocked(violation="blocked_path", agent="bad-bot", **over) -> Event:
    b = {"agentId": agent, "ownerId": "tejaswi", "ts": TS, "eventId": "ab" * 16,
         "type": "blocked", "violationType": violation}
    b |= {"attemptedPath": ".env"} if violation == "blocked_path" else {"attemptedCostUsd": 0.0123}
    e = validate_event(b | over, NOW)
    assert isinstance(e, Event), e
    return e


class FakePublisher:
    def __init__(self, exc=None):
        self.calls, self.exc = [], exc

    def publish(self, subject, body):
        self.calls.append((subject, body))
        if self.exc:
            raise self.exc


def test_subject_names_agent_and_violation():
    subject, _ = format_alert(blocked())
    assert "bad-bot" in subject and "blocked_path" in subject


def test_subject_fits_sns_limits_for_long_agent_id():
    subject, _ = format_alert(blocked(agent="a" * 128))
    assert len(subject) <= 100 and "\n" not in subject and subject.isascii()


def test_blocked_path_body():
    _, body = format_alert(blocked(meta={"tool": "read_file", "entry": ".env"}))
    for s in ("bad-bot", "blocked_path", TS, "attemptedPath", ".env", "read_file"):
        assert s in body


def test_spend_cap_body():
    _, body = format_alert(blocked("spend_cap"))
    assert "attemptedCostUsd" in body and "0.0123" in body and "spend_cap" in body


def test_control_chars_in_path_are_escaped():
    _, body = format_alert(blocked(attemptedPath="x\nFAKE: line\r\x00"))
    assert "\nFAKE" not in body and "\r" not in body and "\x00" not in body
    assert "x\\nFAKE: line\\r\\x00" in body


def test_publish_alert_success():
    p = FakePublisher()
    e = blocked()
    assert publish_alert(p, e) is True
    assert p.calls == [format_alert(e)]


def test_publish_alert_failure_logs_and_returns_false(caplog):
    p = FakePublisher(RuntimeError("secret-ish message"))
    with caplog.at_level(logging.INFO, logger="agentwatch_api"):
        assert publish_alert(p, blocked()) is False
    rec = [r for r in caplog.records if "alert_publish_failed" in r.getMessage()]
    assert len(rec) == 1
    msg = rec[0].getMessage()
    assert "bad-bot" in msg and "ab" * 16 in msg and "secret-ish" not in msg


def test_sns_publisher_calls_client():
    class FakeSns:
        def __init__(self):
            self.kw = None

        def publish(self, **kw):
            self.kw = kw

    c = FakeSns()
    SnsPublisher("arn:aws:sns:us-west-2:123456789012:t", client=c).publish("S", "B")
    assert c.kw == {"TopicArn": "arn:aws:sns:us-west-2:123456789012:t", "Subject": "S", "Message": "B"}


# ---- v2 8.2: paused alert text ----


def paused(meta) -> Event:
    b = {"agentId": "demo-bot", "ownerId": "tejaswi", "ts": TS, "eventId": "cd" * 16,
         "type": "blocked", "violationType": "paused", "meta": meta}
    e = validate_event(b, NOW)
    assert isinstance(e, Event), e
    return e


def test_paused_llm_call_body_lists_action_and_model():
    subject, body = format_alert(paused({"action": "llm_call", "model": "m"}))
    assert "paused" in subject and "demo-bot" in subject
    lines = body.splitlines()
    assert "action: llm_call" in lines and "model: m" in lines
    assert lines.index("action: llm_call") < lines.index("model: m")
    assert "attemptedPath" not in body and "attemptedCostUsd" not in body


def test_paused_tool_call_body_lists_action_and_tool():
    _, body = format_alert(paused({"action": "tool_call", "tool": "read_file"}))
    lines = body.splitlines()
    assert "action: tool_call" in lines and "tool: read_file" in lines


def test_paused_meta_non_scalar_skipped_and_control_chars_escaped():
    _, body = format_alert(paused({"action": "llm_call\nFAKE: x", "model": {"nested": 1}}))
    assert "\nFAKE" not in body and "action: llm_call\\nFAKE: x" in body
    assert "model:" not in body


def test_paused_numeric_meta_printed():
    _, body = format_alert(paused({"action": "tool_call", "tool": 7}))
    assert "tool: 7" in body.splitlines()
