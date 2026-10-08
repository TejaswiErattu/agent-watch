from datetime import datetime, timezone

import pytest

from agentwatch_api.auth import Credentials
from agentwatch_api.pricing import estimate_cost
from agentwatch_api.rules import to_json, EMPTY_CONFIG
from agentwatch_api.service import Result, ingest_event
from agentwatch_api.store import META_SK, InMemoryStore, event_sk, round_cost

NOW = datetime(2026, 10, 8, 12, tzinfo=timezone.utc)
H = "a" * 64
CREDS = Credentials("tejaswi", H)
MODEL = "claude-haiku-4-5"
TS = "2026-10-08T10:00:00.000Z"


def body(type_="llm_call", eid="0" * 32, ts=TS, **over):
    b = {"agentId": "bot", "ownerId": "tejaswi", "ts": ts, "eventId": eid, "type": type_}
    if type_ == "llm_call":
        b |= {"model": MODEL, "inputTokens": 1000, "outputTokens": 500}
    elif type_ == "tool_call":
        b |= {"tool": "read_file", "target": "notes.md"}
    else:
        b |= {"violationType": "blocked_path", "attemptedPath": ".env"}
    return b | over


def test_invalid_body_400_stores_nothing():
    s = InMemoryStore()
    r = ingest_event(s, CREDS, body(eventId="nope"), NOW)
    assert r.status == 400 and "eventId" in r.body["error"]
    assert s.items == {}


def test_body_owner_must_match_credentials():
    s = InMemoryStore()
    r = ingest_event(s, CREDS, body(ownerId="someone"), NOW)
    assert r.status == 400 and "ownerId" in r.body["error"]
    assert s.items == {}


def test_first_event_registers_agent():
    s = InMemoryStore()
    assert ingest_event(s, CREDS, body(type_="tool_call"), NOW).status == 200
    rec = s.get_agent("bot")
    assert rec.owner_id == "tejaswi"
    assert to_json(rec.guardrails) == to_json(EMPTY_CONFIG)
    assert rec.first_seen == rec.last_seen == TS


def test_llm_cost_is_server_side():
    s = InMemoryStore()
    r = ingest_event(s, CREDS, body(costUsd=0.0), NOW)
    expected = round_cost(estimate_cost(MODEL, 1000, 500))
    assert expected > 0
    assert r == Result(200, {"eventId": "0" * 32, "costUsd": expected, "duplicate": False})
    assert s.items[("bot", event_sk(TS, "0" * 32))]["costUsd"] == expected
    assert s.get_agent("bot").total_spend_usd == expected


@pytest.mark.parametrize("type_", ["tool_call", "blocked"])
def test_non_llm_events_cost_zero_even_if_client_sends_cost(type_):
    s = InMemoryStore()
    r = ingest_event(s, CREDS, body(type_=type_, costUsd=99.0), NOW)
    assert r.status == 200 and r.body["costUsd"] == 0.0
    assert s.get_agent("bot").total_spend_usd == 0.0


def test_unknown_model_costs_zero():
    s = InMemoryStore()
    r = ingest_event(s, CREDS, body(model="mystery-model"), NOW)
    assert r.status == 200 and r.body["costUsd"] == 0.0


def test_response_shape():
    r = ingest_event(InMemoryStore(), CREDS, body(type_="tool_call"), NOW)
    assert set(r.body) == {"eventId", "costUsd", "duplicate"}
    assert r.body["duplicate"] is False


def test_only_one_meta_after_two_events():
    s = InMemoryStore()
    ingest_event(s, CREDS, body(eid="1" * 32), NOW)
    ingest_event(s, CREDS, body(eid="2" * 32), NOW)
    assert sum(1 for (_, sk) in s.items if sk == META_SK) == 1
