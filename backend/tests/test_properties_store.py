import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from agentwatch_api.store import classify_cancellation

CODES = [None, "ConditionalCheckFailed", "TransactionConflict", "ThrottlingError", "ValidationError"]


def _reason(code):
    # DynamoDB reports a non-failing item as {"Code": "None"}.
    return {"Code": "None"} if code is None else {"Code": code}


# Feature: agent-watch, Property 28: Transaction outcomes are classified correctly
@settings(max_examples=100)
@given(c0=st.sampled_from(CODES), c1=st.sampled_from(CODES))
def test_classification_clause(c0, c1):
    reasons = [_reason(c0), _reason(c1)]
    if c1 == "ConditionalCheckFailed":
        assert classify_cancellation(reasons) == "forbidden"
    elif c0 == "ConditionalCheckFailed" and c1 is None:
        assert classify_cancellation(reasons) == "duplicate"
    else:
        with pytest.raises(RuntimeError):
            classify_cancellation(reasons)
