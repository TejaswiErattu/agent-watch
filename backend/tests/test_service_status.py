"""Unit tests for get_status / parse_status / put_status (task 8.1, Req 27.1-27.7)."""

from datetime import datetime, timezone

import pytest

from agentwatch_api.auth import Credentials
from agentwatch_api.rules import EMPTY_CONFIG, GuardrailConfig
from agentwatch_api.service import Result, get_status, list_inventory, new_record, put_status
from agentwatch_api.store import InMemoryStore

H = "a" * 64
CREDS = Credentials("tejaswi", H)
CFG = GuardrailConfig(1.5, (".env",))
NOW = datetime(2026, 10, 14, 18, 2, 11, 123987, tzinfo=timezone.utc)
NOW_TS = "2026-10-14T18:02:11.123Z"  # floored to ms


def seeded(cfg=CFG):
    s = InMemoryStore()
    s.create_agent_if_absent(new_record("bot", CREDS, cfg))
    return s


def test_get_status_missing_agent_is_not_paused_and_creates_nothing():
    s = InMemoryStore()
    r = get_status(s, CREDS, "ghost")
    assert r == Result(200, {"agentId": "ghost", "paused": False, "pausedAt": None})
    assert s.items == {}


def test_get_status_existing_agent_defaults_to_not_paused():
    r = get_status(seeded(), CREDS, "bot")
    assert r == Result(200, {"agentId": "bot", "paused": False, "pausedAt": None})


def test_put_status_missing_agent_creates_record_with_empty_config_and_state():
    s = InMemoryStore()
    r = put_status(s, CREDS, "bot", {"paused": True}, NOW)
    assert r == Result(200, {"agentId": "bot", "paused": True, "pausedAt": NOW_TS})
    rec = s.get_agent("bot")
    assert rec.guardrails == EMPTY_CONFIG and rec.owner_id == "tejaswi"
    assert rec.first_seen is None and rec.last_seen is None
    assert rec.paused is True and rec.paused_at == NOW_TS


def test_put_then_get_round_trip_and_resume_clears_paused_at():
    s = seeded()
    assert put_status(s, CREDS, "bot", {"paused": True}, NOW).body["pausedAt"] == NOW_TS
    assert get_status(s, CREDS, "bot").body == {"agentId": "bot", "paused": True, "pausedAt": NOW_TS}
    r = put_status(s, CREDS, "bot", {"paused": False}, NOW)
    assert r.body == {"agentId": "bot", "paused": False, "pausedAt": None}
    assert get_status(s, CREDS, "bot").body == {"agentId": "bot", "paused": False, "pausedAt": None}
    assert s.get_agent("bot").guardrails == CFG


def test_inventory_mirrors_paused():
    s = seeded()
    put_status(s, CREDS, "bot", {"paused": True}, NOW)
    (item,) = list_inventory(s, CREDS).body["agents"]
    assert item["paused"] is True


@pytest.mark.parametrize("creds", [Credentials("someone", H), Credentials("tejaswi", "b" * 64)])
def test_wrong_credentials_403_and_unchanged(creds):
    s = seeded()
    snap = s.snapshot()
    assert put_status(s, creds, "bot", {"paused": True}, NOW) == Result(403, {"error": "forbidden"})
    assert get_status(s, creds, "bot") == Result(403, {"error": "forbidden"})
    assert s.snapshot() == snap


def test_verifier_replaced_mid_flight_403():
    class Swap(InMemoryStore):
        def set_paused(self, agent_id, paused, paused_at, key_verifier):
            self.items[(agent_id, "META")]["keyVerifier"] = "c" * 64
            return super().set_paused(agent_id, paused, paused_at, key_verifier)

    s = Swap()
    s.create_agent_if_absent(new_record("bot", CREDS, CFG))
    assert put_status(s, CREDS, "bot", {"paused": True}, NOW).status == 403
    assert s.get_agent("bot").paused is False


@pytest.mark.parametrize(
    "body", [{}, {"paused": "yes"}, {"paused": 1}, {"paused": True, "x": 1}, [], None, "true"]
)
def test_bad_bodies_400_naming_field_and_no_side_effects(body):
    s = seeded()
    snap = s.snapshot()
    r = put_status(s, CREDS, "bot", body, NOW)
    assert r.status == 400 and "paused" in r.body["error"]
    assert s.snapshot() == snap
    empty = InMemoryStore()
    assert put_status(empty, CREDS, "bot", body, NOW).status == 400
    assert empty.items == {}


def test_bad_agent_id_400():
    s = InMemoryStore()
    assert get_status(s, CREDS, "has space").status == 400
    r = put_status(s, CREDS, "has space", {"paused": True}, NOW)
    assert r.status == 400 and "agentId" in r.body["error"]
    assert s.items == {}
