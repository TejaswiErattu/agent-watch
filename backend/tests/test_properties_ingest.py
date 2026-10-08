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


# ---- 2.3: Properties 10 and 12 ----

import pytest  # noqa: E402

from agentwatch_api.rules import EMPTY_CONFIG  # noqa: E402
from agentwatch_api.service import new_record  # noqa: E402
from agentwatch_api.store import META_SK  # noqa: E402


@st.composite
def submissions(draw):
    """Distinct-eventId bodies plus a submission order that may repeat them (resubmissions)."""
    pool = draw(st.lists(valid_bodies(), min_size=1, max_size=8, unique_by=lambda b: b["eventId"]))
    order = draw(st.lists(st.integers(0, len(pool) - 1), min_size=1, max_size=16))
    return [pool[i] for i in order]


# Feature: agent-watch, Property 10: Total spend equals the sum of distinct stored events
@settings(max_examples=100)
@given(subs=submissions())
def test_total_spend_equals_sum_of_distinct_events(subs):
    s = InMemoryStore()
    for b in subs:
        assert ingest_event(s, CREDS, b, NOW).status == 200
    events = [v for (_, sk), v in s.items.items() if sk != META_SK]
    assert len(events) == len({b["eventId"] for b in subs})
    assert s.get_agent("bot").total_spend_usd == pytest.approx(sum(e["costUsd"] for e in events), abs=1e-4)


class MaybeLosesRace(InMemoryStore):
    """Each create_agent_if_absent may lose to a same-owner request that lands first."""

    def __init__(self, losses):
        super().__init__()
        self.losses = iter(losses)

    def create_agent_if_absent(self, record):
        if next(self.losses, False):
            super().create_agent_if_absent(new_record(record.agent_id, CREDS, EMPTY_CONFIG))
        return super().create_agent_if_absent(record)


# Feature: agent-watch, Property 12: Registration invariants
@settings(max_examples=100)
@given(subs=submissions(), losses=st.lists(st.booleans(), max_size=4))
def test_registration_invariants_events_only(subs, losses):
    s = MaybeLosesRace(losses)
    stored_ts = []
    seen = set()
    for b in subs:
        assert ingest_event(s, CREDS, b, NOW).status == 200
        if b["eventId"] not in seen:
            seen.add(b["eventId"])
            stored_ts.append(b["ts"])
    metas = [v for (_, sk), v in s.items.items() if sk == META_SK]
    assert len(metas) == 1
    rec = s.get_agent("bot")
    assert rec.first_seen == stored_ts[0]
    assert rec.last_seen == max(stored_ts)
    assert rec.guardrails == EMPTY_CONFIG


# ---- 2.5: Property 12 with config PUTs interleaved ----

from agentwatch_api.rules import GuardrailConfig, to_json  # noqa: E402
from agentwatch_api.service import put_config  # noqa: E402

configs = st.builds(
    GuardrailConfig,
    st.one_of(st.none(), st.floats(0, 100, allow_nan=False)),
    st.lists(st.text(min_size=1, max_size=10), max_size=4).map(tuple),
)


# Feature: agent-watch, Property 12: Registration invariants
@settings(max_examples=100)
@given(
    subs=submissions(),
    puts=st.lists(st.tuples(st.integers(0, 16), configs), max_size=4),
    losses=st.lists(st.booleans(), max_size=6),
)
def test_registration_invariants_with_puts(subs, puts, losses):
    s = MaybeLosesRace(losses)
    ops = [("event", b) for b in subs]
    for pos, cfg in sorted(puts, key=lambda p: p[0], reverse=True):
        ops.insert(min(pos, len(ops)), ("put", cfg))
    stored_ts, seen, last_cfg = [], set(), EMPTY_CONFIG
    for kind, x in ops:
        if kind == "put":
            assert put_config(s, CREDS, "bot", to_json(x)).status == 200
            last_cfg = x
        else:
            assert ingest_event(s, CREDS, x, NOW).status == 200
            if x["eventId"] not in seen:
                seen.add(x["eventId"])
                stored_ts.append(x["ts"])
    assert sum(1 for (_, sk) in s.items if sk == META_SK) == 1
    rec = s.get_agent("bot")
    assert rec.first_seen == stored_ts[0]
    assert rec.last_seen == max(stored_ts)
    assert rec.guardrails == last_cfg
