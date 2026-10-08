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


# ---- service clause (task 2.3) ----

from datetime import datetime, timezone  # noqa: E402

from agentwatch_api.auth import Credentials  # noqa: E402
from agentwatch_api.rules import EMPTY_CONFIG  # noqa: E402
from agentwatch_api.service import ingest_event, new_record  # noqa: E402
from agentwatch_api.store import META_SK, InMemoryStore  # noqa: E402

NOW = datetime(2026, 10, 8, 12, tzinfo=timezone.utc)
CREDS = Credentials("tejaswi", "a" * 64)


class SwappableStore(InMemoryStore):
    """When swap_next is set, the META keyVerifier is replaced just before the transaction."""

    swap_next = False

    def record_event(self, event, cost, key_verifier):
        if self.swap_next:
            self.swap_next = False
            self.items[(event.agent_id, META_SK)]["keyVerifier"] = "c" * 64
        return super().record_event(event, cost, key_verifier)


class CountingPublisher:
    def __init__(self):
        self.calls = 0

    def publish(self, subject, body):
        self.calls += 1


def _body(i):
    return {"agentId": "bot", "ownerId": "tejaswi", "ts": f"2026-10-08T10:00:{i:02d}.000Z",
            "eventId": f"{i:032x}", "type": "llm_call", "model": "claude-haiku-4-5",
            "inputTokens": 100 * (i + 1), "outputTokens": 10}


ops = st.lists(
    st.tuples(st.sampled_from(["new", "resubmit"]), st.integers(0, 5), st.booleans()),
    min_size=1, max_size=12,
)


# Feature: agent-watch, Property 28: Transaction outcomes are classified correctly
@settings(max_examples=100)
@given(ops=ops)
def test_service_clause(ops):
    s = SwappableStore()
    s.create_agent_if_absent(new_record("bot", CREDS, EMPTY_CONFIG))
    pub = CountingPublisher()
    owned, stored, next_i = True, [], 0
    for kind, pick, swap in ops:
        if kind == "resubmit" and stored:
            i = stored[pick % len(stored)]
        else:
            i, next_i = next_i, next_i + 1
        spend_before = s.items[("bot", META_SK)]["totalSpendUsd"]
        calls_before = pub.calls
        s.swap_next = swap
        r = ingest_event(s, CREDS, _body(i), NOW, publisher=pub)
        s.swap_next = False
        if not owned:
            assert r.status == 403  # rejected at authorize
        elif swap:
            assert r.status == 403  # verifier replaced mid-flight, even if also a duplicate
            owned = False
        elif i in stored:
            assert r.status == 200 and r.body["duplicate"] is True
        else:
            assert r.status == 200 and r.body["duplicate"] is False
            stored.append(i)
            continue
        assert r.status == 403 or r.body["duplicate"] is True
        assert s.items[("bot", META_SK)]["totalSpendUsd"] == spend_before
        assert pub.calls == calls_before
