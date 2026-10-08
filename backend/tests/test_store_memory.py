import pytest

from agentwatch_api.rules import EMPTY_CONFIG, GuardrailConfig
from agentwatch_api.store import META_SK, AgentRecord, InMemoryStore, Store, event_sk

KV = "a" * 64
OTHER_KV = "b" * 64


def rec(agent_id="bot", owner="tejaswi", kv=KV, cfg=EMPTY_CONFIG):
    return AgentRecord(agent_id=agent_id, owner_id=owner, key_verifier=kv, guardrails=cfg)


def test_event_sk_and_meta():
    assert event_sk("2026-10-08T00:00:00.000Z", "ab" * 16) == "2026-10-08T00:00:00.000Z#" + "ab" * 16
    assert META_SK == "META"
    # Event SKs start with a digit, so META sorts after every event.
    assert event_sk("9999-12-31T23:59:59.999Z", "f" * 32) < META_SK


def test_in_memory_store_satisfies_protocol():
    assert isinstance(InMemoryStore(), Store)


def test_new_record_defaults():
    r = rec()
    assert r.first_seen is None and r.last_seen is None and r.model is None
    assert r.total_spend_usd == 0.0


def test_get_agent_unknown_is_none():
    assert InMemoryStore().get_agent("nope") is None


def test_create_agent_if_absent_once():
    s = InMemoryStore()
    assert s.create_agent_if_absent(rec()) is True
    assert s.create_agent_if_absent(rec(owner="intruder", kv=OTHER_KV)) is False
    got = s.get_agent("bot")
    assert got.owner_id == "tejaswi" and got.key_verifier == KV


def test_get_agent_returns_a_copy():
    s = InMemoryStore()
    s.create_agent_if_absent(rec())
    s.get_agent("bot").total_spend_usd = 99.0
    assert s.get_agent("bot").total_spend_usd == 0.0


def test_put_config_with_matching_verifier():
    s = InMemoryStore()
    s.create_agent_if_absent(rec())
    cfg = GuardrailConfig(1.0, (".env",))
    assert s.put_config("bot", cfg, KV) is True
    assert s.get_agent("bot").guardrails == cfg


def test_put_config_wrong_verifier_changes_nothing():
    s = InMemoryStore()
    s.create_agent_if_absent(rec())
    before = s.get_agent("bot")
    assert s.put_config("bot", GuardrailConfig(1.0, (".env",)), OTHER_KV) is False
    assert s.get_agent("bot") == before


def test_put_config_missing_agent_false():
    assert InMemoryStore().put_config("ghost", EMPTY_CONFIG, KV) is False


def test_meta_items_carry_gsi_owner_and_verifier():
    s = InMemoryStore()
    s.create_agent_if_absent(rec())
    item = s.items[("bot", META_SK)]
    assert item["gsiOwnerId"] == "tejaswi"
    assert item["keyVerifier"] == KV
