from datetime import datetime, timedelta, timezone

from hypothesis import given, settings
from hypothesis import strategies as st

from agentwatch_api.auth import Credentials
from agentwatch_api.service import get_spend, ingest_event
from agentwatch_api.store import InMemoryStore

CREDS = Credentials(owner_id="tejaswi", key_hash="a" * 64)
NOW = datetime(2026, 10, 9, 12, 0, 0, tzinfo=timezone.utc)
DAY_MS = 24 * 3600 * 1000
MODELS = ["claude-haiku-4-5", "unknown-model"]


def _ts(dt):
    return dt.strftime("%Y-%m-%dT%H:%M:%S.") + f"{dt.microsecond // 1000:03d}Z"


# Offsets in ms relative to NOW. Cluster some on the window edges (-DAY_MS and 0).
offsets = st.one_of(
    st.integers(-2 * DAY_MS, DAY_MS // 24),
    st.sampled_from([-DAY_MS - 1, -DAY_MS, -DAY_MS + 1, -1, 0, 1]),
)
events_s = st.lists(
    st.tuples(
        offsets,
        st.sampled_from(["llm_call", "tool_call"]),
        st.sampled_from(MODELS),
        st.integers(0, 100_000),
        st.integers(0, 100_000),
    ),
    max_size=25,
)


# Feature: agent-watch, Property 11: Rolling 24h spend matches the window sum
@settings(max_examples=100)
@given(events=events_s, now_us=st.integers(0, 999))
def test_rolling_spend_matches_window_sum(events, now_us):
    now = NOW + timedelta(microseconds=now_us)  # sub-ms part of now must not shift the window
    s = InMemoryStore()
    for i, (off, typ, model, tin, tout) in enumerate(events):
        body = {"agentId": "bot", "ownerId": "tejaswi",
                "ts": _ts(NOW + timedelta(milliseconds=off)), "eventId": f"{i:032x}", "type": typ}
        if typ == "llm_call":
            body |= {"model": model, "inputTokens": tin, "outputTokens": tout}
        else:
            body |= {"tool": "t", "target": "x"}
        assert ingest_event(s, CREDS, body, now).status == 200

    # Independent reference: walk the stored items, filter by -24h < offset <= 0.
    expected = sum(
        item["costUsd"] for (_, sk), item in s.items.items()
        if sk != "META"
        and -DAY_MS < (datetime.strptime(item["ts"], "%Y-%m-%dT%H:%M:%S.%fZ").replace(tzinfo=timezone.utc)
                       - NOW) / timedelta(milliseconds=1) <= 0
    )
    r = get_spend(s, CREDS, "bot", now)
    if not events:
        assert r.status == 200 and r.body["rollingSpendUsd"] == 0.0
        return
    assert r.status == 200
    assert abs(r.body["rollingSpendUsd"] - expected) <= 0.0001
    total = s.get_agent("bot").total_spend_usd
    assert r.body["rollingSpendUsd"] <= total + 1e-9
