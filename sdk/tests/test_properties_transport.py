import json
import logging

from hypothesis import HealthCheck, given, settings, strategies as st

from agentwatch.client import ApiClient, Response, TransportError, key_hash
from fakes import FakeTransport

outcome = st.sampled_from(["ok", "401", "403", "500", "net"])
op = st.sampled_from(["post_event", "get_config", "get_spend"])


def _make(o):
    return {"ok": Response(200, {}), "401": Response(401, {"error": "unauthorized"}),
            "403": Response(403, {"error": "forbidden"}), "500": Response(500, None),
            "net": TransportError("network down")}[o]


# Feature: agent-watch, Property 19: Credentials sent, secrets never leaked by the SDK
@settings(max_examples=100, suppress_health_check=[HealthCheck.function_scoped_fixture])
# Realistic keys: long and random. A short key like "X-Agentw" would falsely "leak" via header names.
@given(api_key=st.text(st.characters(min_codepoint=33, max_codepoint=0x2FF), min_size=16, max_size=40)
       .map(lambda s: "sk-" + s),
       steps=st.lists(st.tuples(op, outcome), min_size=1, max_size=8))
def test_property_19_credentials_sent_secrets_never_leaked(caplog, api_key, steps):
    caplog.clear()
    caplog.set_level(logging.DEBUG)
    t = FakeTransport([_make(o) for _, o in steps], route_spend=False)
    c = ApiClient("https://api.example.com", "tejaswi", key_hash(api_key), transport=t)
    for name, _ in steps:
        try:
            if name == "post_event":
                c.post_event({"agentId": "bot", "type": "tool_call"})
            else:
                getattr(c, name)("bot")
        except TransportError:
            pass
    assert len(t.requests) == len(steps)
    for r in t.requests:
        assert r["headers"]["X-Agentwatch-Owner"] == "tejaswi"
        assert r["headers"]["X-Agentwatch-Key-Hash"] == key_hash(api_key)
        blob = r["url"] + json.dumps(r["headers"]) + json.dumps(r["json"])
        assert api_key not in blob
    assert api_key not in caplog.text
    assert api_key not in repr(c)


retry_outcome = st.sampled_from(["200", "201", "net", "timeout", "500", "503", "429", "400", "401", "403"])
STOP = {"200", "201", "400", "401", "403"}


def _retry_make(o):
    if o == "net":
        return TransportError("ConnectionError")
    if o == "timeout":
        return TransportError("Timeout")
    return Response(int(o), {"error": "x"} if o == "400" else None)


# Feature: agent-watch, Property 20: Retry policy
@settings(max_examples=100)
@given(outcomes=st.lists(retry_outcome, min_size=1, max_size=8))
def test_property_20_retry_policy(outcomes):
    import agentwatch.client as c
    from agentwatch.client import send_with_retries

    c._auth_warned = False
    t = FakeTransport([_retry_make(o) for o in outcomes], default=Response(500, None))
    a = ApiClient("https://x", "tejaswi", key_hash("k"), transport=t)
    sleeps = []
    ok = send_with_retries(a, {"eventId": "e" * 32}, sleeps.append)  # never raises

    # Expected attempts: up to and including the first stopping outcome, capped at 4.
    padded = outcomes + ["500"] * 4
    expected = next((i + 1 for i, o in enumerate(padded[:4]) if o in STOP), 4)
    assert len(t.requests) == expected
    assert sleeps == [0.5, 1, 2][: expected - 1]
    assert ok == (padded[expected - 1] in {"200", "201"})
