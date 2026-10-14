"""Task 8.4: pause enforced before every LLM and tool call, one event per episode (Req 27.12-27.14)."""

import pytest

import agentwatch
from agentwatch import AgentPaused, SpendCapExceeded
from agentwatch.client import CONTROL_INTERVAL_S, Response
from fakes import FakeAnthropic, FakeBedrock, FakeTransport, spend_body, status_body

EP = "https://api.example.com"
PRICED = {"models": {"m": {"inputPerMTokUsd": 3.0, "outputPerMTokUsd": 15.0}}}
MSGS = [{"role": "user", "content": "hi"}]


class Clock:
    def __init__(self, t=1000.0):
        self.t = t

    def __call__(self):
        return self.t


def make(paused=True, cap=None, spent=0.0):
    cfg = Response(200, {"guardrails": {"dailySpendCapUsd": cap, "blockedPaths": [".env"]},
                         "pricing": PRICED})
    t = FakeTransport([cfg], spend_outcomes=[Response(200, spend_body(spent))],
                      status_outcomes=[Response(200, status_body(paused))])
    clock = Clock()
    aw = agentwatch.init("bot", "tejaswi", "sk-key", endpoint=EP, transport=t, clock=clock,
                         sleep=lambda s: None)
    return aw, t, clock


def blocked(t):
    return [r["json"] for r in t.requests if r["url"].endswith("/events") and r["json"]["type"] == "blocked"]


def set_status(t, clock, paused):
    t.status_outcomes.append(Response(200, status_body(paused)))
    clock.t += CONTROL_INTERVAL_S


def test_paused_bedrock_raises_and_never_calls():
    aw, t, _ = make()
    raw = FakeBedrock()
    with pytest.raises(AgentPaused):
        aw.wrap(raw).converse(modelId="m", messages=[{"role": "user", "content": [{"text": "hi"}]}])
    assert raw.calls == []
    (e,) = blocked(t)
    assert e["violationType"] == "paused"
    assert e["meta"] == {"action": "llm_call", "model": "m"}


def test_paused_anthropic_raises_and_never_calls():
    aw, t, _ = make()
    raw = FakeAnthropic()
    with pytest.raises(AgentPaused):
        aw.wrap(raw).messages.create(model="m", max_tokens=10, messages=MSGS)
    assert raw.calls == []
    assert [e["meta"]["action"] for e in blocked(t)] == ["llm_call"]


def test_paused_tool_without_path_args_raises_and_never_runs():
    aw, t, _ = make()
    ran = []

    @aw.tool
    def add(a, b):
        ran.append((a, b))
        return a + b

    with pytest.raises(AgentPaused):
        add(1, 2)
    assert ran == []
    (e,) = blocked(t)
    assert e["meta"] == {"action": "tool_call", "tool": "add"}
    aw._sender.flush(5)
    assert not [r for r in t.requests if r["url"].endswith("/events") and r["json"]["type"] == "tool_call"]


def test_pause_checked_before_paths():
    aw, t, _ = make()

    @aw.tool
    def read_file(path):
        return "secret"

    with pytest.raises(AgentPaused):
        read_file(".env")
    assert [e["violationType"] for e in blocked(t)] == ["paused"]


def test_one_event_per_episode_and_new_event_after_resume():
    aw, t, clock = make()
    raw = FakeAnthropic()
    c = aw.wrap(raw)

    @aw.tool
    def noop():
        return 1

    for call in (lambda: c.messages.create(model="m", max_tokens=1, messages=MSGS), noop, noop):
        with pytest.raises(AgentPaused):
            call()
    assert len(blocked(t)) == 1

    set_status(t, clock, False)
    c.messages.create(model="m", max_tokens=1, messages=MSGS)
    assert noop() == 1 and len(raw.calls) == 1 and len(blocked(t)) == 1

    set_status(t, clock, True)
    for _ in range(2):
        with pytest.raises(AgentPaused):
            noop()
    assert len(blocked(t)) == 2


def test_status_still_paused_does_not_start_new_episode():
    aw, t, clock = make()

    @aw.tool
    def noop():
        return 1

    with pytest.raises(AgentPaused):
        noop()
    set_status(t, clock, True)
    with pytest.raises(AgentPaused):
        noop()
    assert len(blocked(t)) == 1


def test_pause_wins_over_spend_cap():
    aw, t, _ = make(paused=True, cap=0.0, spent=1.0)
    raw = FakeBedrock()
    with pytest.raises(AgentPaused):
        aw.wrap(raw).converse(modelId="m", messages=[])
    assert [e["violationType"] for e in blocked(t)] == ["paused"]


def test_not_paused_runs_normally_with_no_blocked_event():
    aw, t, _ = make(paused=False)
    raw = FakeBedrock()
    aw.wrap(raw).converse(modelId="m", messages=[])
    assert len(raw.calls) == 1 and blocked(t) == []
