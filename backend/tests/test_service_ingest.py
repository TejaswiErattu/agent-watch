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


# ---- 2.3 races, duplicates, forbidden, lastSeen ----

from agentwatch_api.rules import GuardrailConfig  # noqa: E402
from agentwatch_api.service import new_record  # noqa: E402

OTHER = Credentials("intruder", "b" * 64)


class RacingStore(InMemoryStore):
    """create_agent_if_absent loses: another request's record lands first."""

    def __init__(self, racer_creds):
        super().__init__()
        self.racer_creds = racer_creds
        self.create_calls = 0

    def create_agent_if_absent(self, record):
        self.create_calls += 1
        super().create_agent_if_absent(new_record(record.agent_id, self.racer_creds, EMPTY_CONFIG))
        return super().create_agent_if_absent(record)  # False: already exists


class SwapVerifierStore(InMemoryStore):
    """The record's keyVerifier is replaced between authorize and the transaction."""

    def record_event(self, event, cost, key_verifier):
        self.items[(event.agent_id, META_SK)]["keyVerifier"] = "c" * 64
        return super().record_event(event, cost, key_verifier)


def test_lost_race_same_owner_rereads_and_stores():
    s = RacingStore(CREDS)
    r = ingest_event(s, CREDS, body(), NOW)
    assert r.status == 200 and r.body["duplicate"] is False
    assert s.create_calls == 1
    assert s.get_agent("bot").first_seen == TS


def test_lost_race_other_owner_forbidden():
    s = RacingStore(OTHER)
    r = ingest_event(s, CREDS, body(), NOW)
    assert r == Result(403, {"error": "forbidden"})
    assert [sk for (_, sk) in s.items] == [META_SK]
    assert s.get_agent("bot").first_seen is None


@pytest.mark.parametrize("creds", [OTHER, Credentials("tejaswi", "b" * 64), Credentials("intruder", H)])
def test_mismatched_existing_record_forbidden_and_unchanged(creds):
    s = InMemoryStore()
    ingest_event(s, CREDS, body(eid="1" * 32), NOW)
    snap = s.snapshot()
    r = ingest_event(s, creds, body(ownerId=creds.owner_id, eid="2" * 32), NOW)
    assert r == Result(403, {"error": "forbidden"})
    assert s.snapshot() == snap


def test_forbidden_even_when_also_duplicate():
    s = InMemoryStore()
    ingest_event(s, CREDS, body(), NOW)
    snap = s.snapshot()
    r = ingest_event(s, Credentials("tejaswi", "b" * 64), body(), NOW)
    assert r.status == 403 and s.snapshot() == snap


def test_verifier_replaced_mid_flight_forbidden_no_last_seen():
    s = SwapVerifierStore()
    s.create_agent_if_absent(new_record("bot", CREDS, EMPTY_CONFIG))
    r = ingest_event(s, CREDS, body(), NOW)
    assert r == Result(403, {"error": "forbidden"})
    meta = s.items[("bot", META_SK)]
    assert "lastSeen" not in meta and "firstSeen" not in meta
    assert meta["totalSpendUsd"] == 0.0


def test_resubmission_is_duplicate_no_spend_change():
    s = InMemoryStore()
    first = ingest_event(s, CREDS, body(), NOW)
    spend = s.get_agent("bot").total_spend_usd
    again = ingest_event(s, CREDS, body(), NOW)
    assert again == Result(200, {"eventId": "0" * 32, "costUsd": first.body["costUsd"], "duplicate": True})
    assert s.get_agent("bot").total_spend_usd == spend
    assert sum(1 for (_, sk) in s.items if sk != META_SK) == 1


def test_unreported_agent_keeps_config_and_gets_seen_times():
    s = InMemoryStore()
    cfg = GuardrailConfig(2.0, (".env",))
    s.create_agent_if_absent(new_record("bot", CREDS, cfg))
    assert ingest_event(s, CREDS, body(type_="tool_call"), NOW).status == 200
    rec = s.get_agent("bot")
    assert rec.guardrails == cfg
    assert rec.first_seen == rec.last_seen == TS


def test_last_seen_keeps_later_ts_out_of_order():
    s = InMemoryStore()
    ingest_event(s, CREDS, body(eid="1" * 32, ts="2026-10-08T10:00:00.000Z"), NOW)
    ingest_event(s, CREDS, body(eid="2" * 32, ts="2026-10-08T09:00:00.000Z"), NOW)
    rec = s.get_agent("bot")
    assert rec.last_seen == "2026-10-08T10:00:00.000Z"
    assert rec.first_seen == "2026-10-08T10:00:00.000Z"  # first to arrive, not earliest
    ingest_event(s, CREDS, body(eid="3" * 32, ts="2026-10-08T11:00:00.000Z"), NOW)
    assert s.get_agent("bot").last_seen == "2026-10-08T11:00:00.000Z"
