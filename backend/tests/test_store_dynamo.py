"""DynamoStore writes (task 1.12): agent-record create, config put, transactional record_event, bump_last_seen.

Uses a hand-written fake low-level client that records calls and can raise a
TransactionCanceledException-shaped ClientError with CancellationReasons. No AWS, no moto.
"""

from __future__ import annotations

from decimal import Decimal

import pytest
from botocore.exceptions import ClientError

from agentwatch_api.rules import EMPTY_CONFIG
from agentwatch_api.store import META_SK, AgentRecord, DynamoStore
from agentwatch_api.validation import Event

TABLE = "agentwatch"
KV = "a" * 64


def cancel_error(reasons):
    return ClientError(
        {
            "Error": {"Code": "TransactionCanceledException", "Message": "cancelled"},
            "CancellationReasons": reasons,
        },
        "TransactWriteItems",
    )


class FakeClient:
    """Records calls; raises whatever is queued in `raise_on`."""

    def __init__(self):
        self.calls: list[tuple[str, dict]] = []
        self.raise_on: dict[str, Exception] = {}
        self.query_pages: list[dict] = []

    def _record(self, name, kwargs):
        self.calls.append((name, kwargs))
        if name in self.raise_on:
            raise self.raise_on[name]

    def put_item(self, **kwargs):
        self._record("put_item", kwargs)
        return {}

    def update_item(self, **kwargs):
        self._record("update_item", kwargs)
        return {}

    def transact_write_items(self, **kwargs):
        self._record("transact_write_items", kwargs)
        return {}

    def get_item(self, **kwargs):
        self._record("get_item", kwargs)
        return {}


def make_record(**over):
    base = dict(agent_id="agent-1", owner_id="owner-1", key_verifier=KV, guardrails=EMPTY_CONFIG)
    base.update(over)
    return AgentRecord(**base)


def llm_event():
    return Event(
        agent_id="agent-1", owner_id="owner-1", ts="2026-10-08T00:00:00.000Z",
        event_id="f" * 32, type="llm_call",
        item={"agentId": "agent-1", "ownerId": "owner-1", "ts": "2026-10-08T00:00:00.000Z",
              "eventId": "f" * 32, "type": "llm_call", "model": "claude", "inputTokens": 10,
              "outputTokens": 5, "meta": {}},
    )


# ---- create_agent_if_absent ----

def test_create_sends_attribute_not_exists_and_gsi_owner():
    c = FakeClient()
    store = DynamoStore(TABLE, client=c)
    assert store.create_agent_if_absent(make_record()) is True
    name, kwargs = c.calls[-1]
    assert name == "put_item"
    assert kwargs["TableName"] == TABLE
    assert "attribute_not_exists(sk)" in kwargs["ConditionExpression"]
    assert kwargs["Item"]["gsiOwnerId"] == {"S": "owner-1"}


def test_create_returns_false_on_conditional_failure():
    c = FakeClient()
    c.raise_on["put_item"] = ClientError(
        {"Error": {"Code": "ConditionalCheckFailedException", "Message": "x"}}, "PutItem"
    )
    store = DynamoStore(TABLE, client=c)
    assert store.create_agent_if_absent(make_record()) is False


# ---- record_event transaction ----

def test_record_event_sends_two_transact_items_in_order():
    c = FakeClient()
    store = DynamoStore(TABLE, client=c)
    assert store.record_event(llm_event(), 0.0012345, KV) == "stored"
    name, kwargs = c.calls[-1]
    assert name == "transact_write_items"
    items = kwargs["TransactItems"]
    assert len(items) == 2
    put = items[0]["Put"]
    assert "attribute_not_exists(sk)" in put["ConditionExpression"]
    upd = items[1]["Update"]
    assert "ADD totalSpendUsd" in upd["UpdateExpression"]
    assert "if_not_exists(firstSeen" in upd["UpdateExpression"]
    assert "keyVerifier = :kv" in upd["ConditionExpression"]
    assert upd["ExpressionAttributeValues"][":kv"] == {"S": KV}


def test_record_event_writes_decimal_rounded_cost():
    c = FakeClient()
    store = DynamoStore(TABLE, client=c)
    store.record_event(llm_event(), 0.123456789, KV)
    _, kwargs = c.calls[-1]
    upd = kwargs["TransactItems"][1]["Update"]
    assert upd["ExpressionAttributeValues"][":c"] == {"N": str(Decimal(str(round(0.123456789, 6))))}


@pytest.mark.parametrize(
    "reasons,expected",
    [
        ([{"Code": "ConditionalCheckFailed"}, {"Code": "None"}], "duplicate"),
        ([{"Code": "None"}, {"Code": "ConditionalCheckFailed"}], "forbidden"),
        ([{"Code": "ConditionalCheckFailed"}, {"Code": "ConditionalCheckFailed"}], "forbidden"),
    ],
)
def test_record_event_maps_cancellation(reasons, expected):
    c = FakeClient()
    c.raise_on["transact_write_items"] = cancel_error(reasons)
    store = DynamoStore(TABLE, client=c)
    assert store.record_event(llm_event(), 0.0, KV) == expected


def test_record_event_reraises_unexpected_cancellation():
    c = FakeClient()
    c.raise_on["transact_write_items"] = cancel_error(
        [{"Code": "ThrottlingError"}, {"Code": "None"}]
    )
    store = DynamoStore(TABLE, client=c)
    with pytest.raises(Exception):
        store.record_event(llm_event(), 0.0, KV)


# ---- bump_last_seen ----

def test_bump_last_seen_swallows_conditional_failure():
    c = FakeClient()
    c.raise_on["update_item"] = ClientError(
        {"Error": {"Code": "ConditionalCheckFailedException", "Message": "x"}}, "UpdateItem"
    )
    store = DynamoStore(TABLE, client=c)
    store.bump_last_seen("agent-1", "2026-10-08T00:00:00.000Z")  # must not raise
    name, kwargs = c.calls[-1]
    assert name == "update_item"
    assert "lastSeen" in kwargs["UpdateExpression"]


# ---- get_agent / put_config ----

def test_get_agent_uses_consistent_read_and_returns_none_when_missing():
    c = FakeClient()
    store = DynamoStore(TABLE, client=c)
    assert store.get_agent("nope") is None
    name, kwargs = c.calls[-1]
    assert name == "get_item"
    assert kwargs["ConsistentRead"] is True
    assert kwargs["Key"] == {"agentId": {"S": "nope"}, "sk": {"S": META_SK}}


def test_put_config_sends_verifier_condition():
    c = FakeClient()
    store = DynamoStore(TABLE, client=c)
    assert store.put_config("agent-1", EMPTY_CONFIG, KV) is True
    name, kwargs = c.calls[-1]
    assert name == "update_item"
    assert "keyVerifier = :kv" in kwargs["ConditionExpression"]
    assert kwargs["ExpressionAttributeValues"][":kv"] == {"S": KV}


def test_put_config_returns_false_on_conditional_failure():
    c = FakeClient()
    c.raise_on["update_item"] = ClientError(
        {"Error": {"Code": "ConditionalCheckFailedException", "Message": "x"}}, "UpdateItem"
    )
    store = DynamoStore(TABLE, client=c)
    assert store.put_config("agent-1", EMPTY_CONFIG, KV) is False
