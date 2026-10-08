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
