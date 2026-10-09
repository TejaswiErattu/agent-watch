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


# ---- Property 16 ----

from agentwatch_api.auth import Credentials  # noqa: E402
from agentwatch_api.service import ingest_event  # noqa: E402
from agentwatch_api.store import InMemoryStore  # noqa: E402

CREDS = Credentials("o", "a" * 64)


class CountingPublisher:
    def __init__(self, fail):
        self.n, self.fail = 0, fail

    def publish(self, subject, body):
        self.n += 1
        if self.fail:
            raise RuntimeError("down")


@st.composite
def any_body(draw):
    b = {"agentId": "bot", "ownerId": "o", "ts": draw(ts),
         "eventId": draw(st.sampled_from(["0" * 32, "1" * 32, "2" * 32])),
         "type": draw(st.sampled_from(["llm_call", "tool_call", "blocked"]))}
    if b["type"] == "llm_call":
        b |= {"model": "claude-haiku-4-5", "inputTokens": 10, "outputTokens": 5}
    elif b["type"] == "tool_call":
        b |= {"tool": "t", "target": "x"}
    else:
        b |= {"violationType": "blocked_path", "attemptedPath": ".env"}
    return b


# Feature: agent-watch, Property 16: Alert publish rules
@settings(max_examples=100)
@given(st.lists(any_body(), min_size=1, max_size=8), st.booleans())
def test_alert_publish_rules(bodies, fail):
    s, p = InMemoryStore(), CountingPublisher(fail)
    expected = 0
    for b in bodies:
        before = p.n
        r = ingest_event(s, CREDS, b, NOW, publisher=p)
        assert r.status == 200
        new_blocked = b["type"] == "blocked" and not r.body["duplicate"]
        expected += new_blocked
        assert p.n - before == int(new_blocked)
        assert ("bot", f"{b['ts']}#{b['eventId']}") in s.items
    assert p.n == expected
