import pytest

from agentwatch.guardrails import spend_decision


@pytest.mark.parametrize("total,est,cap,want", [
    (0.0, 0.0, 0.0, "allow"),      # exactly equal allows
    (0.5, 0.5, 1.0, "allow"),
    (0.5, 0.500001, 1.0, "block"),
    (1.0, 0.0, 1.0, "allow"),
    (1.1, 0.0, 1.0, "block"),      # already over, even a free call is blocked
    (0.0, 2.0, 1.0, "block"),
])
def test_spend_decision_blocks_iff_total_plus_estimate_exceeds_cap(total, est, cap, want):
    assert spend_decision(total, est, cap) == want
