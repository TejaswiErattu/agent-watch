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
@given(api_key=st.text(min_size=8, max_size=40).filter(lambda s: s.strip() == s and len(set(s)) > 3),
       steps=st.lists(st.tuples(op, outcome), min_size=1, max_size=8))
def test_property_19_credentials_sent_secrets_never_leaked(caplog, api_key, steps):
    caplog.clear()
    caplog.set_level(logging.DEBUG)
    t = FakeTransport([_make(o) for _, o in steps])
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
