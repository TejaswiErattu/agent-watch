import json

from hypothesis import given, settings
from hypothesis import strategies as st

from agentwatch_api.rules import KEYS, GuardrailConfig, parse_config, to_json
from agentwatch_api.store import item_to_record

caps = st.one_of(st.none(), st.floats(0, 1000, allow_nan=False, allow_infinity=False), st.integers(0, 1000))
paths = st.lists(st.text(min_size=1, max_size=40), max_size=10).map(tuple)
# Literal words only: always compile, so every generated config is valid.
commands = st.lists(st.from_regex(r"[a-z]{1,10}", fullmatch=True), max_size=10).map(tuple)

v2_configs = st.builds(GuardrailConfig, caps, paths, commands)
v1_bodies = st.builds(lambda c, p: {"dailySpendCapUsd": c, "blockedPaths": list(p)}, caps, paths)


# Feature: agent-watch-v2, Property 32: Guardrail_Config v2 round trip and v1 compatibility
@settings(max_examples=100)
@given(cfg=v2_configs, v1=v1_bodies)
def test_property_32_v2_round_trip_and_v1_compat(cfg, v1):
    out = to_json(cfg)
    assert set(out) == set(KEYS)
    assert parse_config(json.loads(json.dumps(out))) == cfg

    parsed = parse_config(v1)
    assert isinstance(parsed, GuardrailConfig)
    assert parsed.blocked_commands == ()

    item = {"agentId": "bot", "sk": "META", "ownerId": "o", "gsiOwnerId": "o",
            "keyVerifier": "v" * 64, "guardrails": v1, "totalSpendUsd": 0}
    rec = item_to_record(item)
    assert rec.paused is False
    assert rec.guardrails.blocked_commands == ()
