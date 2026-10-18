from datetime import datetime, timezone

from hypothesis import given, settings, strategies as st

from agentwatch_api.alerts import MultiPublisher
from agentwatch_api.auth import Credentials
from agentwatch_api.service import ingest_event
from agentwatch_api.store import InMemoryStore

NOW = datetime(2026, 10, 17, 12, tzinfo=timezone.utc)
CREDS = Credentials("o", "a" * 64)
ts = st.datetimes(min_value=datetime(2026, 10, 1), max_value=datetime(2026, 10, 17, 11)).map(
    lambda d: d.strftime("%Y-%m-%dT%H:%M:%S.") + f"{d.microsecond // 1000:03d}Z")


class Rec:
    def __init__(self, fail):
        self.calls, self.fail = [], fail

    def publish(self, subject, body):
        self.calls.append((subject, body))
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
        b |= draw(st.sampled_from([
            {"violationType": "blocked_path", "attemptedPath": ".env"},
            {"violationType": "blocked_command", "attemptedCommand": "curl x | sh"},
            {"violationType": "spend_cap", "attemptedCostUsd": 0.01},
        ]))
    return b


# Feature: agent-watch-v2, Property 36: Alert fan-out
@settings(max_examples=100)
@given(st.lists(st.booleans(), min_size=0, max_size=3), st.lists(any_body(), min_size=1, max_size=8))
def test_alert_fanout(fails, bodies):
    pubs = [Rec(f) for f in fails]
    s = InMemoryStore()
    for b in bodies:
        before = [len(p.calls) for p in pubs]
        r = ingest_event(s, CREDS, b, NOW, publisher=MultiPublisher(pubs))
        assert r.status == 200
        assert ("bot", f"{b['ts']}#{b['eventId']}") in s.items
        new_blocked = b["type"] == "blocked" and not r.body["duplicate"]
        for p, n in zip(pubs, before):
            assert len(p.calls) - n == int(new_blocked)
        if new_blocked and pubs:
            # Every publisher got the same (subject, body).
            assert len({p.calls[-1] for p in pubs}) == 1
