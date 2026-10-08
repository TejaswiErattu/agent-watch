from hypothesis import given, settings
from hypothesis import strategies as st

from agentwatch_api.pricing import PRICING, estimate_cost, format_cost, parse_cost

tokens = st.integers(min_value=0, max_value=10_000_000)


# Feature: agent-watch, Property 2: Cost format round trip
@settings(max_examples=100)
@given(model=st.sampled_from(sorted(PRICING)), i=tokens, o=tokens)
def test_cost_format_round_trip(model, i, o):
    cost = estimate_cost(model, i, o)
    assert abs(parse_cost(format_cost(cost)) - cost) <= 0.0001


@settings(max_examples=100)
@given(model=st.one_of(st.sampled_from(sorted(PRICING)), st.text(max_size=40)), i=tokens, o=tokens)
def test_cost_is_never_negative(model, i, o):
    assert estimate_cost(model, i, o) >= 0.0
