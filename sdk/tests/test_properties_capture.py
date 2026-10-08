import re

from hypothesis import given, settings, strategies as st

import agentwatch
from agentwatch.client import Response
from fakes import FakeAnthropic, FakeBedrock, FakeTransport

TS_RE = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{3}Z$")
tok = st.integers(0, 100_000)
step = st.one_of(
    st.tuples(st.just("bedrock"), st.text(min_size=1, max_size=20), tok, tok),
    st.tuples(st.just("anthropic"), st.text(min_size=1, max_size=20), tok, tok),
    st.tuples(st.just("tool"), st.text("abcxyz_", min_size=1, max_size=10),
              st.lists(st.one_of(st.integers(), st.text(max_size=30)), max_size=4)),
)


# Feature: agent-watch, Property 18: Every wrapped call yields one well-formed event
@settings(max_examples=100, deadline=None)
@given(steps=st.lists(step, min_size=1, max_size=10))
def test_property_18_every_wrapped_call_yields_one_event(steps):
    cfg = Response(200, {"guardrails": {"dailySpendCapUsd": None, "blockedPaths": []}, "pricing": {"models": {}}})
    t = FakeTransport([cfg])
    aw = agentwatch.init("bot", "tejaswi", "sk-key", endpoint="https://x", transport=t,
                         clock=lambda: 0.0, sleep=lambda s: None)
    for s in steps:
        if s[0] == "bedrock":
            aw.wrap(FakeBedrock(s[2], s[3])).converse(modelId=s[1], messages=[])
        elif s[0] == "anthropic":
            aw.wrap(FakeAnthropic(s[2], s[3])).messages.create(model=s[1], max_tokens=1, messages=[])
        else:
            aw.tools({s[1]: lambda *a: None})[s[1]](*s[2])
    aw._sender.flush(5)
    evs = [r["json"] for r in t.requests if r["url"].endswith("/events")]

    assert len(evs) == len(steps)
    assert len({e["eventId"] for e in evs}) == len(evs)
    for s, e in zip(steps, evs):
        assert e["agentId"] == "bot" and e["ownerId"] == "tejaswi" and TS_RE.match(e["ts"])
        if s[0] == "tool":
            assert e["type"] == "tool_call" and e["tool"] == s[1] and isinstance(e["target"], str)
            assert isinstance(e["meta"]["args"], list)
        else:
            assert e["type"] == "llm_call" and e["model"] == s[1]
            assert (e["inputTokens"], e["outputTokens"]) == (s[2], s[3])
