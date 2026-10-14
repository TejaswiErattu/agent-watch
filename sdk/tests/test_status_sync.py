"""Task 8.3: status poll, Pause_State cache, AgentPaused (Req 27.8-27.11)."""

import logging

import pytest

import agentwatch
from agentwatch.client import (CONTROL_INTERVAL_S, PAUSE_NOT_ACTIVE_MSG, AgentPaused, GuardrailBlocked,
                               Response, TransportError)
from fakes import FakeTransport, status_body

EP = "https://api.example.com"


class Clock:
    def __init__(self, t=1000.0):
        self.t = t

    def __call__(self):
        return self.t


def init(status_outcomes=(), clock=None):
    t = FakeTransport(status_outcomes=list(status_outcomes))
    clock = clock or Clock()
    aw = agentwatch.init("bot", "tejaswi", "sk-key", endpoint=EP, transport=t, clock=clock,
                         sleep=lambda s: None)
    return aw, t, clock


def test_init_fetches_status_once_and_routes_separately():
    aw, t, _ = init()
    assert [r["url"] for r in t.status_requests] == [f"{EP}/agents/bot/status"]
    assert t.status_requests[0]["method"] == "GET"
    assert not any(r["url"].endswith("/status") for r in t.requests)
    assert aw.paused is False


def test_init_reads_paused_true():
    aw, _, _ = init([Response(200, status_body(True))])
    assert aw.paused is True


def test_refresh_only_after_control_interval():
    aw, t, clock = init([Response(200, status_body(False)), Response(200, status_body(True))])
    clock.t += CONTROL_INTERVAL_S - 0.01
    aw._maybe_refresh_status()
    assert len(t.status_requests) == 1 and aw.paused is False
    clock.t += 0.01
    aw._maybe_refresh_status()
    assert len(t.status_requests) == 2 and aw.paused is True


BAD = [TransportError("x"), RuntimeError("boom"), Response(500, None), Response(403, {"error": "f"}),
       Response(200, None), Response(200, {"agentId": "bot"}), Response(200, {"paused": "true"}),
       Response(200, {"paused": 1}), Response(200, ["paused"])]


@pytest.mark.parametrize("bad", BAD)
def test_failure_keeps_last_state_and_warns(bad, caplog):
    aw, t, clock = init([Response(200, status_body(True))])
    caplog.clear()
    t.status_outcomes.append(bad)
    clock.t += CONTROL_INTERVAL_S
    with caplog.at_level(logging.WARNING, logger="agentwatch"):
        aw._maybe_refresh_status()
    assert aw.paused is True
    msgs = [r.getMessage() for r in caplog.records]
    assert msgs and PAUSE_NOT_ACTIVE_MSG not in msgs
    assert any("status" in m for m in msgs)


@pytest.mark.parametrize("bad", BAD)
def test_not_active_message_while_never_succeeded(bad, caplog):
    with caplog.at_level(logging.WARNING, logger="agentwatch"):
        aw, t, clock = init([bad])
    assert aw.paused is False
    assert [r.getMessage() for r in caplog.records].count(PAUSE_NOT_ACTIVE_MSG) == 1
    # Still never succeeded: the next failure logs it again.
    caplog.clear()
    t.status_outcomes.append(bad)
    clock.t += CONTROL_INTERVAL_S
    with caplog.at_level(logging.WARNING, logger="agentwatch"):
        aw._maybe_refresh_status()
    assert PAUSE_NOT_ACTIVE_MSG in [r.getMessage() for r in caplog.records]
    # After one success it never appears again.
    caplog.clear()
    t.status_outcomes += [Response(200, status_body(False)), bad]
    for _ in range(2):
        clock.t += CONTROL_INTERVAL_S
        with caplog.at_level(logging.WARNING, logger="agentwatch"):
            aw._maybe_refresh_status()
    assert PAUSE_NOT_ACTIVE_MSG not in [r.getMessage() for r in caplog.records]


def test_success_logs_nothing(caplog):
    with caplog.at_level(logging.WARNING, logger="agentwatch"):
        init()
    assert not [r for r in caplog.records if "status" in r.getMessage() or "pause" in r.getMessage()]


def test_resume_clears_pause_reported():
    aw, t, clock = init([Response(200, status_body(True))])
    aw._pause_reported = True
    t.status_outcomes.append(Response(200, status_body(True)))
    clock.t += CONTROL_INTERVAL_S
    aw._maybe_refresh_status()
    assert aw._pause_reported is True  # still the same episode
    t.status_outcomes.append(Response(200, status_body(False)))
    clock.t += CONTROL_INTERVAL_S
    aw._maybe_refresh_status()
    assert aw._pause_reported is False


def test_agent_paused_is_guardrail_blocked():
    e = AgentPaused("agent bot is paused")
    assert isinstance(e, GuardrailBlocked)
    assert e.violation_type == "paused"
    assert e.detail == "agent bot is paused"


def test_exported():
    assert agentwatch.AgentPaused is AgentPaused
    assert "AgentPaused" in agentwatch.__all__


def test_api_client_get_status_url():
    t = FakeTransport(route_spend=False)
    from agentwatch.client import ApiClient, key_hash
    ApiClient(EP, "tejaswi", key_hash("k"), transport=t).get_status("bot")
    assert t.requests[0]["method"] == "GET"
    assert t.requests[0]["url"] == f"{EP}/agents/bot/status"
