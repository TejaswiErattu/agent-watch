import math

from hypothesis import given, settings, strategies as st

import agentwatch
from agentwatch.client import Response, TransportError
from agentwatch.pricing import cost_from_table
from fakes import FakeAnthropic, FakeBedrock, FakeTransport, spend_body

pricing = st.fixed_dictionaries({"models": st.dictionaries(
    st.sampled_from(["a", "b"]),
    st.fixed_dictionaries({"inputPerMTokUsd": st.floats(0, 100), "outputPerMTokUsd": st.floats(0, 100)}),
    max_size=2)})
initial = st.one_of(st.floats(0, 50, allow_nan=False).map(lambda v: ("ok", v)),
                    st.sampled_from([("net", None), ("500", None)]))
calls = st.lists(st.tuples(st.sampled_from(["bedrock", "anthropic"]), st.sampled_from(["a", "b", "zz"]),
                           st.integers(0, 50_000), st.integers(0, 50_000)), max_size=10)


def _spend_resp(kind, v):
    return {"ok": lambda: Response(200, spend_body(v)), "net": lambda: TransportError("x"),
            "500": lambda: Response(500, None)}[kind]()


# Feature: agent-watch, Property 22: Local spend accounting
@settings(max_examples=100, deadline=None)
@given(table=pricing, init=initial, steps=calls, fail_sync=st.booleans())
def test_property_22_local_spend_accounting(table, init, steps, fail_sync):
    cfg = Response(200, {"guardrails": {"dailySpendCapUsd": None, "blockedPaths": []}, "pricing": table})
    now = [0.0]
    t = FakeTransport([cfg], spend_outcomes=[_spend_resp(*init), TransportError("down")])
    aw = agentwatch.init("bot", "tejaswi", "sk-key", endpoint="https://x", transport=t,
                         clock=lambda: now[0], sleep=lambda s: None)
    expected = init[1] if init[0] == "ok" else 0.0
    for provider, model, i, o in steps:
        if provider == "bedrock":
            aw.wrap(FakeBedrock(in_tok=i, out_tok=o)).converse(modelId=model, messages=[])
        else:
            aw.wrap(FakeAnthropic(in_tok=i, out_tok=o)).messages.create(model=model, messages=[], max_tokens=1)
        expected += cost_from_table(table, model, i, o)
    assert math.isclose(aw.local_spend, expected, rel_tol=1e-9, abs_tol=1e-12)
    if fail_sync:  # a failed sync leaves it unchanged
        now[0] = 60.0
        aw._maybe_sync_spend()
        assert math.isclose(aw.local_spend, expected, rel_tol=1e-9, abs_tol=1e-12)
