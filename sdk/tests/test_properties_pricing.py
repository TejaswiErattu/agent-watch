import logging

import pytest
from hypothesis import HealthCheck, given, settings, strategies as st

from agentwatch import pricing

TABLE = {"models": {"known-a": {"inputPerMTokUsd": 3.0, "outputPerMTokUsd": 15.0},
                    "known-b": {"inputPerMTokUsd": 1.0, "outputPerMTokUsd": 5.0}}}
names = st.one_of(st.sampled_from(sorted(TABLE["models"])),
                  st.text(min_size=1, max_size=12).filter(lambda s: s not in TABLE["models"]))


@pytest.fixture(autouse=True)
def _clear_warned():
    pricing._warned.clear()
    yield
    pricing._warned.clear()


def _warned_models(caplog):
    return [r.args[0] for r in caplog.records
            if r.name == "agentwatch" and r.levelno == logging.WARNING and "no price for model" in r.msg]


# Feature: agent-watch, Property 29: Unknown models warn once per process
@settings(max_examples=100, suppress_health_check=[HealthCheck.function_scoped_fixture])
@given(seq=st.lists(names, max_size=20))
def test_property_29_unknown_models_warn_once(seq, caplog):
    pricing._warned.clear()
    caplog.clear()
    caplog.set_level(logging.WARNING, logger="agentwatch")
    for m in seq:
        pricing.warn_unknown_model(TABLE, m)
        if m not in TABLE["models"]:
            assert pricing.cost_from_table(TABLE, m, 100, 100) == 0.0
    warned = _warned_models(caplog)
    unknown = [m for m in dict.fromkeys(seq) if m not in TABLE["models"]]
    assert warned == unknown  # each unknown exactly once, in first-seen order; known never


# Feature: agent-watch, Property 29: Unknown models warn once per process (EMPTY clause)
@settings(max_examples=100, suppress_health_check=[HealthCheck.function_scoped_fixture])
@given(seq=st.lists(names, max_size=20))
def test_property_29_no_warning_without_successful_fetch(seq, caplog):
    import agentwatch
    from fakes import FakeAnthropic, FakeTransport, net_error

    pricing._warned.clear()
    aw = agentwatch.init("bot", "tejaswi", "sk-key", endpoint="https://x",
                         transport=FakeTransport([net_error()]), clock=lambda: 0.0, sleep=lambda s: None)
    caplog.clear()
    caplog.set_level(logging.WARNING, logger="agentwatch")
    client = aw.wrap(FakeAnthropic())
    for m in seq:
        client.messages.create(model=m, max_tokens=1, messages=[])
    aw._sender.flush(5)
    assert _warned_models(caplog) == []
