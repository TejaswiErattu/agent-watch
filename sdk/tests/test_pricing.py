import ast
from pathlib import Path

from agentwatch.pricing import cost_from_table

TABLE = {"models": {"m": {"inputPerMTokUsd": 3.0, "outputPerMTokUsd": 15.0}}}


def test_known_model_cost():
    # 1000 * 3 + 500 * 15 = 10500 per million tokens
    assert cost_from_table(TABLE, "m", 1000, 500) == 0.0105


def test_unknown_model_and_empty_table_cost_zero():
    assert cost_from_table(TABLE, "other", 1000, 500) == 0.0
    assert cost_from_table({}, "m", 1000, 500) == 0.0
    assert cost_from_table({"models": {}}, "m", 1000, 500) == 0.0


def test_zero_tokens_cost_zero():
    assert cost_from_table(TABLE, "m", 0, 0) == 0.0


def test_no_numeric_price_literals_in_sdk_pricing():
    src = (Path(__file__).resolve().parent.parent / "agentwatch" / "pricing.py").read_text()
    tree = ast.parse(src)
    for node in ast.walk(tree):
        if isinstance(node, ast.Dict):
            for v in node.values:
                assert not (isinstance(v, ast.Constant) and isinstance(v.value, float)), "price literal in dict"
        if isinstance(node, ast.Constant) and isinstance(node.value, float) and node.value != 0.0:
            raise AssertionError(f"float literal {node.value!r} in sdk pricing.py")


# ---- task 3.14: unknown-model warn-once ----

import logging

import pytest

import agentwatch
from agentwatch import pricing
from agentwatch.client import Response
from fakes import FakeAnthropic, FakeTransport, net_error


@pytest.fixture(autouse=True)
def _clear_warned():
    pricing._warned.clear()
    yield
    pricing._warned.clear()


def _watcher(first_config):
    t = FakeTransport([first_config])
    return agentwatch.init("bot", "tejaswi", "sk-key", endpoint="https://x", transport=t,
                           clock=lambda: 0.0, sleep=lambda s: None)


def _warnings(caplog):
    return [r for r in caplog.records if r.name == "agentwatch" and r.levelno == logging.WARNING
            and "no price for model" in r.getMessage()]


def test_warn_unknown_model_once_and_never_for_known(caplog):
    caplog.set_level(logging.WARNING, logger="agentwatch")
    pricing.warn_unknown_model(TABLE, "mystery")
    pricing.warn_unknown_model(TABLE, "mystery")
    pricing.warn_unknown_model(TABLE, "m")
    (w,) = _warnings(caplog)
    assert "mystery" in w.getMessage()


def test_wrapper_warns_once_with_fetched_table(caplog):
    cfg = Response(200, {"guardrails": {"dailySpendCapUsd": None, "blockedPaths": []}, "pricing": TABLE})
    aw = _watcher(cfg)
    caplog.set_level(logging.WARNING, logger="agentwatch")
    client = aw.wrap(FakeAnthropic())
    for _ in range(2):
        client.messages.create(model="claude-unknown-x", max_tokens=1, messages=[])
    client.messages.create(model="m", max_tokens=1, messages=[])
    aw._sender.flush(5)
    (w,) = _warnings(caplog)
    assert "claude-unknown-x" in w.getMessage()


def test_wrapper_does_not_warn_with_empty_config(caplog):
    aw = _watcher(net_error())  # first fetch fails -> EMPTY
    caplog.set_level(logging.WARNING, logger="agentwatch")
    client = aw.wrap(FakeAnthropic())
    for _ in range(2):
        client.messages.create(model="claude-unknown-x", max_tokens=1, messages=[])
    aw._sender.flush(5)
    assert _warnings(caplog) == []
