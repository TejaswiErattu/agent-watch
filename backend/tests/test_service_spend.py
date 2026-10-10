"""Unit tests for get_spend (service layer, no AWS)."""

from datetime import datetime, timezone

from agentwatch_api.auth import Credentials
from agentwatch_api.pricing import estimate_cost
from agentwatch_api.service import get_spend, ingest_event
from agentwatch_api.store import InMemoryStore, round_cost

NOW = datetime(2026, 10, 9, 12, 0, 0, tzinfo=timezone.utc)
NOW_TS = "2026-10-09T12:00:00.000Z"
START_TS = "2026-10-08T12:00:00.000Z"  # NOW - 24h
CREDS = Credentials(owner_id="tejaswi", key_hash="a" * 64)
OTHER = Credentials(owner_id="tejaswi", key_hash="b" * 64)
MODEL = "claude-haiku-4-5"
COST = round_cost(estimate_cost(MODEL, 1000, 500))


def _llm(ts, eid):
    return {"agentId": "bot", "ownerId": "tejaswi", "ts": ts, "eventId": eid,
            "type": "llm_call", "model": MODEL, "inputTokens": 1000, "outputTokens": 500}


def _ingest(store, ts, i):
    assert ingest_event(store, CREDS, _llm(ts, f"{i:032x}"), NOW).status == 200


def test_response_shape():
    s = InMemoryStore()
    _ingest(s, "2026-10-09T11:00:00.000Z", 1)
    r = get_spend(s, CREDS, "bot", NOW)
    assert r.status == 200
    assert r.body == {"agentId": "bot", "rollingSpendUsd": COST,
                      "windowStart": START_TS, "windowEnd": NOW_TS}


def test_window_excludes_start_and_includes_end():
    s = InMemoryStore()
    _ingest(s, START_TS, 1)                    # exactly now - 24h: excluded
    _ingest(s, "2026-10-08T12:00:00.001Z", 2)  # 1 ms inside: included
    _ingest(s, NOW_TS, 3)                      # exactly now: included
    _ingest(s, "2026-10-09T12:00:00.001Z", 4)  # 1 ms in the future: excluded
    r = get_spend(s, CREDS, "bot", NOW)
    assert r.status == 200
    assert abs(r.body["rollingSpendUsd"] - 2 * COST) < 1e-9


def test_sub_millisecond_now_is_floored_to_the_event_ts_precision():
    s = InMemoryStore()
    _ingest(s, NOW_TS, 1)
    r = get_spend(s, CREDS, "bot", NOW.replace(microsecond=999))
    assert r.body["windowEnd"] == NOW_TS
    assert abs(r.body["rollingSpendUsd"] - COST) < 1e-9


def test_missing_agent_returns_zero_and_creates_nothing():
    s = InMemoryStore()
    r = get_spend(s, CREDS, "nobody", NOW)
    assert r.status == 200
    assert r.body == {"agentId": "nobody", "rollingSpendUsd": 0.0,
                      "windowStart": START_TS, "windowEnd": NOW_TS}
    assert s.items == {}


def test_mismatched_credentials_return_403():
    s = InMemoryStore()
    _ingest(s, NOW_TS, 1)
    r = get_spend(s, OTHER, "bot", NOW)
    assert r.status == 403
    assert r.body == {"error": "forbidden"}


def test_invalid_agent_id_returns_400():
    s = InMemoryStore()
    r = get_spend(s, CREDS, "bad id!", NOW)
    assert r.status == 400
    assert "agentId" in r.body["error"]
    assert s.items == {}
