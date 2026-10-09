from datetime import datetime, timezone

from hypothesis import given, settings, strategies as st

from agentwatch_api.alerts import format_alert
from agentwatch_api.validation import Event, validate_event

NOW = datetime(2026, 10, 8, 12, tzinfo=timezone.utc)

agent_ids = st.text(alphabet="abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789._-",
                    min_size=1, max_size=128)
# Printable paths (control chars are escaped in the body; covered by an example test).
paths = st.text(st.characters().filter(str.isprintable), min_size=1, max_size=1024)
costs = st.floats(min_value=0, max_value=1e6, allow_nan=False, allow_infinity=False)
ts = st.datetimes(min_value=datetime(2026, 1, 1), max_value=datetime(2026, 10, 8, 11)).map(
    lambda d: d.strftime("%Y-%m-%dT%H:%M:%S.") + f"{d.microsecond // 1000:03d}Z")


@st.composite
def blocked_events(draw):
    b = {"agentId": draw(agent_ids), "ownerId": "o", "ts": draw(ts),
         "eventId": draw(st.text("0123456789abcdef", min_size=32, max_size=32)), "type": "blocked"}
    if draw(st.booleans()):
        b |= {"violationType": "blocked_path", "attemptedPath": draw(paths)}
    else:
        b |= {"violationType": "spend_cap", "attemptedCostUsd": draw(costs)}
    e = validate_event(b, NOW)
    assert isinstance(e, Event), e
    return e


# Feature: agent-watch, Property 17: Alert content
@settings(max_examples=100)
@given(blocked_events())
def test_alert_content(e):
    subject, body = format_alert(e)
    assert e.agent_id in body and e.type == "blocked"
    assert e.item["violationType"] in body and e.ts in body
    if e.item["violationType"] == "blocked_path":
        assert e.item["attemptedPath"] in body
    else:
        assert repr(e.item["attemptedCostUsd"]) in body
    assert len(subject) <= 100 and subject.isascii() and "\n" not in subject
