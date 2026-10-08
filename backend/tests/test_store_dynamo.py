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

    def query(self, **kwargs):
        self._record("query", kwargs)
        if self.query_pages:
            return self.query_pages.pop(0)
        return {"Items": []}


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


# ---- queries (task 1.13) ----


def ev_item_av(sk, type_="tool_call", cost=0.0):
    return {
        "agentId": {"S": "agent-1"},
        "sk": {"S": sk},
        "type": {"S": type_},
        "costUsd": {"N": str(Decimal(str(round(cost, 6))))},
    }


def test_query_events_builds_sk_between_excluding_meta():
    c = FakeClient()
    c.query_pages = [{"Items": [ev_item_av("2026-10-08T00:00:00.000Z#" + "a" * 32)]}]
    store = DynamoStore(TABLE, client=c)
    items, last_sk = store.query_events("agent-1", ascending=True, limit=10)
    name, kwargs = c.calls[-1]
    assert name == "query"
    assert kwargs["TableName"] == TABLE
    kce = kwargs["KeyConditionExpression"]
    assert "agentId = :pk" in kce
    assert "sk BETWEEN :lo AND :hi" in kce
    # High bound must sort below META so events only come back.
    assert kwargs["ExpressionAttributeValues"][":hi"]["S"] < META_SK
    assert kwargs["ScanIndexForward"] is True
    assert kwargs["Limit"] == 10
    assert items[0]["sk"] == "2026-10-08T00:00:00.000Z#" + "a" * 32
    assert last_sk is None


def test_query_events_descending_and_cursor_and_type_filter():
    c = FakeClient()
    c.query_pages = [
        {
            "Items": [ev_item_av("s1", "llm_call"), ev_item_av("s2", "tool_call")],
            "LastEvaluatedKey": {"agentId": {"S": "agent-1"}, "sk": {"S": "s2"}},
        }
    ]
    store = DynamoStore(TABLE, client=c)
    items, last_sk = store.query_events(
        "agent-1", ascending=False, limit=2, type_filter="llm_call", start_after="s9"
    )
    _, kwargs = c.calls[-1]
    assert kwargs["ScanIndexForward"] is False
    assert kwargs["ExclusiveStartKey"]["sk"] == {"S": "s9"}
    assert "#t = :type" in kwargs["FilterExpression"] or "type = :type" in kwargs["FilterExpression"]
    assert last_sk == "s2"
    # DynamoDB applies the FilterExpression server-side, so the store returns the service's items as-is.
    assert all(set(i) >= {"sk", "type"} for i in items)


def test_list_by_owner_queries_owner_index():
    c = FakeClient()
    c.query_pages = [
        {
            "Items": [
                {
                    "agentId": {"S": "agent-1"},
                    "sk": {"S": META_SK},
                    "ownerId": {"S": "owner-1"},
                    "gsiOwnerId": {"S": "owner-1"},
                    "keyVerifier": {"S": KV},
                    "guardrails": {"M": {"dailySpendCapUsd": {"NULL": True}, "blockedPaths": {"L": []}}},
                    "totalSpendUsd": {"N": "1.5"},
                }
            ]
        }
    ]
    store = DynamoStore(TABLE, client=c)
    records = store.list_by_owner("owner-1")
    name, kwargs = c.calls[-1]
    assert name == "query"
    assert kwargs["IndexName"] == "ownerIndex"
    assert "gsiOwnerId = :owner" in kwargs["KeyConditionExpression"]
    assert kwargs["ExpressionAttributeValues"][":owner"] == {"S": "owner-1"}
    assert len(records) == 1
    assert records[0].owner_id == "owner-1"
    assert records[0].total_spend_usd == 1.5


def test_sum_spend_pages_and_converts_decimal():
    c = FakeClient()
    c.query_pages = [
        {
            "Items": [ev_item_av("s1", cost=0.25), ev_item_av("s2", cost=0.75)],
            "LastEvaluatedKey": {"agentId": {"S": "agent-1"}, "sk": {"S": "s2"}},
        },
        {"Items": [ev_item_av("s3", cost=1.0)]},
    ]
    store = DynamoStore(TABLE, client=c)
    total = store.sum_spend("agent-1", "s0", "s9")
    assert total == 2.0
    assert isinstance(total, float)
    # Paged twice: second call carried ExclusiveStartKey.
    query_calls = [k for n, k in c.calls if n == "query"]
    assert len(query_calls) == 2
    assert query_calls[1]["ExclusiveStartKey"]["sk"] == {"S": "s2"}
