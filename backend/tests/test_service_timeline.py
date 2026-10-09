"""Unit tests for get_timeline (service layer, no AWS)."""

import base64
import json

from agentwatch_api.auth import Credentials
from agentwatch_api.service import encode_cursor, get_timeline, ingest_event
from agentwatch_api.store import InMemoryStore
from datetime import datetime, timezone

NOW = datetime(2026, 10, 8, 12, tzinfo=timezone.utc)
CREDS = Credentials(owner_id="tejaswi", key_hash="a" * 64)
OTHER = Credentials(owner_id="tejaswi", key_hash="b" * 64)

TIMELINE_FIELDS = {
    "ts", "eventId", "type", "model", "tool", "target", "inputTokens",
    "outputTokens", "costUsd", "violationType", "attemptedCostUsd", "attemptedPath", "meta",
}


def _event(ts, eid, **extra):
    b = {"agentId": "bot", "ownerId": "tejaswi", "ts": ts, "eventId": eid}
    b |= extra
    return b


def _llm(ts, eid, in_toks=10, out_toks=5):
    return _event(ts, eid, type="llm_call", model="claude-haiku-4-5",
                  inputTokens=in_toks, outputTokens=out_toks)


def _ingest(store, body):
    assert ingest_event(store, CREDS, body, NOW).status == 200


def test_defaults_order_asc_limit_50():
    s = InMemoryStore()
    for i in range(3):
        _ingest(s, _llm(f"2026-10-08T00:00:0{i}.000Z", f"{i:032x}"))
    r = get_timeline(s, CREDS, "bot", {})
    assert r.status == 200
    eids = [e["eventId"] for e in r.body["events"]]
    assert eids == sorted(eids)  # ascending
    assert r.body["nextCursor"] is None


def test_bad_params_return_400():
    s = InMemoryStore()
    for q in (
        {"limit": "0"},
        {"limit": "101"},
        {"limit": "abc"},
        {"order": "sideways"},
        {"type": "not_a_type"},
        {"cursor": "@@@not-base64@@@"},
    ):
        assert get_timeline(s, CREDS, "bot", q).status == 400, q


def test_cursor_sk_that_is_not_an_event_sk_returns_400():
    s = InMemoryStore()
    bad = base64.urlsafe_b64encode(json.dumps({"sk": "META"}).encode()).decode()
    assert get_timeline(s, CREDS, "bot", {"cursor": bad}).status == 400


def test_missing_agent_returns_empty_with_null_cursor():
    s = InMemoryStore()
    r = get_timeline(s, CREDS, "ghost", {})
    assert r.status == 200
    assert r.body == {"events": [], "nextCursor": None}
    assert s.items == {}


def test_credential_mismatch_returns_403():
    s = InMemoryStore()
    _ingest(s, _llm("2026-10-08T00:00:00.000Z", "0" * 32))
    assert get_timeline(s, OTHER, "bot", {}).status == 403


def test_absent_fields_are_null():
    s = InMemoryStore()
    _ingest(s, _event("2026-10-08T00:00:00.000Z", "0" * 32, type="tool_call", tool="read_file", target="x"))
    (item,) = get_timeline(s, CREDS, "bot", {}).body["events"]
    assert set(item) == TIMELINE_FIELDS
    assert item["model"] is None
    assert item["inputTokens"] is None
    assert item["tool"] == "read_file"


def test_pagination_follows_cursor():
    s = InMemoryStore()
    for i in range(5):
        _ingest(s, _llm(f"2026-10-08T00:00:0{i}.000Z", f"{i:032x}"))
    first = get_timeline(s, CREDS, "bot", {"limit": "2"})
    assert len(first.body["events"]) == 2
    assert first.body["nextCursor"] is not None
    second = get_timeline(s, CREDS, "bot", {"limit": "2", "cursor": first.body["nextCursor"]})
    assert len(second.body["events"]) == 2
    # cursors must advance, no overlap
    seen = {e["eventId"] for e in first.body["events"]}
    assert seen.isdisjoint({e["eventId"] for e in second.body["events"]})


def test_encode_cursor_round_trips_an_event_sk():
    sk = "2026-10-08T00:00:00.000Z#" + "0" * 32
    cur = encode_cursor(sk)
    s = InMemoryStore()
    # a well-formed event-sk cursor on an empty agent is accepted (not a 400)
    assert get_timeline(s, CREDS, "bot", {"cursor": cur}).status == 200
