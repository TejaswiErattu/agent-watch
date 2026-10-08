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


# ---- 1.9 event writes ----

from datetime import datetime, timezone  # noqa: E402

from agentwatch_api.validation import validate_event  # noqa: E402

NOW = datetime(2026, 10, 8, 12, tzinfo=timezone.utc)


def ev(ts="2026-10-08T10:00:00.000Z", eid="0" * 32, type_="llm_call", **over):
    body = {"agentId": "bot", "ownerId": "tejaswi", "ts": ts, "eventId": eid, "type": type_}
    if type_ == "llm_call":
        body |= {"model": "claude-haiku-4-5", "inputTokens": 10, "outputTokens": 5}
    elif type_ == "tool_call":
        body |= {"tool": "read_file", "target": "x"}
    else:
        body |= {"violationType": "blocked_path", "attemptedPath": ".env"}
    body |= over
    e = validate_event(body, NOW)
    assert not isinstance(e, Exception), e
    return e


def store_with_agent():
    s = InMemoryStore()
    s.create_agent_if_absent(rec())
    return s


def test_record_event_stored_updates_record():
    s = store_with_agent()
    assert s.record_event(ev(), 0.25, KV) == "stored"
    r = s.get_agent("bot")
    assert r.total_spend_usd == 0.25
    assert r.first_seen == "2026-10-08T10:00:00.000Z"
    assert r.model == "claude-haiku-4-5"
    item = s.items[("bot", event_sk("2026-10-08T10:00:00.000Z", "0" * 32))]
    assert item["costUsd"] == 0.25
    assert item["type"] == "llm_call"


def test_first_seen_kept_once_set():
    s = store_with_agent()
    s.record_event(ev(ts="2026-10-08T10:00:00.000Z", eid="1" * 32), 0.0, KV)
    s.record_event(ev(ts="2026-10-08T09:00:00.000Z", eid="2" * 32), 0.0, KV)
    assert s.get_agent("bot").first_seen == "2026-10-08T10:00:00.000Z"


def test_model_only_set_by_llm_call():
    s = store_with_agent()
    s.record_event(ev(type_="tool_call"), 0.0, KV)
    assert s.get_agent("bot").model is None
    s.record_event(ev(eid="1" * 32), 0.0, KV)
    s.record_event(ev(eid="2" * 32, model="claude-haiku-4-5-20251001"), 0.0, KV)
    assert s.get_agent("bot").model == "claude-haiku-4-5-20251001"


def test_duplicate_sk_no_cost_change():
    s = store_with_agent()
    assert s.record_event(ev(), 0.25, KV) == "stored"
    snap = s.snapshot()
    assert s.record_event(ev(), 0.25, KV) == "duplicate"
    assert s.snapshot() == snap


def test_forbidden_wins_over_duplicate():
    s = store_with_agent()
    s.record_event(ev(), 0.25, KV)
    snap = s.snapshot()
    assert s.record_event(ev(), 0.25, OTHER_KV) == "forbidden"
    assert s.snapshot() == snap


def test_forbidden_writes_nothing():
    s = store_with_agent()
    snap = s.snapshot()
    assert s.record_event(ev(), 0.25, OTHER_KV) == "forbidden"
    assert s.snapshot() == snap


def test_record_event_missing_agent_forbidden():
    # The Update's keyVerifier condition fails on a missing item.
    s = InMemoryStore()
    assert s.record_event(ev(), 0.1, KV) == "forbidden"
    assert s.items == {}


def test_event_items_have_no_secrets_or_gsi_key():
    s = store_with_agent()
    for i, t in enumerate(["llm_call", "tool_call", "blocked"]):
        s.record_event(ev(eid=str(i) * 32, type_=t), 0.0, KV)
    for (aid, sk), item in s.items.items():
        if sk != META_SK:
            assert "keyVerifier" not in item
            assert "gsiOwnerId" not in item


def test_bump_last_seen_keeps_later():
    s = store_with_agent()
    s.bump_last_seen("bot", "2026-10-08T10:00:00.000Z")
    assert s.get_agent("bot").last_seen == "2026-10-08T10:00:00.000Z"
    s.bump_last_seen("bot", "2026-10-08T09:00:00.000Z")
    assert s.get_agent("bot").last_seen == "2026-10-08T10:00:00.000Z"
    s.bump_last_seen("bot", "2026-10-08T11:00:00.000Z")
    assert s.get_agent("bot").last_seen == "2026-10-08T11:00:00.000Z"


def test_bump_last_seen_missing_agent_noop():
    s = InMemoryStore()
    s.bump_last_seen("ghost", "2026-10-08T10:00:00.000Z")
    assert s.items == {}
