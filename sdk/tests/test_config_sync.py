import logging

import pytest

import agentwatch
from agentwatch.client import EMPTY, ConfigResponse, Response, TransportError, Watcher, key_hash
from fakes import FakeTransport

EP = "https://api.example.com"
PRICING = {"models": {"m": {"inputPerMTokUsd": 1.0, "outputPerMTokUsd": 5.0}}}


def cfg_body(cap=None, paths=(".env",), pricing=PRICING):
    return {"guardrails": {"dailySpendCapUsd": cap, "blockedPaths": list(paths)}, "pricing": pricing}


class Clock:
    def __init__(self, t=1000.0):
        self.t = t

    def __call__(self):
        return self.t


def init(outcomes, clock=None, **kw):
    t = FakeTransport(outcomes)
    clock = clock or Clock()
    aw = agentwatch.init("bot", "tejaswi", "sk-key", endpoint=EP, transport=t, clock=clock,
                         sleep=lambda s: None, **kw)
    return aw, t, clock


def config_calls(t):
    return [r for r in t.requests if r["url"].endswith("/config")]


def test_init_requires_endpoint(monkeypatch):
    monkeypatch.delenv("AGENTWATCH_ENDPOINT", raising=False)
    with pytest.raises(ValueError, match="endpoint"):
        agentwatch.init("bot", "tejaswi", "sk-key", transport=FakeTransport())


def test_init_uses_env_endpoint(monkeypatch):
    monkeypatch.setenv("AGENTWATCH_ENDPOINT", EP)
    t = FakeTransport([Response(200, cfg_body())])
    aw = agentwatch.init("bot", "tejaswi", "sk-key", transport=t, clock=Clock(), sleep=lambda s: None)
    assert t.requests[0]["url"] == f"{EP}/agents/bot/config"
    assert isinstance(aw, Watcher)


def test_init_fetches_config_once():
    aw, t, _ = init([Response(200, cfg_body(cap=2.0))])
    assert len(config_calls(t)) == 1
    assert aw.config == ConfigResponse(2.0, (".env",), PRICING)


@pytest.mark.parametrize("bad", [TransportError("x"), Response(500, None), Response(403, {"error": "forbidden"}),
                                 Response(200, {"nope": 1}), Response(200, None),
                                 Response(200, cfg_body(cap="lots")),
                                 Response(200, cfg_body(paths=[1]))])
def test_failing_first_fetch_leaves_empty(bad):
    aw, _, _ = init([bad])
    assert aw.config is EMPTY
    assert EMPTY.daily_spend_cap_usd is None and EMPTY.blocked_paths == () and EMPTY.pricing == {}


def test_failure_after_success_keeps_last_good_and_warns(caplog):
    caplog.set_level(logging.WARNING, logger="agentwatch")
    clock = Clock()
    aw, t, _ = init([Response(200, cfg_body(cap=1.0)), TransportError("down")], clock=clock)
    good = aw.config
    clock.t += 60
    aw._maybe_refresh_config()
    assert aw.config == good
    assert "config" in caplog.text.lower()
    assert "sk-key" not in caplog.text and key_hash("sk-key") not in caplog.text


def test_refresh_only_after_60s_since_last_attempt():
    clock = Clock()
    aw, t, _ = init([Response(200, cfg_body())] * 5, clock=clock)
    clock.t += 59.9
    aw._maybe_refresh_config()
    assert len(config_calls(t)) == 1
    clock.t += 0.1  # exactly 60 s
    aw._maybe_refresh_config()
    assert len(config_calls(t)) == 2
    aw._maybe_refresh_config()  # just attempted
    assert len(config_calls(t)) == 2


def test_failed_refresh_retries_at_most_once_per_interval():
    clock = Clock()
    aw, t, _ = init([TransportError("x")] * 5, clock=clock)
    for _ in range(13):  # 65 s of checks every 5 s
        clock.t += 5
        aw._maybe_refresh_config()
    # init + exactly one retry at +60 s; the next is not due until +120 s
    assert len(config_calls(t)) == 2


def test_successful_refresh_replaces_cache():
    clock = Clock()
    aw, _, _ = init([Response(200, cfg_body(cap=1.0)), Response(200, cfg_body(cap=3.0, paths=()))], clock=clock)
    clock.t += 60
    aw._maybe_refresh_config()
    assert aw.config == ConfigResponse(3.0, (), PRICING)


def test_watcher_repr_hides_secrets():
    aw, _, _ = init([Response(200, cfg_body())])
    text = repr(aw)
    assert "sk-key" not in text and key_hash("sk-key") not in text and "bot" in text


def test_init_exported_from_package():
    assert callable(agentwatch.init)


# ---- 3.20 loud warning while guardrails are not active ----

NOT_ACTIVE = "agentwatch: guardrails NOT active (config fetch failed)"


def _count(caplog):
    return sum(1 for r in caplog.records if r.getMessage() == NOT_ACTIVE and r.levelno == logging.WARNING)


@pytest.mark.parametrize("bad", [TransportError("x"), Response(500, None), Response(200, {"nope": 1})])
def test_failed_first_fetch_warns_not_active_once_at_init(caplog, bad):
    caplog.set_level(logging.WARNING, logger="agentwatch")
    init([bad])
    assert _count(caplog) == 1


def test_not_active_repeats_per_failed_refresh_until_success(caplog):
    caplog.set_level(logging.WARNING, logger="agentwatch")
    clock = Clock()
    aw, _, _ = init([TransportError("x"), Response(500, None), Response(200, cfg_body()),
                     TransportError("x")], clock=clock)
    assert _count(caplog) == 1
    clock.t += 30
    aw._maybe_refresh_config()  # not due: no fetch, no extra warning
    assert _count(caplog) == 1
    clock.t += 30
    aw._maybe_refresh_config()  # failed refresh, still never succeeded
    assert _count(caplog) == 2
    clock.t += 60
    aw._maybe_refresh_config()  # success
    assert _count(caplog) == 2
    clock.t += 60
    aw._maybe_refresh_config()  # failure after a success: last-good warning only
    assert _count(caplog) == 2
    assert "keeping last good config" in caplog.text


def test_no_not_active_warning_when_first_fetch_succeeds(caplog):
    caplog.set_level(logging.WARNING, logger="agentwatch")
    init([Response(200, cfg_body())])
    assert _count(caplog) == 0
