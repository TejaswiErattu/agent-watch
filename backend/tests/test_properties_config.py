from hypothesis import given, settings
from hypothesis import strategies as st

from agentwatch_api.auth import Credentials
from agentwatch_api.pricing import pricing_table
from agentwatch_api.rules import EMPTY_CONFIG, to_json
from agentwatch_api.service import get_config
from agentwatch_api.store import InMemoryStore

agent_ids = st.from_regex(r"[A-Za-z0-9._-]{1,128}", fullmatch=True)
creds_s = st.builds(
    Credentials,
    st.from_regex(r"[A-Za-z0-9._-]{1,64}", fullmatch=True),
    st.from_regex(r"[0-9a-f]{64}", fullmatch=True),
)


# Feature: agent-watch, Property 6: Read routes never create records
@settings(max_examples=100)
@given(agent_id=agent_ids, creds=creds_s)
def test_get_config_never_creates_records(agent_id, creds):
    s = InMemoryStore()
    r = get_config(s, creds, agent_id)
    assert r.status == 200
    assert r.body == {"guardrails": to_json(EMPTY_CONFIG), "pricing": pricing_table()}
    assert s.items == {}


# ---- 2.5: Properties 4 and 5 ----

import math  # noqa: E402

from agentwatch_api.rules import GuardrailConfig  # noqa: E402
from agentwatch_api.service import new_record, put_config  # noqa: E402

path_s = st.text(min_size=1, max_size=40)
configs = st.builds(
    GuardrailConfig,
    st.one_of(st.none(), st.floats(0, 1000, allow_nan=False, allow_infinity=False)),
    st.lists(path_s, max_size=10).map(tuple),
)
bad_caps = st.one_of(
    st.booleans(), st.text(max_size=5), st.floats(max_value=-1e-9, allow_nan=False),
    st.just(float("nan")), st.just(float("inf")), st.lists(st.integers(), max_size=2),
)
bad_paths = st.one_of(
    st.text(max_size=5), st.none(), st.integers(),
    st.lists(path_s, max_size=3).map(lambda xs: xs + [""]),
    st.lists(path_s, max_size=3).map(lambda xs: xs + [7]),
)


@st.composite
def bad_bodies(draw):
    good = to_json(draw(configs))
    which = draw(st.sampled_from(["dailySpendCapUsd", "blockedPaths"]))
    good[which] = draw(bad_caps if which == "dailySpendCapUsd" else bad_paths)
    return good, which


# Feature: agent-watch, Property 4: Invalid guardrail configs are rejected without side effects
@settings(max_examples=100)
@given(bad=bad_bodies(), existing=st.one_of(st.none(), configs), creds=creds_s)
def test_invalid_configs_rejected_without_side_effects(bad, existing, creds):
    body, field = bad
    s = InMemoryStore()
    if existing is not None:
        s.create_agent_if_absent(new_record("bot", creds, existing))
    before = s.snapshot()
    r = put_config(s, creds, "bot", body)
    assert r.status == 400 and field in r.body["error"]
    assert s.snapshot() == before


def _same(a, b):
    """Config equality where float caps compare exactly (no NaN can appear here)."""
    return a == b and (a["dailySpendCapUsd"] is None or not math.isnan(a["dailySpendCapUsd"]))


# Feature: agent-watch, Property 5: Config PUT then GET round trip
@settings(max_examples=100)
@given(cfg=configs, agent_id=agent_ids, creds=creds_s, preexisting=st.booleans())
def test_put_then_get_round_trip(cfg, agent_id, creds, preexisting):
    s = InMemoryStore()
    if preexisting:
        s.create_agent_if_absent(new_record(agent_id, creds, EMPTY_CONFIG))
    r = put_config(s, creds, agent_id, to_json(cfg))
    assert r.status == 200 and _same(r.body["guardrails"], to_json(cfg))
    g = get_config(s, creds, agent_id)
    assert g.status == 200
    assert _same(g.body["guardrails"], to_json(cfg))
    assert g.body["pricing"] == pricing_table()
