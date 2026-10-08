from datetime import datetime, timezone

from hypothesis import given, settings
from hypothesis import strategies as st

from agentwatch_api.auth import Credentials
from agentwatch_api.service import ingest_event
from agentwatch_api.store import InMemoryStore

NOW = datetime(2026, 10, 8, 12, tzinfo=timezone.utc)
CREDS = Credentials("tejaswi", "a" * 64)

eids = st.from_regex(r"[0-9a-f]{32}", fullmatch=True)
ts_s = st.datetimes(min_value=datetime(2026, 1, 1), max_value=datetime(2026, 12, 31)).map(
    lambda d: d.strftime("%Y-%m-%dT%H:%M:%S.") + f"{d.microsecond // 1000:03d}Z"
)


@st.composite
def valid_bodies(draw):
    t = draw(st.sampled_from(["llm_call", "tool_call", "blocked_path", "spend_cap"]))
    b = {"agentId": "bot", "ownerId": "tejaswi", "ts": draw(ts_s), "eventId": draw(eids)}
    if t == "llm_call":
        b |= {"type": t, "model": "claude-haiku-4-5",
              "inputTokens": draw(st.integers(0, 10**6)), "outputTokens": draw(st.integers(0, 10**6))}
    elif t == "tool_call":
        b |= {"type": t, "tool": "read_file", "target": draw(st.text(max_size=20))}
    elif t == "blocked_path":
        b |= {"type": "blocked", "violationType": t, "attemptedPath": ".env"}
    else:
        b |= {"type": "blocked", "violationType": t,
              "attemptedCostUsd": draw(st.floats(0, 100, allow_nan=False))}
    return b


def required_fields(b):
    common = ["agentId", "ownerId", "ts", "eventId", "type"]
    per_type = {
        "llm_call": ["model", "inputTokens", "outputTokens"],
        "tool_call": ["tool", "target"],
    }
    if b["type"] == "blocked":
        extra = ["violationType", "attemptedPath" if b["violationType"] == "blocked_path" else "attemptedCostUsd"]
    else:
        extra = per_type[b["type"]]
    return common + extra


BAD_VALUES = {
    "agentId": ["", "has space", 5], "ownerId": ["", "someone-else", None], "ts": ["yesterday", "٢٠٢٦-01-01T00:00:00.000Z"],
    "eventId": ["X" * 32, ""], "type": ["file_read", None], "model": ["", 7],
    "inputTokens": [-1, "10", True, 1.5], "outputTokens": [-1, None], "tool": ["", 3],
    "target": [None, 4], "violationType": ["oops", None], "attemptedPath": ["", 9],
    "attemptedCostUsd": [-0.5, "1", True, float("nan")],
}


# Feature: agent-watch, Property 7: Invalid events are rejected and nothing is stored
@settings(max_examples=100)
@given(b=valid_bodies(), data=st.data())
def test_invalid_events_rejected_and_nothing_stored(b, data):
    s = InMemoryStore()
    name = data.draw(st.sampled_from(required_fields(b)))
    bad = dict(b)
    if data.draw(st.booleans()):
        del bad[name]
    else:
        bad[name] = data.draw(st.sampled_from(BAD_VALUES[name]))
    before = s.snapshot()
    r = ingest_event(s, CREDS, bad, NOW)
    assert r.status == 400
    assert isinstance(r.body.get("error"), str) and r.body["error"]
    assert s.snapshot() == before


# Sanity: the generator only yields valid bodies, so the mutations above are what fails.
@settings(max_examples=100)
@given(b=valid_bodies())
def test_valid_bodies_are_accepted(b):
    assert ingest_event(InMemoryStore(), CREDS, b, NOW).status == 200
