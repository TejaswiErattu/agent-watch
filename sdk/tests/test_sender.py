import logging

import pytest

from agentwatch.client import ApiClient, Response, TransportError, key_hash, send_with_retries
from fakes import FakeTransport

EID = "e" * 32
EVENT = {"agentId": "bot", "eventId": EID}


class Sleeps(list):
    def __call__(self, s):
        self.append(s)


def api(outcomes):
    t = FakeTransport(outcomes)
    return ApiClient("https://x", "tejaswi", key_hash("k"), transport=t), t


@pytest.fixture(autouse=True)
def _reset_auth_warning():
    import agentwatch.client as c
    c._auth_warned = False
    yield
    c._auth_warned = False


def test_5xx_then_200_succeeds_on_attempt_2():
    a, t = api([Response(503, None), Response(200, {})])
    sleeps = Sleeps()
    assert send_with_retries(a, EVENT, sleeps) is True
    assert len(t.requests) == 2 and sleeps == [0.5]


@pytest.mark.parametrize("status", [401, 403])
def test_auth_failure_logs_once_no_retry(caplog, status):
    caplog.set_level(logging.WARNING, logger="agentwatch")
    a, t = api([Response(status, {"error": "x"}), Response(status, {"error": "x"})])
    sleeps = Sleeps()
    assert send_with_retries(a, EVENT, sleeps) is False
    assert send_with_retries(a, EVENT, sleeps) is False
    assert len(t.requests) == 2 and sleeps == []
    msgs = [r.getMessage() for r in caplog.records]
    assert msgs.count("agentwatch: authorization failed (check owner_id/api_key)") == 1


def test_400_logs_server_message_no_retry(caplog):
    caplog.set_level(logging.WARNING, logger="agentwatch")
    a, t = api([Response(400, {"error": "eventId: must be 32 lowercase hex"})])
    assert send_with_retries(a, EVENT, Sleeps()) is False
    assert len(t.requests) == 1
    assert "eventId: must be 32 lowercase hex" in caplog.text


def test_four_failures_warn_with_event_id(caplog):
    caplog.set_level(logging.WARNING, logger="agentwatch")
    a, t = api([TransportError("x"), Response(429, None), Response(500, None), TransportError("y")])
    sleeps = Sleeps()
    assert send_with_retries(a, EVENT, sleeps) is False
    assert len(t.requests) == 4 and sleeps == [0.5, 1, 2]
    assert EID in caplog.text


def test_unexpected_exception_never_raises(caplog):
    class Broken:
        def post_event(self, e):
            raise RuntimeError("bug")

    assert send_with_retries(Broken(), EVENT, Sleeps()) is False
