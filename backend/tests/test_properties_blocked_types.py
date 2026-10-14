"""Property 39 (v2). One clause per Violation_Type; later groups add a clause to CLAUSES.

A clause gives a strategy for the type's valid extra fields and a strategy for invalid variants
(the type's required field missing, empty, non-string, or too long). Meta-only types have no
invalid variants beyond an unknown violationType, which the shared test covers.
The v1 Properties 7 and 8 stay untouched.
"""

from datetime import datetime, timezone

from hypothesis import given, settings, strategies as st

from agentwatch_api.auth import Credentials
from agentwatch_api.service import get_timeline, ingest_event
from agentwatch_api.store import InMemoryStore

NOW = datetime(2026, 10, 8, 12, tzinfo=timezone.utc)
CREDS = Credentials("o", "a" * 64)
ALL_SEVEN = ("spend_cap", "blocked_path", "paused", "blocked_command",
             "rate_limit", "secret_redacted", "blocked_domain")

ts = st.datetimes(min_value=datetime(2026, 1, 1), max_value=datetime(2026, 10, 8, 11)).map(
    lambda d: d.strftime("%Y-%m-%dT%H:%M:%S.") + f"{d.microsecond // 1000:03d}Z")
event_ids = st.text("0123456789abcdef", min_size=32, max_size=32)
meta_values = st.one_of(st.text(max_size=50), st.integers(-1000, 1000), st.booleans(), st.none())


# ---- clauses: vt -> (valid extras, invalid extras or None) ----

@st.composite
def _paused_valid(draw):
    action = draw(st.sampled_from(["llm_call", "tool_call"]))
    detail_key = "model" if action == "llm_call" else "tool"
    meta = {"action": action, detail_key: draw(meta_values)}
    # Fields that belong to other types are dropped, never validated.
    extra = draw(st.fixed_dictionaries({}, optional={"attemptedPath": st.text(max_size=5),
                                                     "attemptedCostUsd": st.integers(0, 5)}))
    return {"meta": meta, **extra}


CLAUSES = {
    "paused": (_paused_valid, None),
    # 9.2 blocked_command, 12.1 rate_limit, 14.2 secret_redacted, 15.1 blocked_domain
}

TIMELINE_DETAIL_FIELDS = ()  # 9.2 adds "attemptedCommand", 15.1 adds "attemptedUrl"


def _body(vt, eid, t, extra):
    return {"agentId": "bot", "ownerId": "o", "ts": t, "eventId": eid,
            "type": "blocked", "violationType": vt, **extra}


@st.composite
def valid_cases(draw):
    vt = draw(st.sampled_from(sorted(CLAUSES)))
    return _body(vt, draw(event_ids), draw(ts), draw(CLAUSES[vt][0]()))


@st.composite
def invalid_cases(draw):
    with_invalid = sorted(vt for vt, (_, bad) in CLAUSES.items() if bad is not None)
    if with_invalid and draw(st.booleans()):
        vt = draw(st.sampled_from(with_invalid))
        return _body(vt, draw(event_ids), draw(ts), draw(CLAUSES[vt][1]()))
    vt = draw(st.sampled_from(sorted(CLAUSES)))
    unknown = draw(st.one_of(st.text(max_size=20).filter(lambda s: s not in ALL_SEVEN),
                             st.integers(), st.none()))
    return _body(vt, draw(event_ids), draw(ts), draw(CLAUSES[vt][0]())) | {"violationType": unknown}


# Feature: agent-watch-v2, Property 39: New blocked events validate like the old ones
@settings(max_examples=100)
@given(valid_cases(), invalid_cases())
def test_new_blocked_events_validate_like_the_old_ones(good, bad):
    s = InMemoryStore()

    r = ingest_event(s, CREDS, good, NOW)
    assert r.status == 200, r.body
    assert r.body["costUsd"] == 0.0 and r.body["duplicate"] is False
    stored = s.items[("bot", f"{good['ts']}#{good['eventId']}")]
    assert stored["costUsd"] == 0.0 and stored["violationType"] == good["violationType"]
    assert "attemptedPath" not in stored and "attemptedCostUsd" not in stored

    (item,) = get_timeline(s, CREDS, "bot", {}).body["events"]
    assert item["violationType"] == good["violationType"] and item["costUsd"] == 0.0
    for name in TIMELINE_DETAIL_FIELDS:
        assert item[name] == good.get(name)

    snap = s.snapshot()
    r = ingest_event(s, CREDS, bad, NOW)
    assert r.status == 400, (bad, r.body)
    assert s.snapshot() == snap
