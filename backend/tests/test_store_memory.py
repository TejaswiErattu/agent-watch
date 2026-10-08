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


# ---- 1.10 event and owner queries ----


def seeded(n=5):
    """Agent with n events at minutes 0..n-1, alternating llm_call / tool_call, cost = 0.01 * (i+1)."""
    s = store_with_agent()
    for i in range(n):
        t = "llm_call" if i % 2 == 0 else "tool_call"
        s.record_event(ev(ts=f"2026-10-08T10:0{i}:00.000Z", eid=f"{i:032x}", type_=t), 0.01 * (i + 1), KV)
    return s


def sks(items):
    return [i["sk"] for i in items]


def test_query_events_ascending_and_descending():
    s = seeded()
    asc, _ = s.query_events("bot", ascending=True, limit=50)
    desc, _ = s.query_events("bot", ascending=False, limit=50)
    assert sks(asc) == sorted(sks(asc))
    assert len(asc) == 5
    assert sks(desc) == list(reversed(sks(asc)))


def test_query_events_excludes_meta():
    items, _ = seeded().query_events("bot")
    assert all(i["sk"] != META_SK for i in items)


def test_query_events_limit_and_pagination():
    s = seeded()
    page1, cur = s.query_events("bot", limit=2)
    assert len(page1) == 2 and cur == page1[-1]["sk"]
    page2, cur = s.query_events("bot", limit=2, start_after=cur)
    page3, cur = s.query_events("bot", limit=2, start_after=cur)
    assert cur is None
    assert sks(page1 + page2 + page3) == sks(s.query_events("bot")[0])


def test_query_events_desc_pagination():
    s = seeded()
    page1, cur = s.query_events("bot", ascending=False, limit=3)
    page2, cur2 = s.query_events("bot", ascending=False, limit=3, start_after=cur)
    assert cur2 is None
    assert sks(page1 + page2) == sks(s.query_events("bot", ascending=False)[0])


def test_type_filter_applied_after_page_read():
    s = seeded()  # types: llm, tool, llm, tool, llm
    page, cur = s.query_events("bot", limit=2, type_filter="tool_call")
    # Read 2 items (llm, tool), filter leaves 1: pages can be short.
    assert [i["type"] for i in page] == ["tool_call"]
    assert cur is not None
    all_tools = []
    cur = None
    while True:
        page, cur = s.query_events("bot", limit=2, type_filter="tool_call", start_after=cur)
        all_tools += page
        if cur is None:
            break
    assert len(all_tools) == 2 and all(i["type"] == "tool_call" for i in all_tools)


def test_query_events_other_agent_isolated():
    s = seeded()
    s.create_agent_if_absent(rec(agent_id="other"))
    assert s.query_events("other") == ([], None)
    assert s.query_events("ghost") == ([], None)


def test_list_by_owner_returns_meta_records_only():
    s = seeded()
    s.create_agent_if_absent(rec(agent_id="bot2"))
    s.create_agent_if_absent(rec(agent_id="theirs", owner="someone"))
    got = sorted(r.agent_id for r in s.list_by_owner("tejaswi"))
    assert got == ["bot", "bot2"]
    assert all(isinstance(r, AgentRecord) for r in s.list_by_owner("tejaswi"))
    assert s.list_by_owner("nobody") == []


def test_sum_spend_inclusive_sk_range():
    s = seeded()  # costs 0.01..0.05 at minutes 0..4
    lo = "2026-10-08T10:01:00.000Z#"
    hi = "2026-10-08T10:03:00.000Z#g"  # 'g' sorts after any hex eventId
    assert s.sum_spend("bot", lo, hi) == pytest.approx(0.02 + 0.03 + 0.04)


def test_sum_spend_empty_and_all():
    s = seeded()
    assert s.sum_spend("bot", "2000", "2001") == 0.0
    assert s.sum_spend("ghost", "0", "9") == 0.0
    assert s.sum_spend("bot", "0", "9") == pytest.approx(0.15)


# ---- review fixes before checkpoint 1.14: match DynamoStore ----


def test_total_spend_adds_rounded_cost():
    s = store_with_agent()
    s.record_event(ev(eid="1" * 32), 0.1234567, KV)
    s.record_event(ev(eid="2" * 32), 0.0000004, KV)
    # DynamoStore ADDs Decimal(str(round(cost, 6))), so the total must use the same rounding.
    assert s.get_agent("bot").total_spend_usd == round(0.1234567, 6) + round(0.0000004, 6)


def test_query_events_exactly_full_final_page_returns_cursor():
    # DynamoDB sets LastEvaluatedKey whenever Limit is reached, even if nothing follows.
    s = seeded(4)
    page1, cur = s.query_events("bot", limit=2)
    page2, cur = s.query_events("bot", limit=2, start_after=cur)
    assert len(page2) == 2 and cur == page2[-1]["sk"]
    page3, cur = s.query_events("bot", limit=2, start_after=cur)
    assert page3 == [] and cur is None


def test_query_events_full_page_cursor_with_filter():
    s = seeded(2)  # llm, tool
    page, cur = s.query_events("bot", limit=2, type_filter="llm_call")
    assert len(page) == 1 and cur is not None


def test_agent_record_repr_hides_key_verifier():
    from agentwatch_api.rules import EMPTY_CONFIG as _E
    from agentwatch_api.store import AgentRecord as _AR

    v = "f" * 64
    rec = _AR(agent_id="bot", owner_id="tejaswi", key_verifier=v, guardrails=_E)
    assert v not in repr(rec) and "key_verifier" not in repr(rec)
