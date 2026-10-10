import json

import pytest

import agentwatch
from agentwatch.client import Response
from fakes import FakeAnthropic, FakeBedrock, FakeTransport

PROMPT = "What is the secret recipe for the dining hall soup?"
MSGS_ANTHROPIC = [{"role": "user", "content": PROMPT}]
MSGS_BEDROCK = [{"role": "user", "content": [{"text": PROMPT}]}]


def make():
    cfg = Response(200, {"guardrails": {"dailySpendCapUsd": None, "blockedPaths": []},
                         "pricing": {"models": {}}})
    t = FakeTransport([cfg])
    aw = agentwatch.init("bot", "tejaswi", "sk-key", endpoint="https://x", transport=t,
                         clock=lambda: 0.0, sleep=lambda s: None)
    return aw, t


def events(aw, t):
    aw._sender.flush(5)
    return [r["json"] for r in t.requests if r["url"].endswith("/events")]


def test_wrap_detects_bedrock_and_records_llm_call():
    aw, t = make()
    raw = FakeBedrock(in_tok=120, out_tok=30, stop="max_tokens")
    client = aw.wrap(raw)
    out = client.converse(modelId="us.anthropic.claude-haiku-4-5-20251001-v1:0", messages=MSGS_BEDROCK,
                          system=[{"text": "be brief"}], inferenceConfig={"maxTokens": 256})
    assert out["usage"]["inputTokens"] == 120 and len(raw.calls) == 1
    (e,) = events(aw, t)
    assert e["type"] == "llm_call" and e["model"] == "us.anthropic.claude-haiku-4-5-20251001-v1:0"
    assert (e["inputTokens"], e["outputTokens"]) == (120, 30)
    m = e["meta"]
    assert set(m) == {"provider", "messageCount", "promptChars", "maxTokens", "stopReason", "latencyMs"}
    assert m["provider"] == "bedrock" and m["messageCount"] == 1 and m["maxTokens"] == 256
    assert m["stopReason"] == "max_tokens" and m["promptChars"] == len(PROMPT) + len("be brief")
    assert isinstance(m["latencyMs"], int) and m["latencyMs"] >= 0


def test_wrap_detects_anthropic_and_records_llm_call():
    aw, t = make()
    raw = FakeAnthropic(in_tok=7, out_tok=9)
    client = aw.wrap(raw)
    msg = client.messages.create(model="claude-haiku-4-5", max_tokens=100, system="sys",
                                 messages=MSGS_ANTHROPIC)
    assert msg.usage.input_tokens == 7
    (e,) = events(aw, t)
    assert e["model"] == "claude-haiku-4-5" and (e["inputTokens"], e["outputTokens"]) == (7, 9)
    m = e["meta"]
    assert m["provider"] == "anthropic" and m["maxTokens"] == 100 and m["stopReason"] == "end_turn"
    assert m["promptChars"] == len(PROMPT) + len("sys")


def test_anthropic_block_list_content_counts_text_chars():
    aw, t = make()
    client = aw.wrap(FakeAnthropic())
    client.messages.create(model="m", max_tokens=10, messages=[
        {"role": "user", "content": [{"type": "text", "text": "abc"}, {"type": "image", "source": {}}]}])
    (e,) = events(aw, t)
    assert e["meta"]["promptChars"] == 3


def test_other_attributes_pass_through():
    aw, _ = make()
    b = aw.wrap(FakeBedrock())
    a = aw.wrap(FakeAnthropic())
    assert b.region_name == "us-west-2"
    assert a.messages.count_tokens() == "passthrough"


def test_no_prompt_text_in_event():
    aw, t = make()
    aw.wrap(FakeAnthropic()).messages.create(model="m", max_tokens=10, messages=MSGS_ANTHROPIC)
    aw.wrap(FakeBedrock()).converse(modelId="m", messages=MSGS_BEDROCK)
    for e in events(aw, t):
        assert PROMPT not in json.dumps(e)


@pytest.mark.parametrize("factory,call", [
    (lambda: FakeBedrock(error=RuntimeError("throttled")),
     lambda c: c.converse(modelId="m", messages=MSGS_BEDROCK)),
    (lambda: FakeAnthropic(error=RuntimeError("overloaded")),
     lambda c: c.messages.create(model="m", max_tokens=1, messages=MSGS_ANTHROPIC)),
])
def test_provider_exception_propagates_with_no_event(factory, call):
    aw, t = make()
    with pytest.raises(RuntimeError):
        call(aw.wrap(factory()))
    assert events(aw, t) == []


def test_bedrock_without_max_tokens_reports_null():
    aw, t = make()
    aw.wrap(FakeBedrock()).converse(modelId="m", messages=MSGS_BEDROCK)
    (e,) = events(aw, t)
    assert e["meta"]["maxTokens"] is None


def test_wrap_rejects_unknown_client():
    aw, _ = make()
    with pytest.raises(TypeError, match="Bedrock|Anthropic"):
        aw.wrap(object())


# ---- 6.4: spend cap enforcement ----

from agentwatch import SpendCapExceeded  # noqa: E402
from agentwatch.pricing import estimate_pending_cost  # noqa: E402
from fakes import spend_body  # noqa: E402

PRICED = {"models": {"m": {"inputPerMTokUsd": 3.0, "outputPerMTokUsd": 15.0}}}


def make_capped(cap, spent=0.0):
    cfg = Response(200, {"guardrails": {"dailySpendCapUsd": cap, "blockedPaths": []}, "pricing": PRICED})
    t = FakeTransport([cfg], spend_outcomes=[Response(200, spend_body(spent))])
    aw = agentwatch.init("bot", "tejaswi", "sk-key", endpoint="https://x", transport=t,
                         clock=lambda: 0.0, sleep=lambda s: None)
    return aw, t


def blocked_events(t):
    return [r["json"] for r in t.requests if r["url"].endswith("/events") and r["json"]["type"] == "blocked"]


@pytest.mark.parametrize("provider", ["bedrock", "anthropic"])
def test_over_cap_raises_never_calls_client_and_reports_sync(provider):
    aw, t = make_capped(cap=0.01, spent=0.0099)
    if provider == "bedrock":
        raw = FakeBedrock()
        req = {"modelId": "m", "messages": MSGS_BEDROCK, "inferenceConfig": {"maxTokens": 1000}}
        call = lambda: aw.wrap(raw).converse(**req)  # noqa: E731
        est = estimate_pending_cost(PRICED, "m", req, 1000)
    else:
        raw = FakeAnthropic()
        req = {"model": "m", "messages": MSGS_ANTHROPIC, "max_tokens": 1000}
        call = lambda: aw.wrap(raw).messages.create(**req)  # noqa: E731
        est = estimate_pending_cost(PRICED, "m", req, 1000)
    with pytest.raises(SpendCapExceeded) as ei:
        call()
    assert raw.calls == []
    # Sent synchronously, before the raise: no flush needed.
    (b,) = blocked_events(t)
    assert b["violationType"] == "spend_cap" and b["attemptedCostUsd"] == est
    assert ei.value.violation_type == "spend_cap"
    assert aw.local_spend == 0.0099  # a blocked call adds nothing


def test_at_cap_proceeds():
    req = {"model": "m", "messages": MSGS_ANTHROPIC, "max_tokens": 100}
    est = estimate_pending_cost(PRICED, "m", req, 100)
    aw, t = make_capped(cap=0.5, spent=0.5 - est)
    raw = FakeAnthropic(in_tok=1, out_tok=1)
    aw.wrap(raw).messages.create(**req)
    assert len(raw.calls) == 1 and blocked_events(t) == []


def test_no_cap_always_proceeds():
    aw, t = make_capped(cap=None, spent=1e6)
    raw = FakeBedrock()
    aw.wrap(raw).converse(modelId="m", messages=MSGS_BEDROCK)
    assert len(raw.calls) == 1 and blocked_events(t) == []


def test_check_runs_before_every_call_and_accumulated_spend_trips_it():
    # The estimate is tiny (empty messages, maxTokens 0) so the first call is allowed, but its
    # actual cost is 1000 * 3 / 1e6 = 0.003 > cap 0.002, so the second call is blocked.
    aw, t = make_capped(cap=0.002)
    raw = FakeBedrock(in_tok=1000, out_tok=0)
    c = aw.wrap(raw)
    req = {"modelId": "m", "messages": [], "inferenceConfig": {"maxTokens": 0}}
    c.converse(**req)
    with pytest.raises(SpendCapExceeded):
        c.converse(**req)
    assert len(raw.calls) == 1


def test_block_still_raises_when_reporting_fails():
    from agentwatch.client import TransportError
    aw, t = make_capped(cap=0.0, spent=1.0)
    t.outcomes = [TransportError("down")] * 4
    with pytest.raises(SpendCapExceeded):
        aw.wrap(FakeBedrock()).converse(modelId="m", messages=MSGS_BEDROCK)
