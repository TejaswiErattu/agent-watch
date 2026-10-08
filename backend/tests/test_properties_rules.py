import json

from hypothesis import given, settings
from hypothesis import strategies as st

from agentwatch_api.rules import GuardrailConfig, parse_config, to_json

caps = st.one_of(
    st.none(),
    st.integers(min_value=0, max_value=10**6),
    st.floats(min_value=0, max_value=1e6, allow_nan=False, allow_infinity=False),
)
paths = st.lists(st.text(min_size=1, max_size=1024), max_size=100).map(tuple)
configs = st.builds(GuardrailConfig, caps, paths)


# Feature: agent-watch, Property 3: Guardrail_Config JSON round trip
@settings(max_examples=100)
@given(cfg=configs)
def test_guardrail_config_json_round_trip(cfg):
    assert parse_config(json.loads(json.dumps(to_json(cfg)))) == cfg
