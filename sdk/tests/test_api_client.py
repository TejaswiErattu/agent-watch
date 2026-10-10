import pytest

from agentwatch.client import ApiClient, Response, RequestsTransport, TransportError, key_hash
from fakes import FakeTransport

EP = "https://api.example.com"
H = key_hash("sk-test")


def client(t=None, endpoint=EP):
    return ApiClient(endpoint, "tejaswi", H, transport=t or FakeTransport())


def test_post_event_sends_json_to_events():
    t = FakeTransport()
    ev = {"agentId": "bot", "eventId": "0" * 32}
    resp = client(t).post_event(ev)
    (r,) = t.requests
    assert (r["method"], r["url"], r["json"]) == ("POST", f"{EP}/events", ev)
    assert resp == Response(200, {})


def test_get_config_and_spend_urls():
    t = FakeTransport(route_spend=False)
    c = client(t)
    c.get_config("bot")
    c.get_spend("bot")
    assert [(r["method"], r["url"]) for r in t.requests] == [
        ("GET", f"{EP}/agents/bot/config"),
        ("GET", f"{EP}/agents/bot/spend"),
    ]
    assert all(r["json"] is None for r in t.requests)


def test_trailing_slash_in_endpoint_is_trimmed():
    t = FakeTransport()
    client(t, endpoint=EP + "/").get_config("bot")
    assert t.requests[0]["url"] == f"{EP}/agents/bot/config"


def test_every_request_has_credential_headers_and_2s_timeout():
    t = FakeTransport()
    c = client(t)
    c.post_event({})
    c.get_config("bot")
    c.get_spend("bot")
    for r in t.requests:
        assert r["headers"]["X-Agentwatch-Owner"] == "tejaswi"
        assert r["headers"]["X-Agentwatch-Key-Hash"] == H
        assert r["timeout"] == 2.0


def test_transport_error_propagates():
    t = FakeTransport([TransportError("boom")])
    with pytest.raises(TransportError):
        client(t).get_config("bot")


def test_repr_hides_key_hash():
    c = client()
    assert H not in repr(c) and "tejaswi" in repr(c)


def test_default_transport_is_requests_session():
    c = ApiClient(EP, "tejaswi", H)
    assert isinstance(c.transport, RequestsTransport)


class _FakeResp:
    def __init__(self, status, text):
        self.status_code, self.text = status, text


class _FakeSession:
    def __init__(self, result):
        self.result, self.calls = result, []

    def request(self, method, url, **kw):
        self.calls.append((method, url, kw))
        if isinstance(self.result, Exception):
            raise self.result
        return self.result


def test_requests_transport_parses_json_and_tolerates_non_json():
    s = _FakeSession(_FakeResp(200, '{"a": 1}'))
    assert RequestsTransport(s).request("GET", "u", headers={}, timeout=2.0) == Response(200, {"a": 1})
    s = _FakeSession(_FakeResp(502, "<html>bad gateway</html>"))
    assert RequestsTransport(s).request("GET", "u", headers={}, timeout=2.0) == Response(502, None)


def test_requests_transport_wraps_network_errors():
    import requests

    for exc in (requests.ConnectionError("x"), requests.Timeout("x")):
        with pytest.raises(TransportError):
            RequestsTransport(_FakeSession(exc)).request("GET", "u", headers={}, timeout=2.0)


# ---- 3.19 no redirects, https only ----

import agentwatch  # noqa: E402


@pytest.mark.parametrize("method", ["GET", "POST", "PUT"])
def test_requests_transport_never_follows_redirects(method):
    s = _FakeSession(_FakeResp(200, "{}"))
    RequestsTransport(session=s).request(method, EP + "/x", headers={}, json=None, timeout=2)
    assert s.calls[0][2]["allow_redirects"] is False


def test_redirect_is_returned_not_followed():
    s = _FakeSession(_FakeResp(302, ""))
    r = RequestsTransport(session=s).request("GET", EP + "/x", headers={"X-Agentwatch-Key-Hash": H},
                                             json=None, timeout=2)
    assert r.status == 302 and len(s.calls) == 1


@pytest.mark.parametrize("bad", ["http://example.com", "http://api.example.com/prod", "ftp://x",
                                 "api.example.com", "HTTP://localhost.evil.com", "http://localhost.evil.com",
                                 "http://127.0.0.1.evil.com", "http://localhost@evil.com", "https://", ""])
def test_non_https_endpoint_rejected(bad):
    with pytest.raises(ValueError):
        ApiClient(bad, "tejaswi", H, transport=FakeTransport())
    with pytest.raises(ValueError):
        agentwatch.init("bot", "tejaswi", "sk-key", endpoint=bad or "x", transport=FakeTransport())


@pytest.mark.parametrize("ok", ["https://api.example.com", "https://abc.execute-api.us-west-2.amazonaws.com/",
                                "http://localhost", "http://localhost:3000", "http://127.0.0.1:8080/api"])
def test_https_and_loopback_accepted(ok):
    ApiClient(ok, "tejaswi", H, transport=FakeTransport())
