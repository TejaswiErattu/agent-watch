from hypothesis import given, settings, strategies as st

from agentwatch import pricing as sdk_pricing
from agentwatch_api.pricing import PRICING, estimate_cost, pricing_table

model = st.one_of(st.sampled_from(sorted(PRICING)), st.text(max_size=40))
tokens = st.integers(min_value=0, max_value=10_000_000)


# Feature: agent-watch, Property 1: SDK cost matches backend cost
@settings(max_examples=100)
@given(m=model, i=tokens, o=tokens)
def test_property_1_sdk_cost_matches_backend(m, i, o):
    sdk = sdk_pricing.cost_from_table(pricing_table(), m, i, o)
    backend = estimate_cost(m, i, o)
    assert abs(sdk - backend) <= 0.0001
    assert sdk >= 0
    if m not in PRICING:
        assert sdk == 0.0
