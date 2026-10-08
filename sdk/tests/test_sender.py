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


# ---- 3.5 background Sender ----

import threading  # noqa: E402

from agentwatch import client as _client  # noqa: E402
from agentwatch.client import Sender  # noqa: E402


class ThreadRecordingTransport(FakeTransport):
    def request(self, *a, **kw):
        r = super().request(*a, **kw)
        self.requests[-1]["thread"] = threading.current_thread().name
        return r


def make_sender(t=None, register=lambda fn: None):
    t = t or ThreadRecordingTransport()
    a = ApiClient("https://x", "tejaswi", key_hash("k"), transport=t)
    return Sender(a, sleep=lambda s: None, register_atexit=register), t


def test_enqueue_delivers_in_order_on_daemon_thread():
    s, t = make_sender()
    for i in range(20):
        s.enqueue({"eventId": f"{i:032x}"})
    assert s.flush(timeout=5) is True
    assert [r["json"]["eventId"] for r in t.requests] == [f"{i:032x}" for i in range(20)]
    assert all(r["thread"] == "agentwatch-sender" for r in t.requests)
    assert s._thread.daemon


def test_send_sync_runs_on_caller_thread():
    s, t = make_sender()
    assert s.send_sync({"eventId": "a" * 32}) is True
    (r,) = t.requests
    assert r["thread"] == threading.current_thread().name


def test_flush_waits_for_slow_delivery():
    gate = threading.Event()

    class Slow(ThreadRecordingTransport):
        def request(self, *a, **kw):
            gate.wait(2)
            return super().request(*a, **kw)

    s, t = make_sender(Slow())
    s.enqueue({"eventId": "b" * 32})
    assert s.flush(timeout=0.05) is False  # still in flight
    gate.set()
    assert s.flush(timeout=5) is True and len(t.requests) == 1


def test_flush_on_empty_queue_returns_true():
    s, _ = make_sender()
    assert s.flush(timeout=0.1) is True


def test_atexit_registered_once_per_sender():
    calls = []
    s, _ = make_sender(register=calls.append)
    s.enqueue({"eventId": "c" * 32})
    s.enqueue({"eventId": "d" * 32})
    assert len(calls) == 1
    assert calls[0].__self__ is s and calls[0].__func__ is Sender._atexit_flush


def test_default_atexit_flush_uses_5s(monkeypatch):
    s, _ = make_sender()
    seen = []
    monkeypatch.setattr(s, "flush", lambda timeout: seen.append(timeout) or True)
    s._atexit_flush()
    assert seen == [5.0]


def test_worker_survives_a_failing_send():
    class Boom(ThreadRecordingTransport):
        def request(self, *a, **kw):
            if not self.requests:
                self.requests.append({})
                raise RuntimeError("boom")
            return super().request(*a, **kw)

    s, t = make_sender(Boom())
    s.enqueue({"eventId": "1" * 32})
    s.enqueue({"eventId": "2" * 32})
    assert s.flush(timeout=5) is True
    assert t.requests[-1]["json"]["eventId"] == "2" * 32
