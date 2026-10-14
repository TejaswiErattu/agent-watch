"""Property 30: pause decision and once-per-episode reporting."""

from hypothesis import given, settings
from hypothesis import strategies as st

import agentwatch
from agentwatch import AgentPaused
from agentwatch.client import CONTROL_INTERVAL_S, Response, TransportError
from fakes import FakeBedrock, FakeTransport, status_body

EP = "https://api.example.com"
CFG = Response(200, {"guardrails": {"dailySpendCapUsd": None, "blockedPaths": []}, "pricing": {"models": {}}})

# A status outcome: True/False = valid response; a string = one kind of failure (state kept).
outcome = st.one_of(
    st.booleans(),
    st.sampled_from(["net", "500", "malformed", "str"]),
)


def to_response(o):
    if o is True or o is False:
        return Response(200, status_body(o))
    if o == "net":
        return TransportError("down")
    if o == "500":
        return Response(500, None)
    if o == "malformed":
        return Response(200, {"agentId": "bot"})
    return Response(200, {"paused": "true"})


step = st.tuples(st.floats(min_value=0.0, max_value=12.0, allow_nan=False),  # clock advance
                 st.sampled_from(["llm", "tool"]))


class Clock:
    def __init__(self):
        self.t = 1000.0

    def __call__(self):
        return self.t


# Feature: agent-watch-v2, Property 30: Pause decision and once-per-episode reporting
@settings(max_examples=100, deadline=None)
@given(init_outcome=outcome, outcomes=st.lists(outcome, max_size=30), steps=st.lists(step, max_size=30))
def test_pause_decision_and_once_per_episode(init_outcome, outcomes, steps):
    clock = Clock()
    t = FakeTransport([CFG], status_outcomes=[to_response(init_outcome)] + [to_response(o) for o in outcomes],
                      status_default=Response(500, None))
    aw = agentwatch.init("bot", "tejaswi", "sk-key", endpoint=EP, transport=t, clock=clock,
                         sleep=lambda s: None)
    raw = FakeBedrock()
    llm = aw.wrap(raw)
    tool_runs = []

    @aw.tool
    def act(x):
        tool_runs.append(x)

    # Model of the expected behavior.
    queue = [init_outcome] + list(outcomes)
    last_attempt = clock.t
    attempts = 1
    model_paused = init_outcome is True
    reported = False
    want_events = 0
    want_provider = 0
    want_tool = 0

    for advance, kind in steps:
        clock.t += advance
        if clock.t - last_attempt >= CONTROL_INTERVAL_S:
            last_attempt = clock.t
            o = queue[attempts] if attempts < len(queue) else "500"
            attempts += 1
            if o is True or o is False:
                model_paused = o
                if not o:
                    reported = False
        try:
            if kind == "llm":
                llm.converse(modelId="m", messages=[])
            else:
                act(1)
            raised = False
        except AgentPaused:
            raised = True
        assert raised == model_paused
        assert aw.paused == model_paused
        if model_paused:
            if not reported:
                reported = True
                want_events += 1
        elif kind == "llm":
            want_provider += 1
        else:
            want_tool += 1

    assert len(t.status_requests) == attempts
    assert len(raw.calls) == want_provider
    assert len(tool_runs) == want_tool
    aw._sender.flush(5)
    paused_events = [r for r in t.requests if r["url"].endswith("/events") and r["json"]["type"] == "blocked"]
    assert len(paused_events) == want_events
    assert all(r["json"]["violationType"] == "paused" for r in paused_events)
