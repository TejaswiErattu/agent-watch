"""Local_Spend_Total: init fetch, post-call accumulation, 60 s server sync (task 6.2)."""

import logging

import agentwatch
from agentwatch.client import Response, TransportError
from agentwatch.pricing import cost_from_table
from fakes import FakeAnthropic, FakeBedrock, FakeTransport, spend_body

PRICING = {"models": {"m": {"inputPerMTokUsd": 3.0, "outputPerMTokUsd": 15.0}}}
CFG = Response(200, {"guardrails": {"dailySpendCapUsd": None, "blockedPaths": []}, "pricing": PRICING})


def make(spend_outcomes=None, now=None):
    now = now if now is not None else [0.0]
    t = FakeTransport([CFG], spend_outcomes=spend_outcomes)
    aw = agentwatch.init("bot", "tejaswi", "sk-key", endpoint="https://x", transport=t,
                         clock=lambda: now[0], sleep=lambda s: None)
    return aw, t, now


def test_init_fetches_spend_and_sets_local_total():
    aw, t, _ = make([Response(200, spend_body(0.42))])
    assert len(t.spend_requests) == 1
    req = t.spend_requests[0]
    assert req["method"] == "GET" and req["url"] == "https://x/agents/bot/spend"
    assert req["timeout"] == 2.0
    assert aw.local_spend == 0.42


def test_failing_first_fetch_starts_at_zero_and_warns(caplog):
    caplog.set_level(logging.WARNING, logger="agentwatch")
    aw, _, _ = make([TransportError("Timeout")])
    assert aw.local_spend == 0.0
    assert "spend sync failed" in caplog.text


def test_malformed_spend_responses_count_as_failures():
    for bad in (Response(500, None), Response(200, {}), Response(200, {"rollingSpendUsd": True}),
                Response(200, {"rollingSpendUsd": -1}), Response(200, {"rollingSpendUsd": "1"}),
                Response(200, {"rollingSpendUsd": float("nan")}), Response(403, {"error": "forbidden"})):
        aw, _, _ = make([bad])
        assert aw.local_spend == 0.0, bad


def test_completed_llm_calls_add_actual_cost():
    aw, _, _ = make([Response(200, spend_body(0.1))])
    aw.wrap(FakeBedrock(in_tok=1000, out_tok=200)).converse(modelId="m", messages=[])
    aw.wrap(FakeAnthropic(in_tok=10, out_tok=5)).messages.create(model="m", messages=[], max_tokens=5)
    expected = 0.1 + cost_from_table(PRICING, "m", 1000, 200) + cost_from_table(PRICING, "m", 10, 5)
    assert abs(aw.local_spend - expected) < 1e-12


def test_failed_provider_call_adds_nothing():
    aw, _, _ = make()
    try:
        aw.wrap(FakeBedrock(error=RuntimeError("throttled"))).converse(modelId="m", messages=[])
    except RuntimeError:
        pass
    assert aw.local_spend == 0.0


def test_sync_only_after_interval_and_success_replaces():
    aw, t, now = make([Response(200, spend_body(0.1)), Response(200, spend_body(0.9))])
    aw.wrap(FakeBedrock(in_tok=1000, out_tok=0)).converse(modelId="m", messages=[])
    now[0] = 59.9
    aw._maybe_sync_spend()
    assert len(t.spend_requests) == 1  # too soon
    now[0] = 60.0
    aw._maybe_sync_spend()
    assert len(t.spend_requests) == 2
    assert aw.local_spend == 0.9  # replaced, not added


def test_failed_or_slow_sync_keeps_value_and_warns(caplog):
    aw, t, now = make([Response(200, spend_body(0.3)), TransportError("Timeout"), Response(500, None)])
    caplog.set_level(logging.WARNING, logger="agentwatch")
    for step in (60.0, 120.0):
        now[0] = step
        caplog.clear()
        aw._maybe_sync_spend()
        assert aw.local_spend == 0.3
        assert "spend sync failed" in caplog.text
    assert len(t.spend_requests) == 3
