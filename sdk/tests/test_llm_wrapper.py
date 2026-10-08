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
