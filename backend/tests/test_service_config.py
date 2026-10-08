import pytest

from agentwatch_api.auth import Credentials
from agentwatch_api.pricing import pricing_table
from agentwatch_api.rules import EMPTY_CONFIG, GuardrailConfig, to_json
from agentwatch_api.service import Result, get_config, new_record
from agentwatch_api.store import InMemoryStore

H = "a" * 64
CREDS = Credentials("tejaswi", H)
CFG = GuardrailConfig(1.5, (".env", "~/.ssh"))


def seeded(cfg=CFG):
    s = InMemoryStore()
    s.create_agent_if_absent(new_record("bot", CREDS, cfg))
    return s


def test_get_config_returns_stored_guardrails_and_pricing():
    r = get_config(seeded(), CREDS, "bot")
    assert r == Result(200, {"guardrails": to_json(CFG), "pricing": pricing_table()})


def test_get_config_missing_record_is_empty_and_creates_nothing():
    s = InMemoryStore()
    r = get_config(s, CREDS, "ghost")
    assert r == Result(200, {"guardrails": to_json(EMPTY_CONFIG), "pricing": pricing_table()})
    assert s.items == {}


@pytest.mark.parametrize("creds", [Credentials("someone", H), Credentials("tejaswi", "b" * 64)])
def test_get_config_mismatch_forbidden(creds):
    s = seeded()
    snap = s.snapshot()
    assert get_config(s, creds, "bot") == Result(403, {"error": "forbidden"})
    assert s.snapshot() == snap


def test_get_config_bad_agent_id_400():
    r = get_config(InMemoryStore(), CREDS, "has space")
    assert r.status == 400 and "agentId" in r.body["error"]


# ---- 2.5 put_config ----

from agentwatch_api.service import put_config  # noqa: E402

NEW = GuardrailConfig(None, (".env",))


class RacingStore(InMemoryStore):
    """create_agent_if_absent loses to a record created by `racer` just before it."""

    def __init__(self, racer):
        super().__init__()
        self.racer = racer

    def create_agent_if_absent(self, record):
        super().create_agent_if_absent(new_record(record.agent_id, self.racer, EMPTY_CONFIG))
        return super().create_agent_if_absent(record)


def test_put_config_replaces_existing():
    s = seeded()
    r = put_config(s, CREDS, "bot", to_json(NEW))
    assert r == Result(200, {"guardrails": to_json(NEW)})
    assert s.get_agent("bot").guardrails == NEW


def test_put_config_missing_record_creates_unreported_agent():
    s = InMemoryStore()
    assert put_config(s, CREDS, "bot", to_json(NEW)).status == 200
    rec = s.get_agent("bot")
    assert rec.guardrails == NEW and rec.owner_id == "tejaswi"
    assert rec.first_seen is None and rec.last_seen is None and rec.model is None
    assert rec.total_spend_usd == 0.0


def test_put_config_lost_race_same_owner_applies_config():
    s = RacingStore(CREDS)
    assert put_config(s, CREDS, "bot", to_json(NEW)) == Result(200, {"guardrails": to_json(NEW)})
    assert s.get_agent("bot").guardrails == NEW


def test_put_config_lost_race_other_owner_forbidden():
    s = RacingStore(Credentials("intruder", "b" * 64))
    assert put_config(s, CREDS, "bot", to_json(NEW)) == Result(403, {"error": "forbidden"})
    assert s.get_agent("bot").guardrails == EMPTY_CONFIG


@pytest.mark.parametrize("creds", [Credentials("someone", H), Credentials("tejaswi", "b" * 64)])
def test_put_config_mismatch_forbidden_and_unchanged(creds):
    s = seeded()
    snap = s.snapshot()
    assert put_config(s, creds, "bot", to_json(NEW)) == Result(403, {"error": "forbidden"})
    assert s.snapshot() == snap


def test_put_config_verifier_replaced_mid_flight_forbidden():
    class Swap(InMemoryStore):
        def put_config(self, agent_id, cfg, key_verifier):
            self.items[(agent_id, "META")]["keyVerifier"] = "c" * 64
            return super().put_config(agent_id, cfg, key_verifier)

    s = Swap()
    s.create_agent_if_absent(new_record("bot", CREDS, CFG))
    assert put_config(s, CREDS, "bot", to_json(NEW)).status == 403
    assert s.get_agent("bot").guardrails == CFG


@pytest.mark.parametrize(
    "body,field",
    [
        ({"dailySpendCapUsd": -1, "blockedPaths": []}, "dailySpendCapUsd"),
        ({"dailySpendCapUsd": None, "blockedPaths": [""]}, "blockedPaths"),
        ({"dailySpendCapUsd": None}, "blockedPaths"),
        ([], "body"),
    ],
)
def test_put_config_invalid_body_400_no_side_effects(body, field):
    s = InMemoryStore()
    r = put_config(s, CREDS, "bot", body)
    assert r.status == 400 and field in r.body["error"]
    assert s.items == {}


def test_put_config_bad_agent_id_400():
    s = InMemoryStore()
    r = put_config(s, CREDS, "has space", to_json(NEW))
    assert r.status == 400 and "agentId" in r.body["error"]
    assert s.items == {}
