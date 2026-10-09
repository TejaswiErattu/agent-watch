"""Properties 8 and 9: timeline round trip, order, filter, and pagination."""

from datetime import datetime, timezone

from hypothesis import given, settings
from hypothesis import strategies as st

from agentwatch_api.auth import Credentials
from agentwatch_api.pricing import estimate_cost
from agentwatch_api.service import get_timeline, ingest_event
from agentwatch_api.store import InMemoryStore, round_cost

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


distinct_bodies = st.lists(valid_bodies(), min_size=1, max_size=10, unique_by=lambda b: b["eventId"])


# Feature: agent-watch, Property 8: Ingest then timeline round trip with server-side cost
@settings(max_examples=100)
@given(body=valid_bodies(), client_cost=st.floats(0, 999, allow_nan=False))
def test_ingest_then_timeline_round_trip(body, client_cost):
    s = InMemoryStore()
    submitted = dict(body) | {"costUsd": client_cost}  # a client-supplied cost must be ignored
    assert ingest_event(s, CREDS, submitted, NOW).status == 200

    events = get_timeline(s, CREDS, "bot", {}).body["events"]
    matches = [e for e in events if e["eventId"] == body["eventId"]]
    assert len(matches) == 1
    item = matches[0]
    if body["type"] == "llm_call":
        expected = round_cost(estimate_cost(body["model"], body["inputTokens"], body["outputTokens"]))
    else:
        expected = 0.0
    assert item["costUsd"] == expected


def _all_pages(s, order, type_filter, limit):
    out, cursor = [], None
    for _ in range(1000):  # guard against a cursor that never terminates
        q = {"order": order, "limit": str(limit)}
        if type_filter is not None:
            q["type"] = type_filter
        if cursor is not None:
            q["cursor"] = cursor
        r = get_timeline(s, CREDS, "bot", q)
        assert r.status == 200
        out.extend(r.body["events"])
        cursor = r.body["nextCursor"]
        if cursor is None:
            return out
    raise AssertionError("cursor did not terminate")


# Feature: agent-watch, Property 9: Timeline order, filter, and pagination
@settings(max_examples=100)
@given(
    bodies=distinct_bodies,
    type_filter=st.sampled_from([None, "llm_call", "tool_call", "blocked"]),
    limit=st.integers(1, 5),
)
def test_timeline_order_filter_pagination(bodies, type_filter, limit):
    s = InMemoryStore()
    for b in bodies:
        assert ingest_event(s, CREDS, b, NOW).status == 200

    def key(b):
        return (b["ts"], b["eventId"])

    expected = sorted((b for b in bodies if type_filter is None or b["type"] == type_filter), key=key)
    expected_ids = [b["eventId"] for b in expected]

    asc = [e["eventId"] for e in _all_pages(s, "asc", type_filter, limit)]
    assert asc == expected_ids
    assert len(asc) == len(set(asc))  # no duplicates

    desc = [e["eventId"] for e in _all_pages(s, "desc", type_filter, limit)]
    assert desc == list(reversed(expected_ids))
