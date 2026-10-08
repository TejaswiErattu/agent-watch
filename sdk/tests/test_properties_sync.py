from hypothesis import given, settings, strategies as st

import agentwatch
from agentwatch.client import EMPTY, ConfigResponse, Response, TransportError
from fakes import FakeTransport

SYNC = 60.0
pricing = st.fixed_dictionaries({"models": st.dictionaries(
    st.sampled_from(["a", "b", "c"]),
    st.fixed_dictionaries({"inputPerMTokUsd": st.floats(0, 100), "outputPerMTokUsd": st.floats(0, 100)}),
    max_size=3)})
good = st.builds(lambda cap, paths, p: {"guardrails": {"dailySpendCapUsd": cap, "blockedPaths": paths}, "pricing": p},
                 st.one_of(st.none(), st.floats(0, 100)),
                 st.lists(st.sampled_from([".env", "/etc", "~/.ssh"]), max_size=3), pricing)
outcome = st.one_of(good.map(lambda b: ("ok", b)), st.sampled_from([("net", None), ("500", None), ("bad", None)]))


def _resp(kind, body):
    return {"ok": lambda: Response(200, body), "net": lambda: TransportError("x"),
            "500": lambda: Response(500, None), "bad": lambda: Response(200, {"guardrails": 1})}[kind]()


def _expected(body):
    g = body["guardrails"]
    return ConfigResponse(g["dailySpendCapUsd"], tuple(g["blockedPaths"]), body["pricing"])


# Feature: agent-watch, Property 23: Sync timing and last-good cache
@settings(max_examples=100, deadline=None)
@given(outcomes=st.lists(outcome, min_size=1, max_size=10),
       gaps=st.lists(st.floats(0, 150, allow_nan=False), min_size=0, max_size=12))
def test_property_23_config_sync_timing_and_last_good(outcomes, gaps):
    t = FakeTransport([_resp(*o) for o in outcomes], default=Response(500, None))
    now = [0.0]
    aw = agentwatch.init("bot", "tejaswi", "sk-key", endpoint="https://x", transport=t,
                         clock=lambda: now[0], sleep=lambda s: None)

    # Model: track attempts and last good independently of the implementation.
    queue = list(outcomes)
    last_attempt = 0.0
    attempts = 1
    first = queue.pop(0)
    last_good = _expected(first[1]) if first[0] == "ok" else None
    assert aw.config == (last_good or EMPTY)

    for g in gaps:
        now[0] += g
        aw._maybe_refresh_config()
        if now[0] - last_attempt >= SYNC:
            last_attempt = now[0]
            attempts += 1
            kind, body = queue.pop(0) if queue else ("500", None)
            if kind == "ok":
                last_good = _expected(body)
        assert len(t.requests) == attempts
        if last_good is None:
            assert aw.config is EMPTY
        else:
            assert aw.config == last_good
