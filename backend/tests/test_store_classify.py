import pytest

from agentwatch_api.store import classify_cancellation

CCF = "ConditionalCheckFailed"


def r(*codes):
    return [{"Code": c} if c is not None else {"Code": "None"} for c in codes]


def test_duplicate_item0_failed_item1_none():
    assert classify_cancellation(r(CCF, None)) == "duplicate"


def test_forbidden_item1_failed():
    assert classify_cancellation(r(None, CCF)) == "forbidden"


def test_forbidden_wins_when_both_failed():
    assert classify_cancellation(r(CCF, CCF)) == "forbidden"


@pytest.mark.parametrize(
    "codes",
    [
        ("TransactionConflict", None),
        (None, "TransactionConflict"),
        ("ThrottlingError", None),
        (CCF, "ThrottlingError"),
        ("ValidationError", "ValidationError"),
        (None, None),
    ],
)
def test_other_combinations_raise(codes):
    with pytest.raises(RuntimeError):
        classify_cancellation(r(*codes))


def test_missing_code_key_treated_as_none():
    assert classify_cancellation([{"Code": CCF}, {}]) == "duplicate"


def test_wrong_length_raises():
    with pytest.raises(RuntimeError):
        classify_cancellation([{"Code": CCF}])
