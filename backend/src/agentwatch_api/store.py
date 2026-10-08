"""Event_Store: one DynamoDB table, PK agentId, SK sk.

Items:
- Agent_Record: sk == "META", carries ownerId, gsiOwnerId (sparse GSI key), keyVerifier, guardrails,
  firstSeen?, lastSeen?, model?, totalSpendUsd.
- Event: sk == f"{ts}#{eventId}". No keyVerifier, no gsiOwnerId (Req 4.6, 14.3).

InMemoryStore mirrors DynamoStore's conditional semantics and is used by every service test.
"""

from __future__ import annotations

import copy
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Literal, Protocol, runtime_checkable

from .rules import GuardrailConfig, parse_config, to_json

META_SK = "META"
RecordResult = Literal["stored", "duplicate", "forbidden"]


def event_sk(ts: str, event_id: str) -> str:
    return f"{ts}#{event_id}"


def classify_cancellation(reasons: list[dict]) -> RecordResult:
    """Map a 2-item TransactWriteItems CancellationReasons list to a result.

    Item 0 is the event Put (attribute_not_exists(sk)); item 1 is the META Update
    (keyVerifier = :kv). A non-failing item is reported as {"Code": "None"}.

    - item 1 failed -> wrong verifier -> "forbidden"
    - only item 0 failed -> duplicate SK -> "duplicate"
    - anything else (throttling, conflict, validation, no failure) -> raise
    """
    if len(reasons) != 2:
        raise RuntimeError(f"expected 2 cancellation reasons, got {len(reasons)}")
    code0 = reasons[0].get("Code", "None")
    code1 = reasons[1].get("Code", "None")
    if code1 == "ConditionalCheckFailed":
        return "forbidden"
    if code0 == "ConditionalCheckFailed" and code1 == "None":
        return "duplicate"
    raise RuntimeError(f"unexpected cancellation reasons: {code0!r}, {code1!r}")


@dataclass
class AgentRecord:
    agent_id: str
    owner_id: str
    key_verifier: str = field(repr=False)  # like Credentials: never in logs or tracebacks
    guardrails: GuardrailConfig
    first_seen: str | None = None
    last_seen: str | None = None
    model: str | None = None
    total_spend_usd: float = 0.0


def record_to_item(r: AgentRecord) -> dict:
    item = {
        "agentId": r.agent_id,
        "sk": META_SK,
        "ownerId": r.owner_id,
        "gsiOwnerId": r.owner_id,
        "keyVerifier": r.key_verifier,
        "guardrails": to_json(r.guardrails),
        "totalSpendUsd": r.total_spend_usd,
    }
    # Absent attribute means null (Unreported_Agent).
    for attr, val in (("firstSeen", r.first_seen), ("lastSeen", r.last_seen), ("model", r.model)):
        if val is not None:
            item[attr] = val
    return item


def item_to_record(item: dict) -> AgentRecord:
    cfg = parse_config(item["guardrails"])
    if not isinstance(cfg, GuardrailConfig):  # stored data is always valid; fail loudly if not
        raise ValueError(f"corrupt guardrails on {item['agentId']}: {cfg}")
    return AgentRecord(
        agent_id=item["agentId"],
        owner_id=item["ownerId"],
        key_verifier=item["keyVerifier"],
        guardrails=cfg,
        first_seen=item.get("firstSeen"),
        last_seen=item.get("lastSeen"),
        model=item.get("model"),
        total_spend_usd=float(item.get("totalSpendUsd", 0.0)),
    )


@runtime_checkable
class Store(Protocol):
    def get_agent(self, agent_id: str) -> AgentRecord | None: ...

    def create_agent_if_absent(self, record: AgentRecord) -> bool: ...

    def put_config(self, agent_id: str, cfg: GuardrailConfig, key_verifier: str) -> bool: ...

    def record_event(self, event, cost: float, key_verifier: str) -> RecordResult: ...

    def bump_last_seen(self, agent_id: str, ts: str) -> None: ...

    def get_event_cost(self, agent_id: str, sk: str) -> float | None: ...

    def query_events(
        self,
        agent_id: str,
        *,
        ascending: bool = True,
        limit: int = 50,
        type_filter: str | None = None,
        start_after: str | None = None,
    ) -> tuple[list[dict], str | None]: ...

    def list_by_owner(self, owner_id: str) -> list[AgentRecord]: ...

    def sum_spend(self, agent_id: str, start_sk: str, end_sk: str) -> float: ...


class InMemoryStore:
    def __init__(self) -> None:
        self.items: dict[tuple[str, str], dict] = {}

    # ---- agent records ----

    def get_agent(self, agent_id: str) -> AgentRecord | None:
        item = self.items.get((agent_id, META_SK))
        return item_to_record(item) if item is not None else None

    def create_agent_if_absent(self, record: AgentRecord) -> bool:
        key = (record.agent_id, META_SK)
        if key in self.items:  # attribute_not_exists(sk)
            return False
        self.items[key] = record_to_item(record)
        return True

    def put_config(self, agent_id: str, cfg: GuardrailConfig, key_verifier: str) -> bool:
        item = self.items.get((agent_id, META_SK))
        if item is None or item["keyVerifier"] != key_verifier:  # keyVerifier = :kv
            return False
        item["guardrails"] = to_json(cfg)
        return True

    # ---- events and queries (tasks 1.9, 1.10) ----

    def record_event(self, event, cost: float, key_verifier: str) -> RecordResult:
        """Mirror of the 2-item TransactWriteItems: verifier check, then SK check, then both writes."""
        meta = self.items.get((event.agent_id, META_SK))
        if meta is None or meta["keyVerifier"] != key_verifier:  # item 1 condition
            return "forbidden"
        key = (event.agent_id, event.sk)
        if key in self.items:  # item 0 condition
            return "duplicate"
        rounded = round_cost(cost)
        self.items[key] = {**copy.deepcopy(event.item), "sk": event.sk, "costUsd": rounded}
        # DynamoStore ADDs the rounded cost, so the total uses it too.
        meta["totalSpendUsd"] = meta.get("totalSpendUsd", 0.0) + rounded
        meta.setdefault("firstSeen", event.ts)
        if event.type == "llm_call":
            meta["model"] = event.item["model"]
        return "stored"

    def bump_last_seen(self, agent_id: str, ts: str) -> None:
        meta = self.items.get((agent_id, META_SK))
        if meta is None:
            return
        if "lastSeen" not in meta or meta["lastSeen"] < ts:
            meta["lastSeen"] = ts

    def get_event_cost(self, agent_id: str, sk: str) -> float | None:
        item = self.items.get((agent_id, sk))
        return None if item is None else float(item["costUsd"])

    def _event_items(self, agent_id: str) -> list[dict]:
        return sorted(
            (v for (aid, sk), v in self.items.items() if aid == agent_id and sk != META_SK),
            key=lambda i: i["sk"],
        )

    def query_events(self, agent_id, *, ascending=True, limit=50, type_filter=None, start_after=None):
        """Like a DynamoDB Query: read up to `limit` items past the cursor, THEN filter by type.

        Returns (items, last_sk). Like LastEvaluatedKey, last_sk is set whenever `limit` items
        were read, even if nothing follows (the next page is then empty with last_sk None).
        """
        items = self._event_items(agent_id)
        if not ascending:
            items.reverse()
        if start_after is not None:
            items = [i for i in items if (i["sk"] > start_after if ascending else i["sk"] < start_after)]
        page = items[:limit]
        last_sk = page[-1]["sk"] if page and len(page) == limit else None
        if type_filter is not None:
            page = [i for i in page if i["type"] == type_filter]
        return copy.deepcopy(page), last_sk

    def list_by_owner(self, owner_id: str) -> list[AgentRecord]:
        return [
            item_to_record(v)
            for (aid, sk), v in sorted(self.items.items())
            if sk == META_SK and v.get("gsiOwnerId") == owner_id
        ]

    def sum_spend(self, agent_id: str, start_sk: str, end_sk: str) -> float:
        """Sum costUsd over events with start_sk <= sk <= end_sk (DynamoDB BETWEEN is inclusive)."""
        return float(sum(i["costUsd"] for i in self._event_items(agent_id) if start_sk <= i["sk"] <= end_sk))

    def snapshot(self) -> dict:
        """Deep copy of all items, for 'store unchanged' assertions in tests."""
        return copy.deepcopy(self.items)


# ---- low-level DynamoDB attribute-value (de)serialization ----


def round_cost(cost: float) -> float:
    """The single rounding rule for costs (6 dp), shared by both stores."""
    return round(float(cost), 6)


def _num(x: float | int | Decimal) -> str:
    """Exact DynamoDB N string. Ints stay ints ("10", not "10.0"); costs are rounded by the caller."""
    if isinstance(x, int):
        return str(x)
    if isinstance(x, Decimal):
        return str(x)
    return str(Decimal(repr(float(x))))


def _cost_num(cost: float) -> str:
    return _num(round_cost(cost))


def to_av(value) -> dict:
    """Serialize a plain Python value to a DynamoDB AttributeValue (low-level client)."""
    if isinstance(value, bool):
        return {"BOOL": value}
    if value is None:
        return {"NULL": True}
    if isinstance(value, str):
        return {"S": value}
    if isinstance(value, (int, float, Decimal)):
        return {"N": _num(value)}
    if isinstance(value, dict):
        return {"M": {k: to_av(v) for k, v in value.items()}}
    if isinstance(value, (list, tuple)):
        return {"L": [to_av(v) for v in value]}
    raise TypeError(f"cannot serialize {type(value)!r} to AttributeValue")


def from_av(av: dict):
    (tag, raw), = av.items()
    if tag == "S":
        return raw
    if tag == "N":
        # Integer-looking strings parse as exact ints (no float detour for big values).
        if "." not in raw and "e" not in raw.lower():
            return int(Decimal(raw))
        return float(raw)
    if tag == "BOOL":
        return raw
    if tag == "NULL":
        return None
    if tag == "M":
        return {k: from_av(v) for k, v in raw.items()}
    if tag == "L":
        return [from_av(v) for v in raw]
    raise TypeError(f"unknown AttributeValue tag {tag!r}")


def item_to_av(item: dict) -> dict:
    return {k: to_av(v) for k, v in item.items()}


def av_to_item(av_item: dict) -> dict:
    return {k: from_av(v) for k, v in av_item.items()}


def _is_conditional_failure(err) -> bool:
    code = getattr(err, "response", {}).get("Error", {}).get("Code")
    return code == "ConditionalCheckFailedException"


def _cancellation_reasons(err):
    return getattr(err, "response", {}).get("CancellationReasons")


class DynamoStore:
    """DynamoDB-backed Store using the boto3 low-level client (typed AttributeValues)."""

    def __init__(self, table_name: str, client=None) -> None:
        self.table_name = table_name
        if client is None:  # pragma: no cover - exercised only on AWS
            import boto3

            client = boto3.client("dynamodb")
        self.client = client

    def get_agent(self, agent_id: str) -> AgentRecord | None:
        resp = self.client.get_item(
            TableName=self.table_name,
            Key={"agentId": {"S": agent_id}, "sk": {"S": META_SK}},
            ConsistentRead=True,
        )
        item = resp.get("Item")
        return item_to_record(av_to_item(item)) if item else None

    def create_agent_if_absent(self, record: AgentRecord) -> bool:
        try:
            self.client.put_item(
                TableName=self.table_name,
                Item=item_to_av(record_to_item(record)),
                ConditionExpression="attribute_not_exists(sk)",
            )
            return True
        except Exception as err:
            if _is_conditional_failure(err):
                return False
            raise

    def put_config(self, agent_id: str, cfg: GuardrailConfig, key_verifier: str) -> bool:
        try:
            self.client.update_item(
                TableName=self.table_name,
                Key={"agentId": {"S": agent_id}, "sk": {"S": META_SK}},
                UpdateExpression="SET guardrails = :g",
                ConditionExpression="keyVerifier = :kv",
                ExpressionAttributeValues={
                    ":g": to_av(to_json(cfg)),
                    ":kv": {"S": key_verifier},
                },
            )
            return True
        except Exception as err:
            if _is_conditional_failure(err):
                return False
            raise

    def record_event(self, event, cost: float, key_verifier: str) -> RecordResult:
        event_item = {**event.item, "sk": event.sk, "costUsd": round_cost(cost)}
        set_parts = ["firstSeen = if_not_exists(firstSeen, :ts)"]
        values = {
            ":c": {"N": _cost_num(cost)},
            ":ts": {"S": event.ts},
            ":kv": {"S": key_verifier},
        }
        if event.type == "llm_call":
            set_parts.append("model = :m")
            values[":m"] = {"S": event.item["model"]}
        update_expr = "ADD totalSpendUsd :c SET " + ", ".join(set_parts)
        try:
            self.client.transact_write_items(
                TransactItems=[
                    {
                        "Put": {
                            "TableName": self.table_name,
                            "Item": item_to_av(event_item),
                            "ConditionExpression": "attribute_not_exists(sk)",
                        }
                    },
                    {
                        "Update": {
                            "TableName": self.table_name,
                            "Key": {"agentId": {"S": event.agent_id}, "sk": {"S": META_SK}},
                            "UpdateExpression": update_expr,
                            "ConditionExpression": "keyVerifier = :kv",
                            "ExpressionAttributeValues": values,
                        }
                    },
                ]
            )
            return "stored"
        except Exception as err:
            reasons = _cancellation_reasons(err)
            if reasons is not None:
                return classify_cancellation(reasons)
            raise

    def bump_last_seen(self, agent_id: str, ts: str) -> None:
        try:
            self.client.update_item(
                TableName=self.table_name,
                Key={"agentId": {"S": agent_id}, "sk": {"S": META_SK}},
                UpdateExpression="SET lastSeen = :ts",
                ConditionExpression="attribute_not_exists(lastSeen) OR lastSeen < :ts",
                ExpressionAttributeValues={":ts": {"S": ts}},
            )
        except Exception as err:
            if _is_conditional_failure(err):
                return
            raise

    def get_event_cost(self, agent_id: str, sk: str) -> float | None:
        resp = self.client.get_item(
            TableName=self.table_name,
            Key={"agentId": {"S": agent_id}, "sk": {"S": sk}},
            ConsistentRead=True,
            ProjectionExpression="costUsd",
        )
        item = resp.get("Item")
        return float(from_av(item["costUsd"])) if item and "costUsd" in item else None

    # ---- queries (task 1.13) ----

    # Event SKs are "{ts}#{eventId}"; ts starts with a digit, so this range sits below "META".
    _SK_LO = "0"
    _SK_HI = "9999999999"  # below "META" lexicographically (digit < 'M')

    def query_events(self, agent_id, *, ascending=True, limit=50, type_filter=None, start_after=None):
        values = {
            ":pk": {"S": agent_id},
            ":lo": {"S": self._SK_LO},
            ":hi": {"S": self._SK_HI},
        }
        kwargs = {
            "TableName": self.table_name,
            "KeyConditionExpression": "agentId = :pk AND sk BETWEEN :lo AND :hi",
            "ScanIndexForward": ascending,
            "Limit": limit,
            "ExpressionAttributeValues": values,
        }
        if start_after is not None:
            kwargs["ExclusiveStartKey"] = {"agentId": {"S": agent_id}, "sk": {"S": start_after}}
        if type_filter is not None:
            kwargs["FilterExpression"] = "#t = :type"
            kwargs["ExpressionAttributeNames"] = {"#t": "type"}
            values[":type"] = {"S": type_filter}
        resp = self.client.query(**kwargs)
        items = [av_to_item(i) for i in resp.get("Items", [])]
        last_sk = resp.get("LastEvaluatedKey", {}).get("sk", {}).get("S")
        return items, last_sk

    def list_by_owner(self, owner_id: str) -> list[AgentRecord]:
        records: list[AgentRecord] = []
        start_key = None
        while True:
            kwargs = {
                "TableName": self.table_name,
                "IndexName": "ownerIndex",
                "KeyConditionExpression": "gsiOwnerId = :owner",
                "ExpressionAttributeValues": {":owner": {"S": owner_id}},
            }
            if start_key is not None:
                kwargs["ExclusiveStartKey"] = start_key
            resp = self.client.query(**kwargs)
            records.extend(item_to_record(av_to_item(i)) for i in resp.get("Items", []))
            start_key = resp.get("LastEvaluatedKey")
            if not start_key:
                return records

    def sum_spend(self, agent_id: str, start_sk: str, end_sk: str) -> float:
        total = 0.0
        start_key = None
        while True:
            kwargs = {
                "TableName": self.table_name,
                "KeyConditionExpression": "agentId = :pk AND sk BETWEEN :lo AND :hi",
                "ExpressionAttributeValues": {
                    ":pk": {"S": agent_id},
                    ":lo": {"S": start_sk},
                    ":hi": {"S": end_sk},
                },
            }
            if start_key is not None:
                kwargs["ExclusiveStartKey"] = start_key
            resp = self.client.query(**kwargs)
            for i in resp.get("Items", []):
                total += float(from_av(i["costUsd"]))
            start_key = resp.get("LastEvaluatedKey")
            if not start_key:
                return float(total)
